"""
Лёгкий клиент с session_token и configInfo из реального браузера.
"""
import asyncio, time, random, subprocess, json, gzip
from typing import Optional
from dataclasses import dataclass
import aiohttp

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

class LightweightPlaybackSession:
    def __init__(self, session_id, master_data, fingerprint, api_base="https://www.youtube.com/youtubei/v1"):
        self.id = session_id
        self.master = master_data
        self.fp = fingerprint
        self.api_base = api_base
        self._http = create_tls_session()
        self._http.cookies.update(master_data.get("cookies",{}))
        self.state: Optional[PlaybackState] = None
        self.session_plays = 0
        self.errors = 0
        self._load_live_tokens()

    def _load_live_tokens(self):
        try:
            with open("/home/igor/playback-client/live_tokens.json") as f:
                tokens = json.load(f)
            self.session_token = tokens.get("session_token","")
            self.config_info = tokens.get("configInfo",{})
            self.user_agent = tokens.get("userAgent", self.fp.user_agent)
            self.client_version = tokens.get("clientVersion","2.20260506.01.00")
            self.client_name = tokens.get("clientName","1")
        except:
            self.session_token = ""
            self.config_info = {}
            self.user_agent = self.fp.user_agent
            self.client_version = "2.20260506.01.00"
            self.client_name = "1"

    def _get_audio_url(self, video_id: str) -> Optional[str]:
        try:
            result = subprocess.run(
                ['yt-dlp','-f','bestaudio','--get-url',f'https://www.youtube.com/watch?v={video_id}'],
                capture_output=True, text=True, timeout=15)
            url = result.stdout.strip()
            return url if url and 'googlevideo.com' in url else None
        except: return None

    def _get_duration(self, video_id: str) -> int:
        try:
            result = subprocess.run(
                ['yt-dlp','--print','duration',f'https://www.youtube.com/watch?v={video_id}'],
                capture_output=True, text=True, timeout=10)
            dur = result.stdout.strip()
            return int(dur)*1000 if dur and dur.isdigit() else 180000
        except: return 180000

    async def init_media(self, content_url: str) -> bool:
        content_id = self._extract_id(content_url)
        stream_url = self._get_audio_url(content_id)
        if not stream_url:
            self.errors += 1
            return False
        duration_ms = self._get_duration(content_id)
        self.state = PlaybackState(url=stream_url, content_id=content_id,
                                   duration_ms=duration_ms, started_at=time.time())
        return True

    async def playback_loop(self):
        if not self.state: return
        target_play_sec = get_smart_play_time()
        target_play_ms = min(target_play_sec*1000, self.state.duration_ms)
        chunk_size = 262144
        bytes_per_ms = 16000
        position = 0
        while position < target_play_ms:
            range_start = self.state.bytes_downloaded
            range_end = range_start + chunk_size - 1
            headers = {"Range": f"bytes={range_start}-{range_end}", "User-Agent": self.user_agent}
            try:
                resp = self._http.get(self.state.url, headers=headers)
                chunk = resp.content
                if not chunk: break
                self.state.bytes_downloaded += len(chunk)
                position += len(chunk)/bytes_per_ms
                self.state.position_ms = int(position)
            except:
                await asyncio.sleep(1)
                continue
            if self.state.position_ms - (self.state.ticks_sent*10000) >= 10000:
                await self._send_status_tick()
                self.state.ticks_sent += 1
            play_time = len(chunk)/bytes_per_ms/1000
            await asyncio.sleep(play_time*0.95)
        if self.state.position_ms/self.state.duration_ms >= 0.9:
            await self._send_completion_report()
        self.session_plays += 1

    async def _send_status_tick(self):
        if not self.state: return
        payload = {
            "context": {
                "client": {
                    "hl": "ru", "gl": "DE",
                    "clientName": int(self.client_name) if self.client_name.isdigit() else 1,
                    "clientVersion": self.client_version,
                    "configInfo": self.config_info,
                    "userAgent": self.user_agent,
                    "mainAppWebInfo": {"webDisplayMode": "WEB_DISPLAY_MODE_BROWSER"},
                    "memoryTotalKbytes": 8000000,
                    "connectionType": "CONN_CELLULAR_4G",
                }
            },
            "playbackTracking": {
                "contentId": self.state.content_id,
                "currentTime": self.state.position_ms/1000,
                "duration": self.state.duration_ms/1000,
                "playbackRate": 1.0, "playerState": "PLAYING",
            }
        }
        body = gzip.compress(json.dumps(payload).encode())
        try:
            self._http.post(f"{self.api_base}/log_event?alt=json&key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8",
                          data=body, headers={"Content-Type":"application/json","User-Agent":self.user_agent})
        except: pass

    async def _send_completion_report(self):
        if not self.state: return
        if self.state.position_ms/self.state.duration_ms < 0.9: return
        url = (f"https://www.youtube.com/api/stats/watchtime"
               f"?ns=yt&el=detailpage&cpn={self._random_cpn()}&ver=2"
               f"&cmt={self.state.position_ms/1000:.3f}&fmt=247&fs=0")
        try:
            self._http.post(url, data=f"session_token={self.session_token}",
                          headers={"User-Agent":self.user_agent})
        except: pass

    def _random_cpn(self):
        import string
        return ''.join(random.choices(string.ascii_letters+string.digits, k=16))

    @staticmethod
    def _extract_id(url: str) -> str:
        if "v=" in url: return url.split("v=")[1].split("&")[0]
        return url.split("/")[-1]

    async def close(self):
        if hasattr(self._http,'close'): self._http.close()
