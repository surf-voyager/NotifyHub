"""Exercise the same local controls used by the tray menu, without sending notifications."""
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from notifyhub.config import load
from notifyhub.platform_windows import startup_command

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/local.toml"

def wait_for(check, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.2)
    raise TimeoutError("Lifecycle condition not reached")

def main():
    cfg = load(CONFIG)
    data = Path(cfg["app"]["data_dir"])
    state_file = data / "processes.json"
    def state():
        try:
            return json.loads(state_file.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None
    before = wait_for(state)
    # The exact registry startup command must work and retain single-instance behavior.
    duplicate = subprocess.Popen(startup_command(cfg), creationflags=subprocess.CREATE_NO_WINDOW)
    duplicate.wait(timeout=10)
    assert state() == before, "Duplicate instance changed running process state"
    subprocess.run([sys.executable, "-m", "notifyhub", "--config", str(CONFIG), "--restart"], check=True)
    after = wait_for(lambda: (s if (s := state()) and s["worker"] != before["worker"] else None))
    assert before["tray"] == after["tray"], "Restart replaced tray process"
    subprocess.run([sys.executable, "-m", "notifyhub", "--config", str(CONFIG), "--stop"], check=True)
    wait_for(lambda: not state_file.exists())
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("0.0.0.0", cfg["udp"]["port"]))
    subprocess.Popen(startup_command(cfg), creationflags=subprocess.CREATE_NO_WINDOW)
    final = wait_for(state)
    report = {"single_instance": True, "background_restart": True, "tray_preserved": True, "exit_released_port": True, "registry_command_launch": True, "final_processes": final}
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/local-lifecycle.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))

if __name__ == "__main__":
    main()
