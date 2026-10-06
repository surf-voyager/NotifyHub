import hashlib
import hmac
import ipaddress
import json
import math
import time

METHODS = ("ntfy", "speech", "windows")

def canonical(message):
    return json.dumps({k: v for k, v in message.items() if k != "auth"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def sign(message, secret):
    message["ts"] = int(time.time())
    message["auth"] = hmac.new(secret.encode(), canonical(message), hashlib.sha256).hexdigest()
    return message

def validate(raw, address, cfg, require_content=True):
    if len(raw) > cfg["udp"]["max_packet_bytes"]:
        raise ValueError("packet_too_large")
    message = json.loads(raw.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError("invalid_number")))
    if not isinstance(message, dict) or message.get("v") != 1:
        raise ValueError("invalid_version")
    request_id = message.get("id")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 96:
        raise ValueError("invalid_id")
    ip = ipaddress.ip_address(address[0])
    networks = cfg["auth"]["allowed_sources"]
    if not ip.is_loopback and networks and not any(ip in ipaddress.ip_network(n) for n in networks):
        raise ValueError("source_denied")
    if not ip.is_loopback or "auth" in message:
        secret = cfg.get("secret", "")
        timestamp = message.get("ts")
        if not secret or type(timestamp) not in (int, float) or not math.isfinite(timestamp) or abs(time.time() - timestamp) > cfg["auth"]["max_clock_skew_seconds"]:
            raise ValueError("authentication_failed")
        expected = hmac.new(secret.encode(), canonical(message), hashlib.sha256).hexdigest()
        auth = message.get("auth", "")
        if not isinstance(auth, str) or not hmac.compare_digest(auth, expected):
            raise ValueError("authentication_failed")
    op = message.get("op", "notify")
    if op not in ("notify", "status", "ping"):
        raise ValueError("invalid_operation")
    if op == "notify" and require_content:
        method = message.get("method")
        if method not in METHODS:
            raise ValueError("invalid_method")
        if not cfg[method]["enabled"]:
            raise ValueError("backend_disabled")
        content = message.get("content")
        if not isinstance(content, dict) or not isinstance(content.get("text"), str) or not content["text"].strip():
            raise ValueError("invalid_content")
        if not isinstance(content.get("title", ""), str) or len(content.get("title", "")) > 100:
            raise ValueError("invalid_title")
        if any(ord(c) < 32 and c not in "\n\r\t" for c in content["text"] + content.get("title", "")):
            raise ValueError("invalid_control_character")
        if method == "ntfy" and not cfg["ntfy"]["topic"]:
            raise ValueError("ntfy_topic_not_configured")
    return message

def fingerprint(message):
    payload = {"method": message["method"], "content": message["content"]}
    return hashlib.sha256(canonical(payload)).hexdigest()
