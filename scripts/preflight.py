"""Pre-deployment network checks: no notification is published or played."""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--speech-child")
    args = parser.parse_args()
    if args.speech_child:
        from notifyhub.speech_task import synthesize
        path = Path(args.speech_child) / "probe.mp3"
        data = {"message": {"content": {"text": "NotifyHub test"}}, "speech": {"voice": "zh-CN-XiaoxiaoNeural", "rate": "+0%", "volume": "+0%", "synthesis_timeout_seconds": 45}, "audio": str(path)}
        asyncio.run(synthesize(data))
        if path.stat().st_size < 100:
            raise RuntimeError("Empty synthesized audio")
        print(json.dumps({"speech_direct_bytes": path.stat().st_size}))
        return
    import httpx
    from notifyhub.backends.speech import direct_environment
    env = os.environ.copy()
    env.update({"HTTP_PROXY": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1", "ALL_PROXY": "http://127.0.0.1:1"})
    # HTTP check does not publish to a topic.
    old = os.environ.copy()
    try:
        os.environ.update(env)
        with httpx.Client(trust_env=False, timeout=20) as client:
            response = client.get("https://ntfy.sh/")
            response.raise_for_status()
        print(json.dumps({"ntfy_direct_http": response.status_code}))
    finally:
        os.environ.clear()
        os.environ.update(old)
    with tempfile.TemporaryDirectory(prefix="notifyhub-preflight-") as folder:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--speech-child", folder], env=direct_environment(env), text=True, capture_output=True, timeout=55)
        print(result.stdout.strip())
        if result.returncode:
            print(result.stderr, file=sys.stderr)
            raise SystemExit(result.returncode)
    print("Preflight passed; temporary audio deleted without playback")

if __name__ == "__main__":
    main()
