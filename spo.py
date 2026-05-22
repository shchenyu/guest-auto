import time
import json
import os
import re
import requests
from datetime import datetime, timedelta

# Selenium & BS4 Imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# ================= CONFIGURATION (Updated for GitHub) =================
PROG_URL = "https://sportsonline.vc/prog.txt"
SAVE_DIR = "output"
SAVE_FILE = os.path.join(SAVE_DIR, "spo-b.txt")

HEADER_IMAGE = "https://img2.pic.in.th/Gemini_Generated_Image_6jd8dr6jd8dr6jd8-1.md.png"
GROUP_IMAGE = "https://img5.pic.in.th/file/secure-sv1/ChatGPT-Image-8-..-2569-16_53_16.md.png"
DEFAULT_MATCH_IMAGE = "https://img5.pic.in.th/file/secure-sv1/ChatGPT-Image-8-..-2569-16_53_16.md.png"

besoccer_db = {}

# Keyword กีฬาอื่นๆ
OTHER_SPORTS_KEYWORDS = {
    "Tennis": "Tennis", "ATP": "Tennis", "WTA": "Tennis",
    "NBA": "Basketball", "Basketball": "Basketball",
    "Formula 1": "F1", "F1": "F1",
    "MotoGP": "MotoGP", "UFC": "UFC",
    "Boxing": "Boxing", "NFL": "NFL",
    "Snooker": "Snooker", "Badminton": "Badminton", "Volleyball": "Volleyball"
}

DAY_NAME_MAP = {
    "MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3, 
    "FRIDAY": 4, "SATURDAY": 5, "SUNDAY": 6
}

# ================= HELPER FUNCTIONS =================

def setup_driver():
    options = Options()
    # เพิ่ม Page Load Strategy เป็น eager เพื่อให้บอทโหลดเว็บเร็วขึ้นโดยไม่ต้องรอโหลดรูป/CSS ครบ
    options.page_load_strategy = 'eager' 
    options.add_argument("--headless=new") # ต้องเป็น headless เสมอเมื่อรันบน GitHub
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def get_base_date_from_dayname(day_name_str):
    # ปรับเวลาเป็นไทยก่อนคำนวณหาวัน
    today = datetime.utcnow() + timedelta(hours=7)
    # หาวันจันทร์ของสัปดาห์นี้เป็นจุดอ้างอิง
    start_of_week = today - timedelta(days=today.weekday()) 
    
    target_idx = DAY_NAME_MAP.get(day_name_str.upper())
    if target_idx is None: return None
    
    # คำนวณหาวันเป้าหมายในสัปดาห์ปัจจุบัน
    target_date = start_of_week + timedelta(days=target_idx)
    
    # [BUG FIXED]: ถ้าวันเป้าหมายผ่านไปแล้วมากกว่า 3 วัน (เช่น วันนี้วันศุกร์ แต่ตารางขึ้น MONDAY)
    # ให้ถือว่าเป็นวันของสัปดาห์หน้า เพื่อป้องกันการดึงตารางของสัปดาห์ที่แล้วมาแสดง
    if (target_date.date() - today.date()).days < -3:
        target_date += timedelta(days=7)
        
    return target_date

def extract_channel_name(url):
    try:
        filename = url.split('/')[-1]
        channel = filename.split('.')[0]
        return channel
    except:
        return ""

# ================= LOGIC หลัก =================

def process_and_fetch_dates(lines):
    dates_to_scrape = set()
    processed_matches = [] 
    current_utc_base_date = None
    last_utc_time_obj = None
    utc_days_offset = 0

    for line in lines:
        line = line.strip()
        if not line: continue
        
        if line.upper() in DAY_NAME_MAP:
            current_utc_base_date = get_base_date_from_dayname(line.upper())
            last_utc_time_obj = None 
            utc_days_offset = 0      
            continue

        m = re.match(r"(\d{2}:\d{2})\s+(.*?)\s+\|\s+(https?://\S+)", line)
        if m and current_utc_base_date:
            time_utc_str, title, url = m.groups()
            current_utc_time = datetime.strptime(time_utc_str, "%H:%M")
            
            if last_utc_time_obj:
                if current_utc_time < last_utc_time_obj:
                    if (last_utc_time_obj - current_utc_time).seconds / 3600 > 12:
                        utc_days_offset += 1
            last_utc_time_obj = current_utc_time

            match_date_utc = current_utc_base_date + timedelta(days=utc_days_offset)
            full_dt_utc = datetime.combine(match_date_utc.date(), current_utc_time.time())
            
            # แปลงเป็นเวลาไทย
            full_dt_thai = full_dt_utc + timedelta(hours=7)
            thai_date_str = full_dt_thai.strftime("%Y-%m-%d")
            dates_to_scrape.add(thai_date_str)

            processed_matches.append({
                "thai_datetime": full_dt_thai,
                "time_show": full_dt_thai.strftime("%H:%M"),
                "title": title,
                "url": url,
                "channel": extract_channel_name(url)
            })

    return sorted(list(dates_to_scrape)), processed_matches

def fetch_besoccer_data(date_list):
    if not date_list: return
    print(f"\n[STEP 2] เริ่มดึงข้อมูลจาก BeSoccer...")
    driver = setup_driver()
    try:
        for date_str in date_list:
            url = f"https://www.besoccer.com/livescore/{date_str}"
            try:
                driver.get(url)
                
                # กดปุ่มยอมรับ Cookie (ถ้ามี)
                try:
                    agree_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "accept-btn")))
                    agree_btn.click()
                except: pass

                # ปรับจากการใช้ time.sleep(5) เป็นการรอให้โหลดข้อมูลแมตช์สำเร็จ (ประหยัดเวลาและชัวร์กว่า)
                try:
                    # เพิ่มเวลาจาก 15 เป็น 25 วินาทีเผื่อ GitHub Actions ประมวลผลช้า
                    WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".match-link")))
                except Exception as e:
                    print(f"  - [WARNING] ไม่พบข้อมูลแมตช์สำหรับวันที่ {date_str} หรือโหลดช้าเกินไป")
                    print(f"  - [DEBUG] ตรวจสอบหน้าเว็บขณะ Error: {driver.title}") # ถ้าขึ้นว่า 'Just a moment...' แปลว่าโดนเว็บ BeSoccer บล็อกบอท
                    continue # ข้ามไปยังวันถัดไปหากไม่เจอข้อมูล

                soup = BeautifulSoup(driver.page_source, "html.parser")
                matches = soup.select(".match-link")
                for m in matches:
                    script_tag = m.select_one('script[type="application/ld+json"]')
                    if not script_tag: continue
                    try:
                        js_data = json.loads(script_tag.string)
                        league_name = js_data.get("location", {}).get("competitionName", "")
                        home_name = js_data["competitor"][0].get("name", "").strip().lower()
                        away_name = js_data["competitor"][1].get("name", "").strip().lower()
                        
                        home_img_tag = m.select_one(".team-info.ta-r img")
                        home_logo_url = DEFAULT_MATCH_IMAGE
                        if home_img_tag and home_img_tag.get('src'):
                            src = home_img_tag.get('src').split('?')[0]
                            if src.startswith("//"): src = "https:" + src
                            home_logo_url = src + "?size=120x&lossy=1"

                        match_info = {"league": league_name, "logo": home_logo_url}
                        besoccer_db[home_name] = match_info
                        besoccer_db[away_name] = match_info
                    except: continue
                    
            except Exception as e:
                print(f"  - [ERROR] เกิดข้อผิดพลาดในการดึงข้อมูลของวันที่ {date_str}: {e}")
                continue # หากมี error ในวันนั้นๆ ให้ข้ามไปทำวันถัดไปเลย ไม่ต้องหยุดโปรแกรมทั้งหมด
    finally:
        driver.quit()

def get_match_details(title):
    clean = title.replace(" x ", " vs ").replace("|", "")
    clean = re.sub(r'\d{2}:\d{2}', '', clean).strip()
    for k, v in OTHER_SPORTS_KEYWORDS.items():
        if k.lower() in clean.lower(): return v, DEFAULT_MATCH_IMAGE
    teams = clean.split(" vs ") if " vs " in clean else [clean]
    for t in teams:
        t = t.strip().lower()
        if len(t) < 3: continue
        if t in besoccer_db: return besoccer_db[t]["league"], besoccer_db[t]["logo"]
        for db_team, info in besoccer_db.items():
            if t in db_team or db_team in t: return info["league"], info["logo"]
    return "", DEFAULT_MATCH_IMAGE

def generate_json_final(processed_matches):
    groups_map = {}
    for item in processed_matches:
        thai_date_obj = item['thai_datetime'].date()
        date_key = thai_date_obj.strftime("%Y-%m-%d")
        if date_key not in groups_map:
            yy = str(thai_date_obj.year + 543)[-2:]
            group_name = f"วันที่ {thai_date_obj.day}/{thai_date_obj.month}/{yy}"
            groups_map[date_key] = {"name": group_name, "image": GROUP_IMAGE, "stations": []}
        
        league_name, team_logo = get_match_details(item['title'])
        channel_name = item['channel']
        info_text = f"{league_name}-{channel_name}" if league_name else channel_name
        display = f"{item['time_show']} {item['title']}"
        
        groups_map[date_key]["stations"].append({
            "name": display,
            "image": team_logo,
            "url": item['url'],
            "referer": "https://sportsonline.vc/",
            "info": info_text,
            "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0"
        })

    final_groups = [groups_map[k] for k in sorted(groups_map.keys())]
    now_th = datetime.utcnow() + timedelta(hours=7)
    today_str = now_th.strftime('%d/%m/%Y')
    
    output = {
        "name": f"ดู sportsonline.vc update @{today_str}", # [BUG FIXED] แก้พิมพ์ผิดจาก .cv เป็น .vc
        "author": f"Update@{today_str}",
        "info": f"sportsonline.vc Update@{today_str}", # [BUG FIXED] แก้พิมพ์ผิดจาก .cv เป็น .vc
        "image": HEADER_IMAGE,
        "groups": final_groups
    }
    
    os.makedirs(SAVE_DIR, exist_ok=True)
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    try:
        print("[STEP 1] กำลังดึงข้อมูลจากแหล่งหลัก...")
        r = requests.get(PROG_URL, timeout=15)
        r.raise_for_status() # ดักจับ HTTP Error (เช่น 404, 500)
        
        dates, matches = process_and_fetch_dates(r.text.splitlines())
        fetch_besoccer_data(dates)
        generate_json_final(matches)
        
        print(f"--- SUCCESS: บันทึกไฟล์สำเร็จแล้วที่ {SAVE_FILE} ---")
        
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] ไม่สามารถเชื่อมต่อเพื่อดาวน์โหลดข้อมูลหลักได้: {e}")
    except Exception as e:
        print(f"[ERROR] เกิดข้อผิดพลาดในระบบ: {e}")
