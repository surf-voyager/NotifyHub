import argparse
import multiprocessing
from pathlib import Path
from .config import load

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    controls = parser.add_mutually_exclusive_group()
    controls.add_argument("--stop", action="store_true")
    controls.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    cfg = load(args.config)
    if args.stop or args.restart:
        import win32event, win32con
        from .platform_windows import identity
        event = win32event.OpenEvent(win32con.EVENT_MODIFY_STATE, False, ("Local\\NotifyHub-Quit-" if args.stop else "Local\\NotifyHub-Restart-") + identity(cfg))
        win32event.SetEvent(event)
        event.Close()
        return
    from .tray import run
    try:
        run(cfg)
    except Exception:
        import traceback
        data = Path(cfg["app"]["data_dir"])
        data.mkdir(parents=True, exist_ok=True)
        with (data / "startup-errors.log").open("a", encoding="utf-8") as stream:
            traceback.print_exc(file=stream)
        raise

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
