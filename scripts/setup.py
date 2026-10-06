"""Portable first-run installer; no machine-specific defaults."""
import argparse
import json
import os
import secrets
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="")
    parser.add_argument("--data-dir")
    parser.add_argument("--no-register", action="store_true")
    parser.add_argument("--register-only", action="store_true")
    args = parser.parse_args()
    target = ROOT / ".venv"
    python = target / "Scripts/python.exe"
    if not args.register_only:
        if not python.exists():
            venv.EnvBuilder(with_pip=True).create(target)
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.lock")], check=True)
        subprocess.run([str(python), "-m", "pip", "install", "--no-deps", "--no-build-isolation", "-e", str(ROOT)], check=True)
    local = ROOT / "config/local.toml"
    if not local.exists():
        text = (ROOT / "config/config.example.toml").read_text(encoding="utf-8")
        text = text.replace('[runtime]\n', '[runtime]\nbootstrap_python = ' + json.dumps(sys.executable.replace("\\", "/")) + '\n')
        text = text.replace('topic = ""', 'topic = ' + json.dumps(args.topic, ensure_ascii=False))
        if args.data_dir:
            text = text.replace('data_dir = "${LOCALAPPDATA}/NotifyHub"', 'data_dir = ' + json.dumps(str(Path(args.data_dir).resolve()).replace("\\", "/")))
        local.write_text(text, encoding="utf-8")
    key = ROOT / "config/udp.key"
    if not key.exists():
        key.write_text(secrets.token_hex(32), encoding="utf-8")
    # Restrict the secret to the current user, SYSTEM and administrators.
    if os.name == "nt":
        sid = subprocess.check_output([str(python), "-c", "import win32api,win32security; print(win32security.ConvertSidToStringSid(win32security.GetTokenInformation(win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32security.TOKEN_QUERY),win32security.TokenUser)[0]))"], text=True).strip()
        subprocess.run(["icacls", str(key), "/inheritance:r", "/grant:r", f"*{sid}:(F)", "*S-1-5-18:(F)", "*S-1-5-32-544:(F)"], check=True, stdout=subprocess.DEVNULL)
    if not args.no_register:
        subprocess.run([str(python), "-m", "notifyhub.install", "--config", str(local)], check=True)
    print(f"Installed. Config: {local}")
    print("Autostart is unchanged; enable it from the tray if desired.")

if __name__ == "__main__":
    main()
