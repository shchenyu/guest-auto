import asyncio
import json
import re
import os
from datetime import datetime
from playwright.async_api import async_playwright

# --- ตั้งค่า Path สำหรับ GitHub (ใช้ชื่อไฟล์ตรงๆ) ---
W3U_FILE = "MOM.w3u"
TARGET_URL = "https://aisplay.ais.co.th/portal/live/?vid=59592e08bf6aee4e3ecce051"

async def get_new_params():
    print("[SNIFFER] Starting Headless Browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) # GitHub บังคับ True
        context = await browser.new_context()
        page = await context.new_page()
        found_params = asyncio.Future()

        async def handle_request(request):
            url = request.url
            if ".m3u8" in url and "playbackUrlPrefix" in url and not found_params.done():
                if "?" in url:
                    params = url.split("?", 1)[1]
                    found_params.set_result(params)

        page.on("request", handle_request)
        try:
            await page.goto(TARGET_URL, wait_until='commit', timeout=60000)
            try: await page.click("button.login-type-btn.guest", timeout=5000)
            except: pass
            try: await page.click("button.accept-btn", timeout=5000)
            except: pass
            await asyncio.sleep(25)
        except: pass

        try:
            return await asyncio.wait_for(found_params, timeout=45)
        except:
            return None
        finally:
            await browser.close()

def update_w3u(new_params):
    if not new_params or not os.path.exists(W3U_FILE):
        return

    with open(W3U_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Fix trailing commas
    content = re.sub(r',(\s*[\]}])', r'\1', content)
    data = json.loads(content)

    # Update Links
    stations = data.get("stations", data if isinstance(data, list) else [])
    for s in stations:
        if "url" in s and "playbackUrlPrefix=" in s["url"]:
            base = s["url"].split("?")[0]
            s["url"] = f"{base}?{new_params}"

    # Update Date (BE 2569 format)
    now = datetime.now()
    thai_year = (now.year + 543) % 100
    data["author"] = f" update {now.day}/{now.month}/{thai_year}"

    with open(W3U_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"[SUCCESS] Updated at {now.strftime('%H:%M:%S')}")

async def run():
    params = await get_new_params()
    if params:
        update_w3u(params)

if __name__ == "__main__":

    asyncio.run(run())
