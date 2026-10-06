# This file is standalone: Python standard library only, works on Windows/WSL/Linux.
import argparse
import hashlib
import hmac
import json
import socket
import sys
import time
import uuid
from pathlib import Path

def signed(message, secret):
    result = dict(message)
    if secret:
        result["ts"] = int(time.time())
        raw = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        result["auth"] = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return result

def exchange(sock, host, port, message, secret, timeout=2):
    payload = json.dumps(signed(message, secret), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > 1200:
        raise ValueError("Request exceeds 1200 UTF-8 bytes; shorten content")
    sock.settimeout(timeout)
    sock.send(payload)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = json.loads(sock.recv(4096))
        if response.get("id") == message["id"]:
            return response
    raise TimeoutError("No matching response")

def send(host, port, method, text, title="", secret="", wait=False, timeout=240, request_id=None):
    request_id = request_id or str(uuid.uuid4())
    message = {"v": 1, "id": request_id, "method": method, "content": {"title": title, "text": text}}
    deadline = time.monotonic() + timeout
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((host, port))
        response = None
        for attempt in range(3):
            try:
                response = exchange(sock, host, port, message, secret)
                break
            except socket.timeout:
                continue
        if response is None:
            raise TimeoutError("No ACK: check server, firewall, packet validation and authentication")
        while wait and response["status"] in ("accepted", "running"):
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Final result timeout; query id={request_id} before resending")
            time.sleep(0.25)
            try:
                response = exchange(sock, host, port, {"v": 1, "id": request_id, "op": "status"}, secret)
            except socket.timeout:
                continue
        return response

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int)
    parser.add_argument("--method", choices=("ntfy", "speech", "windows"), required=True)
    parser.add_argument("--text", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--secret-file")
    parser.add_argument("--id")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--timeout", type=float, default=240)
    args = parser.parse_args()
    secret_path = args.secret_file
    port = args.port or 39393
    if args.config:
        from .config import load
        cfg = load(args.config)
        port = args.port or cfg["udp"]["port"]
        secret_path = secret_path or cfg["auth"]["secret_file"]
    secret = Path(secret_path).read_text(encoding="utf-8").strip() if secret_path else ""
    try:
        response = send(args.host, port, args.method, args.text, args.title, secret, args.wait, args.timeout, args.id)
        print(json.dumps(response, ensure_ascii=False))
        return 0 if response["status"] in ("accepted", "running", "completed") else 1
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
