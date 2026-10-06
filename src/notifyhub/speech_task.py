import asyncio
import ctypes
import json
import sys
from pathlib import Path

async def synthesize(data):
    import edge_tts
    cfg = data["speech"]
    await asyncio.wait_for(edge_tts.Communicate(data["message"]["content"]["text"], cfg["voice"], rate=cfg["rate"], volume=cfg["volume"], proxy=None).save(data["audio"]), cfg["synthesis_timeout_seconds"])

def play(path, timeout):
    import time
    api = ctypes.windll.winmm
    api.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
    def command(text, result=False):
        buf = ctypes.create_unicode_buffer(256)
        code = api.mciSendStringW(text, buf, len(buf), None)
        if code:
            raise RuntimeError(f"Windows audio error: {code}")
        return buf.value
    opened = False
    try:
        command(f'open "{path}" type mpegvideo alias notifyhub_audio')
        opened = True
        command("play notifyhub_audio")
        deadline = time.monotonic() + timeout
        while command("status notifyhub_audio mode", True) == "playing":
            if time.monotonic() >= deadline:
                raise TimeoutError("Audio playback timeout")
            time.sleep(0.1)
    finally:
        if opened:
            command("close notifyhub_audio")

if __name__ == "__main__":
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    try:
        asyncio.run(synthesize(data))
        play(data["audio"], data["speech"]["playback_timeout_seconds"])
    except Exception:
        import traceback
        # Persist diagnostic before parent deletes the task folder.
        error_path = Path(data["audio"]).parent.parent.parent / "speech-errors.log"
        with error_path.open("a", encoding="utf-8") as stream:
            traceback.print_exc(file=stream)
        raise
