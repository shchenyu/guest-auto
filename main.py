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
# GET NEW PARAMS
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
            timezone_id="Asia/Bangkok",
        )

        page = await context.new_page()
        found_params = asyncio.get_running_loop().create_future()

        async def handle_request(request):
            url = request.url
            lower_url = url.lower()

            keywords = [
                ".m3u8",
                ".mpd",
                "playback",
                "stream",
                "license",
                "widevine",
                "manifest",
                "media",
                "token",
                "cdn",
            ]

            if any(k in lower_url for k in keywords):
                print("[REQ]", url[:1000])

            # เงื่อนไขหลักแบบเดิม
            if (
                ".m3u8" in lower_url
                and "playbackurlprefix" in lower_url
                and not found_params.done()
            ):
                if "?" in url:
                    params = url.split("?", 1)[1]
                    print("[FOUND PARAMS BY playbackUrlPrefix]")
                    found_params.set_result(params)
                    return

            # เงื่อนไขสำรอง: เจอ m3u8 และมี query string
            if (
                ".m3u8" in lower_url
                and "?" in url
                and not found_params.done()
            ):
                params = url.split("?", 1)[1]
                print("[FOUND PARAMS BY m3u8]")
                found_params.set_result(params)
                return

        async def handle_response(response):
            url = response.url
            lower_url = url.lower()
            status = response.status

            keywords = [
                ".m3u8",
                ".mpd",
                "playback",
                "stream",
                "manifest",
            ]

            if any(k in lower_url for k in keywords):
                print("[RES]", status, url[:1000])

        page.on("request", handle_request)
        page.on("response", handle_response)

        try:
            print("[OPEN]", TARGET_URL)

            await page.goto(
                TARGET_URL,
                wait_until="domcontentloaded",
                timeout=90000,
            )

            await asyncio.sleep(5)

            try:
                await page.screenshot(path="debug-open.png", full_page=True)
                print("[DEBUG] Saved screenshot: debug-open.png")
            except Exception as e:
                print("[DEBUG] Cannot save debug-open.png:", str(e))

            # ปุ่มที่อาจต้องกด
            selectors = [
                "button.login-type-btn.guest",
                "button.accept-btn",
                "text=เข้าชมแบบผู้เยี่ยมชม",
                "text=ผู้เยี่ยมชม",
                "text=ยอมรับ",
                "text=ตกลง",
                "text=Accept",
                "text=OK",
                "button:has-text('Accept')",
                "button:has-text('ยอมรับ')",
                "button:has-text('ตกลง')",
                "button:has-text('ผู้เยี่ยมชม')",
            ]

            for selector in selectors:
                try:
                    await page.click(selector, timeout=5000)
                    print(f"[CLICK] {selector}")
                    await asyncio.sleep(3)
                except Exception:
                    pass

            try:
                await page.screenshot(path="debug-after-click.png", full_page=True)
                print("[DEBUG] Saved screenshot: debug-after-click.png")
            except Exception as e:
                print("[DEBUG] Cannot save debug-after-click.png:", str(e))

            # ลองกด play ถ้ามี
            play_selectors = [
                "button[aria-label='Play']",
                "button:has-text('Play')",
                ".vjs-big-play-button",
                ".jw-icon-playback",
                ".plyr__control--overlaid",
                "video",
            ]

            for selector in play_selectors:
                try:
                    await page.click(selector, timeout=5000)
                    print(f"[PLAY CLICK] {selector}")
                    await asyncio.sleep(5)
                except Exception:
                    pass

            # รอให้เว็บยิง request
            print("[WAIT] Waiting for m3u8 params...")

            try:
                params = await asyncio.wait_for(found_params, timeout=90)
                print("[SUCCESS] Found new params")
                return params

            except asyncio.TimeoutError:
                print("[ERROR] Not found m3u8 params")

                try:
                    await page.screenshot(path="debug-timeout.png", full_page=True)
                    print("[DEBUG] Saved screenshot: debug-timeout.png")
                except Exception as e:
                    print("[DEBUG] Cannot save debug-timeout.png:", str(e))

                return None

        except Exception as e:
            print("[ERROR] Browser error:", str(e))

            try:
                await page.screenshot(path="debug-timeout.png", full_page=True)
                print("[DEBUG] Saved screenshot: debug-timeout.png")
            except Exception:
                pass

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

        # อัปเดตเฉพาะลิงก์ที่เคยมี playbackUrlPrefix
        if "playbackUrlPrefix=" in old_url or "playbackurlprefix=" in old_url.lower():
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
