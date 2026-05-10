import asyncio
import json
from playwright.async_api import async_playwright

TIDAL_ALBUM = "https://tidal.com/album/491391653"

async def main():
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        page = await browser.new_page()
        
        # Загружаем страницу альбома
        await page.goto(TIDAL_ALBUM, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)  # ждём прогрузки JS
        
        # Забираем все ссылки на треки
        track_elements = await page.query_selector_all('a[href*="/track/"]')
        
        tracks = set()
        for el in track_elements:
            href = await el.get_attribute("href")
            if href and "/track/" in href:
                track_id = href.split("/track/")[-1].split("?")[0]
                tracks.add(track_id)
        
        for tid in sorted(tracks):
            print(f"https://embed.tidal.com/tracks/{tid}?autoplay=1")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
