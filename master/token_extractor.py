import asyncio, aiohttp, json, gzip, time

async def extract_tokens(port=9222, timeout=90):
    async with aiohttp.ClientSession() as s:
        async with s.get(f"http://localhost:{port}/json") as resp:
            pages = await resp.json()
    ws = await aiohttp.ClientSession().ws_connect(pages[0]["webSocketDebuggerUrl"])
    await ws.send_json({"id":1,"method":"Network.enable"})
    await ws.receive_json()
    
    result = {"session_token": None, "configInfo": None}
    start = time.time()
    
    print("[Extractor] Жду 90 сек. Видео должно играть!\n")
    
    while time.time() - start < timeout:
        msg = await ws.receive_json()
        params = msg.get("params",{})
        req = params.get("request",{})
        url = req.get("url","")
        post_data = req.get("postData","")
        
        # Ловим session_token — в URL ИЛИ в теле запроса
        if not result["session_token"]:
            # В URL
            if "session_token=" in url:
                token = url.split("session_token=")[1].split("&")[0]
                result["session_token"] = token
                print(f"✅ session_token (URL): {token[:50]}...")
            # В теле запроса
            if post_data and "session_token=" in post_data:
                token = post_data.split("session_token=")[1].split("&")[0].split("\\")[0].rstrip("'")
                result["session_token"] = token
                print(f"✅ session_token (body): {token[:50]}...")
        
        # Ловим configInfo
        if post_data and "log_event" in url and not result["configInfo"]:
            raw = post_data.encode('latin-1') if isinstance(post_data, str) else post_data
            try:
                decoded = gzip.decompress(raw)
                data = json.loads(decoded)
                result["configInfo"] = data.get("context",{}).get("client",{}).get("configInfo",{})
                print(f"✅ configInfo: {len(result['configInfo'])} ключей")
            except:
                pass
        
        # Логируем URL с токеном
        if "youtube" in url and ("watchtime" in url or "qoe" in url) and "session_token" in (url + post_data):
            print(f"  🔑 Найден session_token в запросе!")
        
        if result["session_token"] and result["configInfo"]:
            break
    
    await ws.close()
    return result

if __name__ == "__main__":
    tokens = asyncio.run(extract_tokens())
    if tokens and tokens["session_token"] and tokens["configInfo"]:
        print(f"\n✅ ГОТОВО:")
        print(f"  session_token: {tokens['session_token'][:60]}...")
        print(f"  configInfo: {len(tokens['configInfo'])} ключей")
    else:
        print("\n❌ Не найдено. session_token:", bool(tokens and tokens["session_token"]))
