from pathlib import Path
import httpx

def send(message, cfg):
    headers = {}
    token_file = cfg.get("token_file")
    if token_file:
        token = Path(token_file).read_text(encoding="utf-8").strip()
        headers["Authorization"] = f"Bearer {token}"
    body = {"topic": cfg["topic"], "title": message["content"].get("title", "NotifyHub"), "message": message["content"]["text"]}
    with httpx.Client(trust_env=not cfg["direct"], timeout=cfg["timeout_seconds"], follow_redirects=False) as client:
        response = client.post(cfg["server"].rstrip("/") + "/", json=body, headers=headers)
        response.raise_for_status()
    return "Published to ntfy server; subscriber display not confirmed"
