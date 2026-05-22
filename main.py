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

# ใช้โดเมนนี้ให้ตรงกับ cookie ที่เจอใน DevTools
TARGET_URL = "https://aisplay.ais.th/portal/live/?vid=59592e08bf6aee4e3ecce051"


# ============================================================
# COOKIE HELPER
# ============================================================

def normalize_cookie(cookie):
    """
    ปรับรูปแบบ cookie ให้ Playwright ใช้ได้
    รองรับ cookie จาก Cookie-Editor / Chrome DevTools
    """
    item = {}

    item["name"] = cookie.get("name")
    item["value"] = cookie.get("value", "")

    domain = cookie.get("domain")
    if domain:
        item["domain"] = domain

    item["path"] = cookie.get("path", "/")

    expires = cookie.get("expirationDate", cookie.get("expires", None))
    if isinstance(expires, (int, float)) and expires > 0:
        item["expires"] = int(expires)

    item["httpOnly"] = bool(cookie.get("httpOnly", False))
    item["secure"] = bool(cookie.get("secure", True))

    same_site = cookie.get("sameSite")
    if same_site:
        same_site = str(same_site).lower()

        if same_site in ["no_restriction", "none"]:
            item["sameSite"] = "None"
        elif same_site in ["lax", "lax_mode"]:
            item["sameSite"] = "Lax"
        elif same_site in ["strict", "strict_mode"]:
            item["sameSite"] = "Strict"

    return item


async def load_ais_cookies(context):
    cookies_json = os.getenv("AIS_COOKIES_JSON", "").strip()

    if not cookies_json:
        print("[COOKIE] AIS_COOKIES_JSON not found")
        return False

    try:
        raw_cookies = json.loads(cookies_json)

        if isinstance(raw_cookies, dict):
            raw_cookies = [raw_cookies]

        cookies = []

        for c in raw_cookies:
            if not isinstance(c, dict):
                continue

            if not c.get("name"):
                continue

            domain = str(c.get("domain", "")).lower()

            # รับเฉพาะ cookie ที่เกี่ยวกับ AIS
            if "ais" not in domain:
                continue

            cookies.append(normalize_cookie(c))

        if not cookies:
            print("[COOKIE] No valid AIS cookies")
            return False

        await context.add_cookies(cookies)
        print(f"[COOKIE] Loaded {len(cookies)} AIS cookies")
        return True

    except Exception as e:
        print("[COOKIE ERROR]", str(e))
        return False


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
                "--autoplay-policy=no-user-gesture-required",
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
            java_script_enabled=True,
            ignore_https_errors=True,
        )

        await load_ais_cookies(context)

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
                "ais",
                "anevia",
                "vidnt",
            ]

            if any(k in lower_url for k in keywords):
                print("[REQ]", url[:1500])

            # เงื่อนไขหลัก: m3u8 + playbackUrlPrefix
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
                "license",
                "widevine",
                "ais",
                "anevia",
                "vidnt",
            ]

            if any(k in lower_url for k in keywords):
                print("[RES]", status, url[:1500])

        async def handle_request_failed(request):
            try:
                print("[REQ FAILED]", request.url[:1000], request.failure)
            except Exception:
                pass

        page.on("request", handle_request)
        page.on("response", handle_response)
        page.on("requestfailed", handle_request_failed)

        try:
            print("[OPEN]", TARGET_URL)

            await page.goto(
                TARGET_URL,
                wait_until="domcontentloaded",
                timeout=90000,
            )

            await asyncio.sleep(8)

            try:
                print("[PAGE URL]", page.url)
                print("[PAGE TITLE]", await page.title())

                body_text = await page.locator("body").inner_text(timeout=15000)
                body_text = re.sub(r"\s+", " ", body_text).strip()
                print("[PAGE TEXT]", body_text[:3000])
            except Exception as e:
                print("[DEBUG] Cannot read page text:", str(e))

            try:
                await page.screenshot(path="debug-open.png", full_page=True)
                print("[DEBUG] Saved screenshot: debug-open.png")
            except Exception as e:
                print("[DEBUG] Cannot save debug-open.png:", str(e))

            # ปุ่มที่อาจต้องกดหลัง cookie login แล้ว
            selectors = [
                "button.login-type-btn.guest",
                "button.accept-btn",
                "text=เข้าชมแบบผู้เยี่ยมชม",
                "text=ผู้เยี่ยมชม",
                "text=เข้าสู่ระบบภายหลัง",
                "text=ข้าม",
                "text=ยอมรับ",
                "text=ตกลง",
                "text=Accept",
                "text=OK",
                "button:has-text('Accept')",
                "button:has-text('ยอมรับ')",
                "button:has-text('ตกลง')",
                "button:has-text('ผู้เยี่ยมชม')",
                "button:has-text('ข้าม')",
            ]

            for selector in selectors:
                try:
                    count = await page.locator(selector).count()
                    if count > 0:
                        await page.locator(selector).first().click(
                            timeout=5000,
                            force=True,
                        )
                        print(f"[CLICK] {selector}")
                        await asyncio.sleep(4)
                except Exception:
                    pass

            try:
                await page.screenshot(path="debug-after-cookie.png", full_page=True)
                print("[DEBUG] Saved screenshot: debug-after-cookie.png")
            except Exception as e:
                print("[DEBUG] Cannot save debug-after-cookie.png:", str(e))

            try:
                print("[AFTER CLICK URL]", page.url)
                print("[AFTER CLICK TITLE]", await page.title())

                body_text = await page.locator("body").inner_text(timeout=15000)
                body_text = re.sub(r"\s+", " ", body_text).strip()
                print("[AFTER CLICK TEXT]", body_text[:3000])
            except Exception as e:
                print("[DEBUG] Cannot read after-click text:", str(e))

            # กดปุ่ม play
            play_selectors = [
                "button[aria-label='Play']",
                "button:has-text('Play')",
                ".vjs-big-play-button",
                ".jw-icon-playback",
                ".plyr__control--overlaid",
                ".video-js",
                "video",
            ]

            for selector in play_selectors:
                try:
                    count = await page.locator(selector).count()
                    if count > 0:
                        await page.locator(selector).first().click(
                            timeout=5000,
                            force=True,
                        )
                        print(f"[PLAY CLICK] {selector}")
                        await asyncio.sleep(6)
                except Exception:
                    pass

            # สั่ง video.play() ผ่าน JavaScript
            try:
                await page.evaluate(
                    """
                    () => {
                        const videos = Array.from(document.querySelectorAll('video'));
                        for (const v of videos) {
                            try {
                                v.muted = true;
                                v.play();
                            } catch (e) {}
                        }
                    }
                    """
                )
                print("[JS] Tried video.play()")
                await asyncio.sleep(8)
            except Exception as e:
                print("[JS] video.play failed:", str(e))

            try:
                await page.screenshot(path="debug-after-click.png", full_page=True)
                print("[DEBUG] Saved screenshot: debug-after-click.png")
            except Exception as e:
                print("[DEBUG] Cannot save debug-after-click.png:", str(e))

            print("[WAIT] Waiting for m3u8 params...")

            try:
                params = await asyncio.wait_for(found_params, timeout=90)
                print("[SUCCESS] Found new params")
                return params

            except asyncio.TimeoutError:
                print("[ERROR] Not found m3u8 params")

                try:
                    print("[TIMEOUT URL]", page.url)
                    print("[TIMEOUT TITLE]", await page.title())

                    body_text = await page.locator("body").inner_text(timeout=15000)
                    body_text = re.sub(r"\s+", " ", body_text).strip()
                    print("[TIMEOUT TEXT]", body_text[:3000])
                except Exception as e:
                    print("[DEBUG] Cannot read timeout page text:", str(e))

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

        if "playbackurlprefix=" in old_url.lower():
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
