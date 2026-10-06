import threading
from xml.sax.saxutils import escape

_live = []

def send(message, cfg):
    from winrt.windows.data.xml.dom import XmlDocument
    from winrt.windows.ui.notifications import ToastNotification, ToastNotificationManager
    title = message["content"].get("title") or cfg["default_title"]
    text = message["content"]["text"]
    xml = XmlDocument()
    xml.load_xml(f'<toast><visual><binding template="ToastGeneric"><text>{escape(title)}</text><text>{escape(text)}</text></binding></visual></toast>')
    toast = ToastNotification(xml)
    failures = []
    toast.add_failed(lambda sender, args: failures.append(str(args.error_code)))
    notifier = ToastNotificationManager.create_toast_notifier(cfg["app_id"])
    setting = notifier.setting
    if int(setting) != 0:
        raise RuntimeError(f"Windows notifications disabled: setting={setting}")
    notifier.show(toast)
    # Give async failures a short observation window; retain handles for callbacks.
    threading.Event().wait(0.5)
    if failures:
        raise RuntimeError("Toast failed: " + failures[0])
    _live.append(toast)
    if len(_live) > 100:
        del _live[:-100]
    return "Submitted to Windows; popup visibility not confirmed"
