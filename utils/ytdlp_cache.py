"""
yt-dlp кэш с asyncio.Lock — один запрос на видео, TTL 2 часа.
"""
import asyncio
import time
import subprocess
from typing import Optional

_cache: dict = {}  # video_id -> {"url": str, "duration": int, "expires_at": float}
_lock = asyncio.Lock()
TTL = 2 * 3600  # 2 часа


async def get_audio_url(video_id: str) -> Optional[str]:
    async with _lock:
        cached = _cache.get(video_id)
        if cached and cached["expires_at"] > time.time():
            return cached["url"]

    loop = asyncio.get_event_loop()
    url = await loop.run_in_executor(None, _fetch_url, video_id)

    if url:
        async with _lock:
            if video_id not in _cache:
                _cache[video_id] = {}
            _cache[video_id]["url"] = url
            _cache[video_id]["expires_at"] = time.time() + TTL

    return url


async def get_duration(video_id: str) -> int:
    async with _lock:
        cached = _cache.get(video_id)
        if cached and "duration" in cached and cached["expires_at"] > time.time():
            return cached["duration"]

    loop = asyncio.get_event_loop()
    duration = await loop.run_in_executor(None, _fetch_duration, video_id)

    async with _lock:
        if video_id not in _cache:
            _cache[video_id] = {"expires_at": time.time() + TTL}
        _cache[video_id]["duration"] = duration

    return duration


def _fetch_url(video_id: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ['yt-dlp', '-f', 'bestaudio', '--get-url',
             f'https://www.youtube.com/watch?v={video_id}'],
            capture_output=True, text=True, timeout=15)
        url = result.stdout.strip()
        return url if url and 'googlevideo.com' in url else None
    except Exception:
        return None


def _fetch_duration(video_id: str) -> int:
    try:
        result = subprocess.run(
            ['yt-dlp', '--print', 'duration',
             f'https://www.youtube.com/watch?v={video_id}'],
            capture_output=True, text=True, timeout=10)
        dur = result.stdout.strip()
        return int(dur) * 1000 if dur and dur.isdigit() else 180000
    except Exception:
        return 180000
