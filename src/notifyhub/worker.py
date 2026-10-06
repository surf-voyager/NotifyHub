import json
import logging
import queue
import socket
import threading
import time
from pathlib import Path
from . import hooks
from .protocol import METHODS, fingerprint, validate
from .store import Store
from .backends import ntfy, speech, windows

class Server:
    def __init__(self, cfg, stop, handlers=None):
        self.cfg, self.stop = cfg, stop
        self.data = Path(cfg["app"]["data_dir"])
        self.data.mkdir(parents=True, exist_ok=True)
        cfg["secret"] = Path(cfg["auth"]["secret_file"]).read_text(encoding="utf-8").strip()
        if len(cfg["secret"]) < 32:
            raise ValueError("UDP secret is missing or too short; run setup")
        self.store = Store(self.data / "requests.sqlite3")
        self.store.recover()
        self.queues = {method: queue.Queue(cfg["udp"]["queue_size"]) for method in METHODS}
        self.handlers = handlers or {"ntfy": lambda m: ntfy.send(m, cfg["ntfy"]), "speech": lambda m: speech.send(m, cfg, stop), "windows": lambda m: windows.send(m, cfg["windows"])}
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            if hasattr(socket, "SIO_UDP_CONNRESET"):
                self.socket.ioctl(socket.SIO_UDP_CONNRESET, False)
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            self.socket.bind((cfg["udp"]["bind"], cfg["udp"]["port"]))
            self.socket.settimeout(0.25)
        except Exception:
            self.socket.close()
            self.store.close()
            raise
        self.address = self.socket.getsockname()

    def result(self, request_id):
        record = self.store.get(request_id)
        if record:
            record.pop("fingerprint")
            return record
        return {"id": request_id, "status": "unknown"}

    def handle(self, raw, address):
        message = validate(raw, address, self.cfg)
        request_id = message["id"]
        op = message.get("op", "notify")
        if op == "ping":
            return {"id": request_id, "status": "ready", "version": "0.1.0"}
        if op == "status":
            return self.result(request_id)
        digest = fingerprint(message)
        prior = self.store.get(request_id)
        if prior:
            if prior["fingerprint"] != digest:
                raise ValueError("id_conflict")
            return self.result(request_id)
        self.store.insert(message, digest)
        try:
            self.queues[message["method"]].put_nowait(message)
        except queue.Full:
            self.store.remove(request_id)
            raise ValueError("queue_full")
        return {"id": request_id, "method": message["method"], "status": "accepted"}

    def consume(self, method):
        while not self.stop.is_set():
            try:
                message = self.queues[method].get(timeout=0.2)
            except queue.Empty:
                continue
            request_id = message["id"]
            try:
                self.store.update(request_id, "running")
                hooks.on_message(message, self.cfg)
                detail = self.handlers[method](message)
                self.store.update(request_id, "completed", detail)
                logging.info("Request %s method=%s completed", request_id, method)
            except Exception as error:
                logging.exception("Request %s method=%s failed", request_id, method)
                self.store.update(request_id, "interrupted" if self.stop.is_set() else "failed", type(error).__name__ + ": " + str(error)[:200])
            finally:
                self.queues[method].task_done()

    def run(self, ready=None):
        threads = [threading.Thread(target=self.consume, args=(m,), daemon=True) for m in METHODS]
        for thread in threads:
            thread.start()
        try:
            hooks.on_start(self.cfg)
            if ready:
                ready.set()
            last_prune = 0
            while not self.stop.is_set():
                if time.monotonic() - last_prune > 60:
                    self.store.prune(self.cfg["udp"]["dedup_seconds"])
                    last_prune = time.monotonic()
                try:
                    raw, address = self.socket.recvfrom(65535)
                except socket.timeout:
                    continue
                try:
                    validated = validate(raw, address, self.cfg, require_content=False)
                    try:
                        response = self.handle(raw, address)
                    except ValueError as error:
                        response = {"id": validated["id"], "status": "rejected", "detail": str(error)}
                except Exception as error:
                    # Malformed or unauthorized traffic receives no response.
                    # Valid authenticated client errors are shown in local logs.
                    logging.warning("Rejected request from %s: %s", address[0], str(error)[:100])
                    continue
                try:
                    self.socket.sendto(json.dumps(response, ensure_ascii=False).encode("utf-8"), address)
                except OSError:
                    logging.warning("UDP response could not be delivered to %s", address[0])
        finally:
            self.socket.close()
            self.stop.set()
            for thread in threads:
                thread.join(timeout=20)
            self.store.recover()
            hooks.on_stop(self.cfg)
            # Daemon threads still active after deadline terminate with worker.
            if not any(t.is_alive() for t in threads):
                self.store.close()

def worker_main(config_path, stop, ready):
    from .config import load
    from logging.handlers import RotatingFileHandler
    cfg = load(config_path)
    data = Path(cfg["app"]["data_dir"])
    data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(force=True, level=logging.INFO, handlers=[RotatingFileHandler(data / "service.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")], format="%(asctime)s %(levelname)s %(message)s")
    try:
        speech.clean_orphans(data / "audio")
        Server(cfg, stop).run(ready)
    except Exception:
        logging.exception("Background process failed")
        raise
