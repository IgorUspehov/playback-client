#!/usr/bin/env python3
import asyncio
import signal
from pathlib import Path

import yaml

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
        max_sessions = self.config["playback"]["max_sessions"]
        for i in range(max_sessions):
            fp = SessionFingerprint()
            session = LightweightPlaybackSession(
                session_id=i, master_data=self.master.session_data, fingerprint=fp)
            self.sessions.append(session)
        print(f"[Manager] Создано {len(self.sessions)} сессий")
        print(f"[Manager] RAM: ~{len(self.sessions) * 34} МБ")
        self.running = True
        await self._run_loop()

    async def _run_loop(self):
        url_index = 0
        while self.running:
            if url_index % 10 == 0:
                await self.master.refresh_session_data()
                for s in self.sessions:
                    s.master = self.master.session_data
            session = self.sessions[url_index % len(self.sessions)]
            url = self.urls[url_index % len(self.urls)]
            print(f"[Session {session.id}] ▶ {url[:60]}...")
            success = await session.init_media(url)
            if success:
                await session.playback_loop()
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
