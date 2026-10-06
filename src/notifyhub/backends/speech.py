import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

def direct_environment(environment):
    env = {key: value for key, value in environment.items() if key.lower() not in ("http_proxy", "https_proxy", "all_proxy", "no_proxy", "ws_proxy", "wss_proxy")}
    # urllib on Windows may otherwise discover registry proxies.
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    return env

def clean_orphans(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    import shutil
    for path in root.glob("job-*"):
        if path.is_dir() and (path / ".notifyhub-owned").is_file():
            shutil.rmtree(path)

def send(message, cfg, stop):
    root = Path(cfg["app"]["data_dir"]) / "audio"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="job-", dir=root) as folder:
        folder = Path(folder)
        (folder / ".notifyhub-owned").touch()
        payload = folder / "request.json"
        payload.write_text(json.dumps({"message": message, "speech": cfg["speech"], "audio": str(folder / "speech.mp3")}, ensure_ascii=False), encoding="utf-8")
        env = direct_environment(os.environ) if cfg["speech"]["direct"] else os.environ.copy()
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        with (folder / "error.log").open("w", encoding="utf-8") as errors:
            process = subprocess.Popen([cfg["runtime"]["python"], "-m", "notifyhub.speech_task", str(payload)], env=env, stdout=subprocess.DEVNULL, stderr=errors, creationflags=flags)
            deadline = time.monotonic() + cfg["speech"]["synthesis_timeout_seconds"] + cfg["speech"]["playback_timeout_seconds"] + 5
            try:
                while process.poll() is None:
                    if stop.wait(0.1):
                        raise RuntimeError("Speech interrupted by stop/restart")
                    if time.monotonic() > deadline:
                        raise TimeoutError("Speech task timeout")
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
        if process.returncode:
            # Don't include request contents or credentials in error responses.
            raise RuntimeError(f"Speech task failed, exit={process.returncode}; inspect speech-errors.log")
    return "Playback completed and temporary audio removed"
