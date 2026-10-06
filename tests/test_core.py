import copy
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from notifyhub.config import load
from notifyhub.protocol import validate, sign
from notifyhub.worker import Server
from notifyhub.backends.speech import direct_environment, clean_orphans, send as speech_send
from notifyhub.backends.ntfy import send as ntfy_send
from notifyhub.client import send as client_send
from notifyhub.store import Store

ROOT = Path(__file__).resolve().parents[1]

def config(folder):
    template = (ROOT / "config/config.example.toml").read_text(encoding="utf-8")
    template = template.replace('${LOCALAPPDATA}/NotifyHub', str(folder).replace("\\", "/"))
    template = template.replace('topic = ""', 'topic = "test-topic"')
    path = folder / "local.toml"
    path.write_text(template, encoding="utf-8")
    (folder / "udp.key").write_text("a" * 64)
    cfg = load(path)
    cfg["secret"] = "a" * 64
    cfg["udp"]["bind"] = "127.0.0.1"
    cfg["udp"]["port"] = 0
    return cfg

def message(request_id="test", method="windows"):
    return {"v": 1, "id": request_id, "method": method, "content": {"text": "测试通知", "title": "测试"}}

def raw(msg):
    return json.dumps(msg, ensure_ascii=False).encode("utf-8")

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.cfg = config(self.folder)

    def tearDown(self):
        self.tmp.cleanup()

    def test_relative_paths_independent_of_cwd(self):
        self.assertEqual(self.cfg["auth"]["secret_file"], str(self.folder / "udp.key"))
        self.assertEqual(self.cfg["runtime"]["python"], str((self.folder / "../.venv/Scripts/python.exe").resolve()))

    def test_migration_changes_relative_paths(self):
        other = self.folder / "new machine with spaces"
        other.mkdir()
        migrated = config(other)
        self.assertNotEqual(migrated["runtime"]["python"], self.cfg["runtime"]["python"])
        self.assertEqual(migrated["auth"]["secret_file"], str(other / "udp.key"))

    def test_nonfinite_timestamp_rejected(self):
        item = message()
        item["ts"] = float("nan")
        item["auth"] = "x"
        with self.assertRaises(ValueError):
            validate(raw(item), ("192.0.2.1", 3), self.cfg)

    def test_windows_runtime_constants_and_overload(self):
        import winerror
        from winrt.windows.ui.notifications import ToastNotificationManager
        self.assertEqual(winerror.ERROR_ALREADY_EXISTS, 183)
        notifier = ToastNotificationManager.create_toast_notifier_with_id("NotifyHub.Test")
        self.assertIsNotNone(notifier)

    def test_windows_shortcut_identity_api(self):
        import pythoncom
        from win32com.shell import shell
        from win32com.propsys import propsys, pscon
        link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
        props = link.QueryInterface(propsys.IID_IPropertyStore)
        props.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType("NotifyHub.Desktop"))
        props.Commit()
        self.assertEqual(props.GetValue(pscon.PKEY_AppUserModel_ID).GetValue(), "NotifyHub.Desktop")

    def test_loopback_simple_request(self):
        self.assertEqual(validate(raw(message()), ("127.0.0.1", 3), self.cfg)["method"], "windows")

    def test_remote_requires_auth(self):
        with self.assertRaisesRegex(ValueError, "authentication_failed"):
            validate(raw(message()), ("192.0.2.1", 3), self.cfg)

    def test_remote_hmac(self):
        signed = sign(message(), self.cfg["secret"])
        self.assertEqual(validate(raw(signed), ("192.0.2.1", 3), self.cfg)["id"], "test")

    def test_tampered_hmac(self):
        signed = sign(message(), self.cfg["secret"])
        signed["content"]["text"] = "tampered"
        with self.assertRaises(ValueError):
            validate(raw(signed), ("192.0.2.1", 3), self.cfg)

    def test_expired_auth(self):
        signed = sign(message(), self.cfg["secret"])
        signed["ts"] -= 1000
        with self.assertRaises(ValueError):
            validate(raw(signed), ("192.0.2.1", 3), self.cfg)

    def test_source_allowlist(self):
        self.cfg["auth"]["allowed_sources"] = ["192.0.2.0/24"]
        with self.assertRaisesRegex(ValueError, "source_denied"):
            validate(raw(sign(message(), self.cfg["secret"])), ("198.51.100.1", 3), self.cfg)

    def test_invalid_method(self):
        with self.assertRaisesRegex(ValueError, "invalid_method"):
            validate(raw(message(method="exec")), ("127.0.0.1", 3), self.cfg)

    def test_empty_content(self):
        item = message()
        item["content"]["text"] = " "
        with self.assertRaisesRegex(ValueError, "invalid_content"):
            validate(raw(item), ("127.0.0.1", 3), self.cfg)

    def test_control_characters(self):
        item = message()
        item["content"]["text"] = "bad\x00xml"
        with self.assertRaises(ValueError):
            validate(raw(item), ("127.0.0.1", 3), self.cfg)

    def test_utf8_byte_limit(self):
        item = message()
        item["content"]["text"] = "中" * 500
        with self.assertRaisesRegex(ValueError, "packet_too_large"):
            validate(raw(item), ("127.0.0.1", 3), self.cfg)

    def test_disabled_backend(self):
        self.cfg["speech"]["enabled"] = False
        with self.assertRaisesRegex(ValueError, "backend_disabled"):
            validate(raw(message(method="speech")), ("127.0.0.1", 3), self.cfg)

    def test_missing_topic(self):
        self.cfg["ntfy"]["topic"] = ""
        with self.assertRaisesRegex(ValueError, "ntfy_topic"):
            validate(raw(message(method="ntfy")), ("127.0.0.1", 3), self.cfg)

    def test_proxy_environment_isolated(self):
        source = {"HTTP_PROXY": "bad", "https_proxy": "bad", "ALL_PROXY": "bad", "PATH": "keep"}
        env = direct_environment(source)
        self.assertEqual(env["NO_PROXY"], "*")
        self.assertNotIn("HTTP_PROXY", env)
        self.assertEqual(env["PATH"], "keep")
        self.assertEqual(source["HTTP_PROXY"], "bad")

    def test_windows_registry_proxy_bypass(self):
        from urllib.request import proxy_bypass
        with patch.dict(os.environ, direct_environment(os.environ), clear=True):
            self.assertTrue(proxy_bypass("speech.platform.bing.com"))

    def test_ntfy_disables_proxy_inheritance(self):
        with patch("notifyhub.backends.ntfy.httpx.Client") as client:
            response = client.return_value.__enter__.return_value.post.return_value
            response.raise_for_status.return_value = None
            ntfy_send(message(method="ntfy"), self.cfg["ntfy"])
            self.assertFalse(client.call_args.kwargs["trust_env"])
            payload = client.return_value.__enter__.return_value.post.call_args.kwargs["json"]
            self.assertEqual(payload["message"], "测试通知")

    def test_clean_only_owned_audio_folders(self):
        audio = self.folder / "audio"
        owned = audio / "job-owned"
        unowned = audio / "job-unowned"
        owned.mkdir(parents=True)
        unowned.mkdir()
        (owned / ".notifyhub-owned").touch()
        (owned / "speech.mp3").write_bytes(b"audio")
        clean_orphans(audio)
        self.assertFalse(owned.exists())
        self.assertTrue(unowned.exists())

    def test_store_restart_does_not_replay(self):
        store = Store(self.folder / "test.db")
        store.insert(message(), "digest")
        store.recover()
        self.assertEqual(store.get("test")["status"], "interrupted")
        store.close()

    def test_request_dedup_and_conflict(self):
        server = Server(self.cfg, threading.Event(), handlers={})
        try:
            server.handle(raw(message()), ("127.0.0.1", 3))
            server.handle(raw(message()), ("127.0.0.1", 3))
            self.assertEqual(server.queues["windows"].qsize(), 1)
            changed = message()
            changed["content"]["text"] = "different"
            with self.assertRaisesRegex(ValueError, "id_conflict"):
                server.handle(raw(changed), ("127.0.0.1", 3))
        finally:
            server.socket.close()
            server.store.close()

    def test_queue_full_is_not_recorded_as_accepted(self):
        self.cfg["udp"]["queue_size"] = 1
        server = Server(self.cfg, threading.Event(), handlers={})
        try:
            server.handle(raw(message("one")), ("127.0.0.1", 3))
            with self.assertRaisesRegex(ValueError, "queue_full"):
                server.handle(raw(message("two")), ("127.0.0.1", 3))
            self.assertIsNone(server.store.get("two"))
        finally:
            server.socket.close()
            server.store.close()

    def test_udp_and_backend_isolation(self):
        stop = threading.Event()
        release = threading.Event()
        started = threading.Event()
        def speech_handler(msg):
            started.set()
            release.wait(3)
            return "played"
        handlers = {"speech": speech_handler, "windows": lambda m: "submitted", "ntfy": lambda m: "published"}
        server = Server(self.cfg, stop, handlers)
        thread = threading.Thread(target=server.run)
        thread.start()
        try:
            host, port = server.address
            first = client_send(host, port, "speech", "long speech", request_id="speech")
            self.assertIn(first["status"], ("accepted", "running"))
            self.assertTrue(started.wait(2))
            result = client_send(host, port, "windows", "instant", wait=True, timeout=3)
            self.assertEqual(result["status"], "completed")
            release.set()
        finally:
            release.set()
            stop.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        # Port is released after shutdown.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(server.address)

    def test_speech_interrupt_terminates_and_cleans(self):
        self.cfg["runtime"]["python"] = "fake-python"
        stopped = threading.Event()
        stopped.set()
        with patch("notifyhub.backends.speech.subprocess.Popen") as popen:
            process = popen.return_value
            process.poll.return_value = None
            with self.assertRaisesRegex(RuntimeError, "interrupted"):
                speech_send(message(method="speech"), self.cfg, stopped)
            process.terminate.assert_called_once()
        self.assertEqual(list((self.folder / "audio").glob("job-*")), [])

    def test_standalone_client_matches_module(self):
        self.assertEqual((ROOT / "client/notify.py").read_bytes(), (ROOT / "src/notifyhub/client.py").read_bytes())

    def test_template_has_no_host_configuration(self):
        text = (ROOT / "config/config.example.toml").read_text(encoding="utf-8")
        self.assertNotIn("Anaconda", text)

if __name__ == "__main__":
    unittest.main()
