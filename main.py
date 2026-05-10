#!/usr/bin/env python3
import asyncio
import signal
from pathlib import Path

import yaml
import requests as req_lib_po
import time as time_po

PO_TOKEN_URL = "http://localhost:4416/get_pot"
_po_token_cache = {}

def get_po_token(data_sync_id: str) -> str:
    client_id = data_sync_id.split("||")[0] if "||" in data_sync_id else data_sync_id
    cached = _po_token_cache.get(client_id)
    if cached and cached["expires_at"] > time_po.time():
        return cached["token"]
    try:
        resp = req_lib_po.post(PO_TOKEN_URL, json={"content_binding": {"client_id": client_id}}, timeout=10)
        data = resp.json()
        token = data.get("poToken", "")
        if token:
            _po_token_cache[client_id] = {"token": token, "expires_at": time_po.time() + 11*3600}
            print(f"[PO Token] Получен: {token[:20]}...")
            return token
    except Exception as e:
        print(f"[PO Token] Ошибка: {e}")
    return ""



from master.cdp_client import CDPMasterClient
from session.playback import LightweightPlaybackSession
from utils.fingerprint import SessionFingerprint


class PlaybackManager:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        self.master = CDPMasterClient(self.config["master"]["cdp_port"])
        self.sessions: list[LightweightPlaybackSession] = []
        self.urls: list[str] = []
        self.running = False

    async def load_urls(self):
        urls_file = Path("urls.txt")
        if urls_file.exists():
            self.urls = [line.strip() for line in urls_file.read_text().splitlines() if line.strip()]
        print(f"[Manager] Загружено {len(self.urls)} URL")

    async def start(self):
        await self.load_urls()
        if not self.urls:
            print("[Manager] Файл urls.txt пуст.")
            return
        await self.master.connect()
        await self.master.refresh_session_data()

        # Получаем PO Token
        data_sync_id = self.config.get("data_sync_id", "101149169407488805793||")
        po_token = get_po_token(data_sync_id)
        print(f"[Manager] PO Token: {po_token[:20] if po_token else "не получен"}...")

        max_sessions = self.config["playback"]["max_sessions"]
        for i in range(max_sessions):
            fp = SessionFingerprint()
            session = LightweightPlaybackSession(
                session_id=i, master_data=self.master.session_data, fingerprint=fp, po_token=po_token)
            self.sessions.append(session)
        print(f"[Manager] Создано {len(self.sessions)} сессий")
        print(f"[Manager] RAM: ~{len(self.sessions) * 34} МБ")
        self.running = True
        await self._run_loop()

    async def _run_loop(self):
        url_index = 0
        error_window = []  # последние 20 результатов
        semaphore = asyncio.Semaphore(10)  # макс параллельных yt-dlp запросов
        while self.running:
            if url_index % 10 == 0:
                await self.master.refresh_session_data()
                for s in self.sessions:
                    s.master = self.master.session_data
            session = self.sessions[url_index % len(self.sessions)]
            url = self.urls[url_index % len(self.urls)]
            print(f"[Session {session.id}] ▶ {url[:60]}...")
            async with semaphore:
                success = await session.init_media(url)
            if success:
                error_window.append(0)
                await session.playback_loop()
            else:
                error_window.append(1)
                # Auto-scale: при >30% ошибок делаем паузу
                if len(error_window) >= 10:
                    error_rate = sum(error_window[-10:]) / 10
                    if error_rate > 0.3:
                        wait = min(30, error_rate * 60)
                        print(f"[AutoScale] Error rate {error_rate:.0%} — пауза {wait:.0f}с")
                        await asyncio.sleep(wait)
                    error_window = error_window[-20:]
                else:
                    await asyncio.sleep(5)
            url_index += 1
            if url_index % 100 == 0:
                total_plays = sum(s.session_plays for s in self.sessions)
                total_errors = sum(s.errors for s in self.sessions)
                print(f"[Stats] Plays: {total_plays}, Errors: {total_errors}")

    async def stop(self):
        self.running = False
        for s in self.sessions:
            await s.close()
        await self.master.close()
        print("[Manager] Остановлен")


async def main():
    manager = PlaybackManager()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(manager.stop()))
    await manager.start()


if __name__ == "__main__":
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ImportError:
        pass
    asyncio.run(main())
