import asyncio
import time
import random
from typing import Optional
from dataclasses import dataclass

from utils.fingerprint import SessionFingerprint
from utils.tls import create_tls_session


@dataclass
class PlaybackState:
    url: str
    content_id: str
    duration_ms: int = 0
    bytes_downloaded: int = 0
    position_ms: int = 0
    started_at: float = 0.0
    ticks_sent: int = 0


class LightweightPlaybackSession:
    def __init__(self, session_id: int, master_data: dict, fingerprint: SessionFingerprint,
                 api_base: str = "https://www.youtube.com/youtubei/v1", po_token: str = ""):
        self.id = session_id
        self.master = master_data
        self.po_token = po_token
        self.fp = fingerprint
        self.api_base = api_base
        self._http = create_tls_session()
        self._http.cookies.update(master_data["cookies"])
        self.state: Optional[PlaybackState] = None
        self.session_plays: int = 0
        self.errors: int = 0

    async def _get_audio_url_cached(self, video_id: str):
        from utils.ytdlp_cache import get_audio_url
        return await get_audio_url(video_id)

    async def _get_duration_cached(self, video_id: str) -> int:
        from utils.ytdlp_cache import get_duration
        return await get_duration(video_id)

    async def init_media(self, content_url: str) -> bool:
        content_id = self._extract_id(content_url)
        stream_url = await self._get_audio_url_cached(content_id)
        if not stream_url:
            self.errors += 1
            return False
        if self.po_token and 'googlevideo.com' in stream_url:
            sep = '&' if '?' in stream_url else '?'
            stream_url = f"{stream_url}{sep}pot={self.po_token}"
        duration_ms = await self._get_duration_cached(content_id)
        self.state = PlaybackState(url=stream_url, content_id=content_id,
                                   duration_ms=duration_ms, started_at=time.time())
        return True

    async def init_media_OLD(self, content_url: str) -> bool:
        content_id = self._extract_id(content_url)
        payload = {
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": self.master["headers"]["X-YouTube-Client-Version"],
                    "visitorData": self.master["visitor_data"],
                    "hl": "de",
                    "gl": "DE",
                    "utcOffsetMinutes": self.fp.timezone_offset,
                    "userAgent": self.fp.user_agent,
                    "browserName": "Chrome",
                    "browserVersion": self.fp.user_agent.split("Chrome/")[1].split()[0],
                    "screenWidthPoints": self.fp.screen_width,
                    "screenHeightPoints": self.fp.screen_height,
                    "timeZone": self.fp.timezone,
                }
            },
            "contentId": content_id,
            "params": "8AEB"
        }
        headers = {
            **self.master["headers"],
            **self.fp.to_headers(),
            "Content-Type": "application/json",
        }
        try:
            resp = self._http.post(f"{self.api_base}/player", json=payload, headers=headers)
            if resp.status_code != 200:
                self.errors += 1
                return False
            data = resp.json()
            formats = data.get("streamingData", {}).get("formats", [])
            adaptive = data.get("streamingData", {}).get("adaptiveFormats", [])
            all_formats = formats + adaptive
            if not all_formats:
                return False
            stream_url = all_formats[0]["url"]
            duration_ms = int(data.get("videoDetails", {}).get("lengthSeconds", "180")) * 1000
            self.state = PlaybackState(
                url=stream_url, content_id=content_id,
                duration_ms=duration_ms, started_at=time.time()
            )
            return True
        except Exception:
            self.errors += 1
            return False

    async def playback_loop(self):
        if not self.state:
            return
        import random
        def get_smart_play_time():
            scenario = random.choice([1,2,3])
            chance = random.random()*100
            if scenario==1:
                if chance<=20: return random.randint(65,75)
                elif chance<=50: return random.randint(75,90)
                else: return random.randint(90,150)
            elif scenario==2:
                if chance<=50: return random.randint(90,130)
                else: return random.randint(110,130)
            else:
                if chance<=50: return random.randint(90,120)
                else: return random.randint(100,210)
        target_ms = min(get_smart_play_time()*1000, self.state.duration_ms)
        chunk_size = 262144
        position = 0
        while position < target_ms:
            range_start = self.state.bytes_downloaded
            range_end = range_start + chunk_size - 1
            headers = {"Range": f"bytes={range_start}-{range_end}", "User-Agent": self.fp.user_agent}
            try:
                resp = self._http.get(self.state.url, headers=headers)
                chunk = resp.content
                if not chunk:
                    break
                self.state.bytes_downloaded += len(chunk)
                bytes_per_ms = 16000
                position += len(chunk) / bytes_per_ms
                self.state.position_ms = int(position)
            except Exception:
                await asyncio.sleep(1)
                continue
            if self.state.position_ms - (self.state.ticks_sent * 10000) >= 10000:
                await self._send_status_tick()
                self.state.ticks_sent += 1
            play_time = len(chunk) / bytes_per_ms / 1000
            await asyncio.sleep(play_time * 0.95)
        await self._send_completion_report()
        self.session_plays += 1

    async def _send_status_tick(self):
        if not self.state:
            return
        payload = {
            "context": {"client": {"clientName": "WEB",
                "clientVersion": self.master["headers"]["X-YouTube-Client-Version"]}},
            "playbackTracking": {
                "contentId": self.state.content_id,
                "currentTime": self.state.position_ms / 1000,
                "duration": self.state.duration_ms / 1000,
                "playbackRate": 1.0,
                "playerState": "PLAYING",
            }
        }
        try:
            self._http.post(f"{self.api_base}/log_event", json=payload,
                          headers={**self.master["headers"], **self.fp.to_headers(),
                                   "Content-Type": "application/json"})
        except Exception:
            pass

    async def _send_completion_report(self):
        if not self.state:
            return
        ratio = self.state.position_ms / self.state.duration_ms
        if ratio < 0.9:
            return
        payload = {
            "contentId": self.state.content_id,
            "watchTime": self.state.position_ms / 1000,
            "duration": self.state.duration_ms / 1000,
            "completion": ratio,
        }
        try:
            self._http.post(
                f"{self.api_base.replace('/youtubei/v1', '')}/api/stats/watchtime",
                json=payload,
                headers={**self.master["headers"], **self.fp.to_headers(),
                         "Content-Type": "application/json"})
        except Exception:
            pass

    @staticmethod
    def _extract_id(url: str) -> str:
        if "v=" in url:
            return url.split("v=")[1].split("&")[0]
        elif "/shorts/" in url:
            return url.split("/shorts/")[1].split("?")[0]
        return url.split("/")[-1]

    async def close(self):
        if hasattr(self._http, 'close'):
            self._http.close()
