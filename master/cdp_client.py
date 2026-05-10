"""
Клиент для извлечения сессионных данных через Chrome DevTools Protocol.
"""
import asyncio
import json
from typing import Optional
import aiohttp


class CDPMasterClient:
    def __init__(self, port: int = 9222):
        self.port = port
        self.ws_url: Optional[str] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session_data: dict = {}

    async def connect(self):
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://localhost:{self.port}/json") as resp:
                pages = await resp.json()
        if not pages:
            raise RuntimeError("Нет активных страниц в Chrome")
        self.ws_url = pages[0]["webSocketDebuggerUrl"]
        self.ws = await aiohttp.ClientSession().ws_connect(self.ws_url)
        await self.ws.send_json({"id": 1, "method": "Runtime.enable"})
        await self._wait_for_response(1)
        await self.ws.send_json({"id": 2, "method": "Network.enable"})
        await self._wait_for_response(2)
        print(f"[CDP] Подключён к {pages[0]['url']}")

    async def _wait_for_response(self, request_id: int):
        while True:
            msg = await self.ws.receive_json()
            if msg.get("id") == request_id:
                return msg

    async def extract_cookies(self) -> dict[str, str]:
        await self.ws.send_json({"id": 10, "method": "Network.getCookies"})
        response = await self._wait_for_response(10)
        cookies = response.get("result", {}).get("cookies", [])
        return {c["name"]: c["value"] for c in cookies}

    async def extract_headers(self) -> dict[str, str]:
        """Извлечение токенов и заголовков из ytcfg."""
        await self.ws.send_json({
            "id": 11,
            "method": "Runtime.evaluate",
            "params": {
                "expression": """
                JSON.stringify({
                    xsrf: window.ytcfg?.data_?.XSRF_TOKEN || '',
                    api_key: window.ytcfg?.data_?.INNERTUBE_API_KEY || '',
                    visitor: window.ytcfg?.data_?.VISITOR_DATA || '',
                    clientVersion: window.ytcfg?.data_?.INNERTUBE_CONTEXT_CLIENT_VERSION || '',
                    clientName: window.ytcfg?.data_?.INNERTUBE_CLIENT_NAME || 'WEB',
                    logged_in: window.ytcfg?.data_?.LOGGED_IN || false,
                    hl: window.ytcfg?.data_?.HL || 'ru',
                    gl: window.ytcfg?.data_?.GL || 'DE',
                })
                """,
                "returnByValue": True
            }
        })
        response = await self._wait_for_response(11)
        result = json.loads(response["result"]["result"]["value"])
        return result

    async def refresh_session_data(self):
        cookies = await self.extract_cookies()
        headers = await self.extract_headers()
        self._session_data = {
            "cookies": cookies,
            "xsrf_token": headers.get("xsrf", ""),
            "api_key": headers.get("api_key", ""),
            "visitor_data": headers.get("visitor", ""),
            "client_version": headers.get("clientVersion", "2.20260506.01.00"),
            "client_name": headers.get("clientName", "WEB"),
            "logged_in": headers.get("logged_in", False),
            "hl": headers.get("hl", "ru"),
            "gl": headers.get("gl", "DE"),
            "headers": {
                "X-YouTube-Client-Name": "1",
                "X-YouTube-Client-Version": headers.get("clientVersion", "2.20260506.01.00"),
                "Origin": "https://www.youtube.com",
                "Referer": "https://www.youtube.com/",
            }
        }
        print(f"[CDP] Данные обновлены: {len(self._session_data['cookies'])} cookies | logged_in={self._session_data['logged_in']}")

    @property
    def session_data(self) -> dict:
        return self._session_data.copy()

    async def close(self):
        if self.ws:
            await self.ws.close()
