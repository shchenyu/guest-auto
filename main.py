import asyncio
import json
import re
import os
from datetime import datetime
from playwright.async_api import async_playwright


# ============================================================
# CONFIG
# ============================================================

W3U_FILE = "Hub.w3u"

TARGET_URL = "https://aisplay.ais.co.th/portal/live/?vid=59592e08bf6aee4e3ecce051"


# ============================================================
# GET NEW PARAMS FROM AIS PLAY
# ============================================================

async def get_new_params():
    print("[SNIFFER] Starting Headless Browser...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="th-TH",
        )

        page = await context.new_page()

        found_params = asyncio.get_running_loop().create_future()

        async def handle_request(request):
            url = request.url

            if ".m3u8" in url:
                print("[M3U8]", url[:300])

            if (
                ".m3u8" in url
                and "playbackUrlPrefix" in url
                and not found_params.done()
            ):
                if "?" in url:
                    params = url.split("?", 1)[1]
                    found_params.set_result(params)

        page.on("request", handle_request)

        try:
            print("[OPEN]", TARGET_URL)

            await page.goto(
                TARGET_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            await asyncio.sleep(3)

            click_selectors = [
                "button.login-type-btn.guest",
                "button.accept-btn",
                "text=เข้าชมแบบผู้เยี่ยมชม",
                "text=ผู้เยี่ยมชม",
                "text=ยอมรับ",
                "text=ตกลง",
                "text=Accept",
                "text=OK",
            ]

            for selector in click_selectors:
                try:
                    await page.click(selector, timeout=4000)
                    print(f"[CLICK] {selector}")
                    await asyncio.sleep(2)
                except Exception:
                    pass

            print("[WAIT] Waiting for m3u8 params...")

            try:
                params = await asyncio.wait_for(found_params, timeout=60)
                print("[SUCCESS] Found new params")
                return params

            except asyncio.TimeoutError:
                print("[ERROR] Not found m3u8 params")
                return None

        except Exception as e:
            print("[ERROR] Browser error:", str(e))
            return None

        finally:
            await browser.close()


# ============================================================
# LOAD JSON / W3U
# ============================================================

def load_json_with_fix(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # ลบ comma เกิน เช่น ,] หรือ ,}
    content = re.sub(r",(\s*[\]}])", r"\1", content)

    return json.loads(content)


# ============================================================
# UPDATE Hub.w3u
# ============================================================

def update_w3u(new_params):
    if not new_params:
        print("[SKIP] No params")
        return False

    if not os.path.exists(W3U_FILE):
        print(f"[ERROR] File not found: {W3U_FILE}")
        return False

    try:
        data = load_json_with_fix(W3U_FILE)
    except Exception as e:
        print("[ERROR] Cannot read JSON:", str(e))
        return False

    if isinstance(data, dict):
        stations = data.get("stations", [])
    elif isinstance(data, list):
        stations = data
    else:
        print("[ERROR] Unsupported W3U format")
        return False

    updated_count = 0

    for station in stations:
        if not isinstance(station, dict):
            continue

        old_url = station.get("url")

        if not old_url:
            continue

        if "playbackUrlPrefix=" in old_url:
            base_url = old_url.split("?", 1)[0]
            station["url"] = f"{base_url}?{new_params}"
            updated_count += 1

    if isinstance(data, dict):
        now = datetime.now()
        thai_year_short = (now.year + 543) % 100
        data["author"] = f" update {now.day}/{now.month}/{thai_year_short}"

    try:
        with open(W3U_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        print(f"[SUCCESS] Updated {updated_count} links")
        return updated_count > 0

    except Exception as e:
        print("[ERROR] Cannot write file:", str(e))
        return False


# ============================================================
# MAIN
# ============================================================

async def run():
    params = await get_new_params()

    if params:
        update_w3u(params)
    else:
        print("[FAILED] Cannot get new params")


if __name__ == "__main__":
    asyncio.run(run())
