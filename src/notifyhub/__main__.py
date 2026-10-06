import argparse
import multiprocessing
from pathlib import Path
from .config import load

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()
    cfg = load(args.config)
    if args.stop:
        import win32event, win32con
        from .platform_windows import identity
        event = win32event.OpenEvent(win32con.EVENT_MODIFY_STATE, False, "Local\\NotifyHub-Quit-" + identity(cfg))
        win32event.SetEvent(event)
        event.Close()
        return
    from .tray import run
    run(cfg)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
