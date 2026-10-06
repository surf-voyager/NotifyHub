import json
import logging
import multiprocessing as mp
import os
import threading
import time
from pathlib import Path
from .config import load
from .platform_windows import identity, set_startup, startup_enabled
from .worker import worker_main

class Controller:
    def __init__(self, cfg):
        self.cfg = cfg
        self.lock = threading.RLock()
        self.closed = False
        self.failures = []
        self.process = None
        self.job = None
        self.stop = None
        self.ready = None

    def start(self):
        import win32api, win32job, win32con
        with self.lock:
            if self.closed:
                return
            mp.set_executable(self.cfg["runtime"]["pythonw"])
            self.stop, self.ready = mp.Event(), mp.Event()
            self.process = mp.Process(target=worker_main, args=(self.cfg["config_path"], self.stop, self.ready), name="NotifyHubWorker")
            self.process.start()
            self.job = win32job.CreateJobObject(None, "")
            info = win32job.QueryInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation)
            info["BasicLimitInformation"]["LimitFlags"] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(self.job, win32job.JobObjectExtendedLimitInformation, info)
            handle = win32api.OpenProcess(win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, self.process.pid)
            try:
                win32job.AssignProcessToJobObject(self.job, handle)
            finally:
                handle.Close()
            data = Path(self.cfg["app"]["data_dir"])
            data.mkdir(parents=True, exist_ok=True)
            (data / "processes.json").write_text(json.dumps({"tray": os.getpid(), "worker": self.process.pid}), encoding="utf-8")

    def halt(self):
        with self.lock:
            if self.process:
                self.stop.set()
                self.process.join(timeout=22)
                if self.process.is_alive():
                    self.process.terminate()
                    self.process.join(timeout=5)
                if self.job:
                    self.job.Close()
                self.process.close()
                self.process = self.job = None
            from .backends.speech import clean_orphans
            clean_orphans(Path(self.cfg["app"]["data_dir"]) / "audio")

    def restart(self):
        with self.lock:
            new_cfg = load(self.cfg["config_path"])
            # One instance's persistent state must remain in the same directory.
            if new_cfg["app"]["data_dir"] != self.cfg["app"]["data_dir"]:
                raise ValueError("Changing data_dir requires exit and fresh start")
            for key in ("python", "pythonw"):
                if not Path(new_cfg["runtime"][key]).is_file():
                    raise ValueError(f"Missing configured interpreter: {key}")
            secret = Path(new_cfg["auth"]["secret_file"]).read_text(encoding="utf-8").strip()
            if len(secret) < 32:
                raise ValueError("Invalid UDP key; existing background retained")
            self.halt()
            self.cfg = new_cfg
            self.failures.clear()
            self.start()

    def state(self):
        with self.lock:
            if not self.process or not self.process.is_alive():
                return "Stopped / error"
            return "Running" if self.ready.is_set() else "Starting"

def run(cfg):
    import win32event, win32api, win32con
    import pystray
    from PIL import Image, ImageDraw
    data = Path(cfg["app"]["data_dir"])
    data.mkdir(parents=True, exist_ok=True)
    from logging.handlers import RotatingFileHandler
    logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(data / "tray.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")])
    tag = identity(cfg)
    mutex = win32event.CreateMutex(None, False, "Local\\NotifyHub-" + tag)
    if win32api.GetLastError() == win32con.ERROR_ALREADY_EXISTS:
        mutex.Close()
        return
    quit_event = win32event.CreateEvent(None, True, False, "Local\\NotifyHub-Quit-" + tag)
    win32event.ResetEvent(quit_event)
    controller = Controller(cfg)
    icon = None
    def guarded(action):
        try:
            action()
        except Exception as error:
            logging.exception("Tray action failed")
            if icon:
                icon.notify(str(error)[:200], "NotifyHub")
    def quit_app(*args):
        controller.closed = True
        icon.stop()
    def test(method):
        def send_test(*args):
            import subprocess
            command = [controller.cfg["runtime"]["python"], "-m", "notifyhub.client", "--config", controller.cfg["config_path"], "--method", method, "--title", "NotifyHub test", "--text", "NotifyHub notification test", "--wait"]
            subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)
        return send_test
    def show_file(path):
        return lambda *args: os.startfile(str(path))
    image = Image.new("RGBA", (64, 64), "#2563eb")
    ImageDraw.Draw(image).text((22, 18), "N", fill="white", font_size=30)
    menu = pystray.Menu(
        pystray.MenuItem(lambda item: "NotifyHub: " + controller.state(), None, enabled=False),
        pystray.MenuItem("Test notification", pystray.Menu(*(pystray.MenuItem(method, test(method)) for method in ("ntfy", "speech", "windows")))),
        pystray.MenuItem("Recent requests", lambda *args: guarded(lambda: export_history(controller.cfg))),
        pystray.MenuItem("Logs", show_file(data)),
        pystray.MenuItem("Configuration", show_file(cfg["config_path"])),
        pystray.MenuItem("Start at login", lambda *args: guarded(lambda: set_startup(controller.cfg, not startup_enabled(controller.cfg))), checked=lambda item: startup_enabled(controller.cfg)),
        pystray.MenuItem("Reload / restart background", lambda *args: threading.Thread(target=lambda: guarded(controller.restart), daemon=True).start()),
        pystray.MenuItem("Help", show_file(Path(__file__).resolve().parents[2] / "README.md")),
        pystray.MenuItem("Exit", quit_app))
    icon = pystray.Icon("NotifyHub", image, "NotifyHub", menu)
    def supervise():
        while not controller.closed:
            if win32event.WaitForSingleObject(quit_event, 500) == win32event.WAIT_OBJECT_0:
                quit_app()
                break
            with controller.lock:
                if controller.process and not controller.process.is_alive():
                    now = time.monotonic()
                    controller.failures = [t for t in controller.failures if now-t < 60]
                    if len(controller.failures) < 3:
                        controller.failures.append(now)
                        guarded(controller.halt)
                        guarded(controller.start)
                icon.title = "NotifyHub: " + controller.state()
    try:
        controller.start()
        threading.Thread(target=supervise, daemon=True).start()
        icon.run()
    finally:
        controller.closed = True
        controller.halt()
        (data / "processes.json").unlink(missing_ok=True)
        quit_event.Close()
        mutex.Close()

def export_history(cfg):
    import sqlite3
    path = Path(cfg["app"]["data_dir"])
    with sqlite3.connect(path / "requests.sqlite3") as db:
        rows = db.execute("SELECT id, method, status, detail, datetime(updated, 'unixepoch', 'localtime') FROM requests ORDER BY updated DESC LIMIT 100").fetchall()
    target = path / "recent-requests.txt"
    target.write_text("\n".join(" | ".join(str(x) for x in row) for row in rows), encoding="utf-8")
    os.startfile(str(target))
