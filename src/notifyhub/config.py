import os
import re
import tomllib
from pathlib import Path

PATHS = {"runtime": ["python", "pythonw", "powershell", "wsl_executable", "bootstrap_python"], "app": ["data_dir"], "auth": ["secret_file"], "ntfy": ["token_file"]}

def load(path):
    path = Path(path).resolve()
    with path.open("rb") as stream:
        cfg = tomllib.load(stream)
    for section, names in PATHS.items():
        for name in names:
            value = cfg[section].get(name, "")
            if not value:
                continue
            def expand(match):
                key = match.group(1)
                if key not in os.environ:
                    raise ValueError(f"Missing environment variable: {key}")
                return os.environ[key]
            value = re.sub(r"\$\{([^}]+)\}", expand, value)
            target = Path(value)
            cfg[section][name] = str((path.parent / target).resolve()) if not target.is_absolute() else str(target)
    if not 1 <= cfg["udp"]["port"] <= 65535:
        raise ValueError("UDP port must be 1..65535")
    if not 256 <= cfg["udp"]["max_packet_bytes"] <= 1200:
        raise ValueError("UDP packet limit must be 256..1200 bytes")
    for field in ("queue_size", "dedup_seconds"):
        if cfg["udp"][field] <= 0:
            raise ValueError(f"{field} must be positive")
    import ipaddress
    for network in cfg["auth"]["allowed_sources"]:
        ipaddress.ip_network(network)
    for backend in ("ntfy", "speech", "windows"):
        if not isinstance(cfg[backend]["enabled"], bool):
            raise ValueError("enabled must be boolean")
    if cfg["ntfy"]["enabled"] and not cfg["ntfy"]["server"].startswith("https://"):
        raise ValueError("ntfy server must use HTTPS")
    for section, fields in {"ntfy": ["timeout_seconds"], "speech": ["synthesis_timeout_seconds", "playback_timeout_seconds"]}.items():
        for field in fields:
            if cfg[section][field] <= 0:
                raise ValueError(f"{section}.{field} must be positive")
    cfg["config_path"] = str(path)
    return cfg
