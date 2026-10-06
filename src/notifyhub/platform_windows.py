import hashlib
import subprocess
from pathlib import Path

STARTUP_NAME = "NotifyHub"

def identity(cfg):
    return hashlib.sha256(cfg["app"]["data_dir"].lower().encode()).hexdigest()[:20]

def startup_command(cfg):
    return subprocess.list2cmdline([cfg["runtime"]["pythonw"], "-m", "notifyhub", "--config", cfg["config_path"]])

def startup_enabled(cfg):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            value, _ = winreg.QueryValueEx(key, STARTUP_NAME)
        return value == startup_command(cfg)
    except FileNotFoundError:
        return False

def set_startup(cfg, enabled):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        if enabled:
            command = startup_command(cfg)
            if len(command) > 260:
                raise ValueError("Startup command exceeds Windows Run limit (260 characters)")
            winreg.SetValueEx(key, STARTUP_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, STARTUP_NAME)
            except FileNotFoundError:
                pass

def register_notifications(cfg):
    import winreg
    import pythoncom
    from win32com.shell import shell
    from win32com.propsys import propsys, pscon
    import os
    from PIL import Image, ImageDraw
    data = Path(cfg["app"]["data_dir"])
    data.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (64, 64), "#2563eb")
    draw = ImageDraw.Draw(image)
    draw.text((22, 18), "N", fill="white", font_size=30)
    icon = data / "notifyhub.ico"
    image.save(icon)
    app_id = cfg["windows"]["app_id"]
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{app_id}") as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "NotifyHub")
        winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(icon))
    shortcut = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/NotifyHub.lnk"
    link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
    link.SetPath(cfg["runtime"]["pythonw"])
    link.SetArguments(subprocess.list2cmdline(["-m", "notifyhub", "--config", cfg["config_path"]]))
    link.SetWorkingDirectory(str(Path(cfg["config_path"]).parent))
    link.SetIconLocation(str(icon), 0)
    properties = link.QueryInterface(propsys.IID_IPropertyStore)
    properties.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(app_id))
    properties.Commit()
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(shortcut), 0)
