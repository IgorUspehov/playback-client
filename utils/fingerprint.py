import random
import string
from dataclasses import dataclass, field


@dataclass
class SessionFingerprint:
    session_id: str = field(default_factory=lambda: ''.join(
        random.choices(string.ascii_lowercase + string.digits, k=12)
    ))
    canvas_hash: str = field(default_factory=lambda: hex(random.getrandbits(32)))
    webgl_vendor: str = "Google Inc. (Intel)"
    webgl_renderer: str = "ANGLE (Intel, Mesa Intel(R) Graphics (ADL GT2), OpenGL 4.6)"
    user_agent: str = ""
    platform: str = "Linux x86_64"
    language: str = "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    hardware_concurrency: int = 4
    device_memory: int = 4
    max_touch_points: int = 0
    viewport_width: int = 1920
    viewport_height: int = 1080
    screen_width: int = 1920
    screen_height: int = 1080
    color_depth: int = 24
    pixel_ratio: float = 1.0
    timezone: str = "Europe/Berlin"
    timezone_offset: int = -60
    audio_codecs: str = "opus,vorbis,aac,mp3"
    video_codecs: str = "avc1.640028,h264,av1,VP9"
    plugins: str = "Chrome PDF Plugin,Chrome PDF Viewer,Native Client"
    media_devices: str = "audioinput=1,audiooutput=1,videoinput=1"

    @staticmethod
    def generate_user_agent() -> str:
        chrome_builds = ["120.0.6099.129", "120.0.6099.109", "121.0.6167.85"]
        platform_variants = ["X11; Linux x86_64", "X11; Linux i686"]
        return (
            f"Mozilla/5.0 ({random.choice(platform_variants)}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{random.choice(chrome_builds)} Safari/537.36"
        )

    def __post_init__(self):
        if not self.user_agent:
            self.user_agent = self.generate_user_agent()
        if random.random() > 0.7:
            self.viewport_width = random.choice([1366, 1440, 1536, 1920])
            self.viewport_height = random.choice([768, 864, 900, 1080])
        self.screen_width = self.viewport_width
        self.screen_height = self.viewport_height

    def to_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept-Language": self.language,
            "Sec-CH-UA": '"Chromium";v="120", "Google Chrome";v="120", "Not.A/Brand";v="99"',
            "Sec-CH-UA-Platform": '"Linux"',
            "Sec-CH-UA-Mobile": "?0",
            "Viewport-Width": str(self.viewport_width),
        }
