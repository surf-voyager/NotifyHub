"""Real user-session acceptance. Publishes/plays explicitly marked test notifications."""
import argparse
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from notifyhub.client import send
from notifyhub.config import load
from notifyhub.platform_windows import set_startup, startup_enabled, startup_command

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "config/local.toml"))
    args = parser.parse_args()
    cfg = load(args.config)
    secret = Path(cfg["auth"]["secret_file"]).read_text(encoding="utf-8").strip()
    report = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": {}}
    data = Path(cfg["app"]["data_dir"])
    for method in ("windows", "ntfy", "speech"):
        request_id = "acceptance-" + method + "-" + str(uuid.uuid4())
        result = send("127.0.0.1", cfg["udp"]["port"], method, "NotifyHub 部署测试。通知服务已就绪。", "NotifyHub 部署测试", secret, True, 240, request_id)
        report["results"][method] = result
        print(json.dumps({method: result}, ensure_ascii=False), flush=True)
    report["audio_folders_remaining"] = len(list((data / "audio").glob("job-*")))
    prior = startup_enabled(cfg)
    try:
        set_startup(cfg, True)
        report["autostart_enabled_check"] = startup_enabled(cfg)
        set_startup(cfg, False)
        report["autostart_disabled_check"] = not startup_enabled(cfg)
    finally:
        set_startup(cfg, prior)
    report["autostart_final"] = startup_enabled(cfg)
    try:
        from winrt.windows.ui.notifications import ToastNotificationManager as T
        report["windows_history_count"] = len(T.history.get_history_with_id(cfg["windows"]["app_id"]))
    except Exception as error:
        report["windows_history_error"] = str(error)
    report["passed"] = all(r["status"] == "completed" for r in report["results"].values()) and report["audio_folders_remaining"] == 0 and report["autostart_enabled_check"] and report["autostart_disabled_check"]
    folder = ROOT / "reports"
    folder.mkdir(exist_ok=True)
    (folder / "local-acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "audio_remaining": report["audio_folders_remaining"], "windows_history": report.get("windows_history_count")}), flush=True)
    raise SystemExit(0 if report["passed"] else 1)

if __name__ == "__main__":
    main()
