import argparse
from .config import load
from .platform_windows import register_notifications

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    cfg = load(args.config)
    register_notifications(cfg)
    print("Registered NotifyHub application identity and Start Menu shortcut")

if __name__ == "__main__":
    main()
