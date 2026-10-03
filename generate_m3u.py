import json
import re
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_DOMAINS = [
    "https://api.plapi202624081158.com",
    "https://api.phalang.tv",
    "https://api.phalang1.tv",
    "https://api.phalang.net"
]

OUTPUT_FILE = "phalang.m3u"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Referer": "https://phalang1.tv/",
    "Origin": "https://phalang1.tv"
}

SPORT_MAPPING = {
    "FOOTBALL": "⚽", "BONG DA": "⚽", "SOCCER": "⚽",
    "VOLLEYBALL": "🏐", "BONG CHUYEN": "🏐",
    "BASKETBALL": "🏀", "BONG RO": "🏀",
    "TENNIS": "🎾", "BADMINTON": "🏸", "CAU LONG": "🏸"
}

def parse_to_vn_time(date_val):
    if not date_val:
        return None
    try:
        if isinstance(date_val, (int, float)) or (isinstance(date_val, str) and str(date_val).isdigit()):
            ts = float(date_val)
            if ts > 1e11:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=7))).replace(tzinfo=None)

        val_str = str(date_val).strip().replace("Z", "").replace("T", " ")
        if "." in val_str:
            val_str = val_str.split(".")[0]

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(val_str, fmt)
            except ValueError:
                pass
    except Exception:
        pass
    return None

def get_sport_icon(text):
    text_upper = str(text).upper()
    for key, icon in SPORT_MAPPING.items():
        if key in text_upper:
            return icon
    return "⚽"

def get_blv_name(item, detail):
    """Lấy tên BLV từ JSON hoặc từ chuỗi tiêu đề (LÝ ...)"""
    for src in [detail, item]:
        if not isinstance(src, dict):
            continue
        for k in ["blv", "blv_name", "commentator", "caster", "streamer"]:
            val = src.get(k)
            if isinstance(val, str) and val.strip():
                return val.strip()
            elif isinstance(val, dict):
                n = val.get("name") or val.get("nickname") or val.get("title")
                if n and str(n).strip():
                    return str(n).strip()

    # Quét thêm dạng (LÝ ...) trong tiêu đề / mô tả
    full_text = f"{item.get('title', '')} {detail.get('title', '')} {item.get('desc', '')} {detail.get('desc', '')}"
    match = re.search(r'\((LÝ\s+[^)]+)\)', full_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return ""

def extract_m3u8_urls(obj):
    """Trích xuất URL m3u8 từ JSON hoặc tự sinh từ ID live"""
    if not obj:
        return []
    json_str = json.dumps(obj, ensure_ascii=False)
    
    # 1. Quét URL .m3u8 trực tiếp
    urls = re.findall(r'(?:https?:)?//[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*', json_str)
    clean_urls = []
    for u in urls:
        clean_u = u.strip().rstrip('",;')
        if clean_u.startswith("//"):
            clean_u = "https:" + clean_u
        if clean_u not in clean_urls:
            clean_urls.append(clean_u)
            
    # 2. Nếu không tìm thấy URL m3u8, tìm ID 32 ký tự hex để dựng link
    if not clean_urls:
        stream_ids = re.findall(r'/live/([a-f0-9]{32})', json_str)
        for sid in set(stream_ids):
            clean_urls.append(f"https://pull.digitalcdn.net/live/{sid}/index.m3u8")

    return clean_urls

def fetch_data():
    session = requests.Session()
    session.headers.update(HEADERS)
    matches = []
    seen_ids = set()

    payload = {"limit": 100, "page": 1, "order_asc": "start_date", "queries": [], "query_or": True}

    for base_api in API_DOMAINS:
        try:
            res = session.post(f"{base_api}/matches/graph", json=payload, timeout=8, verify=False)
            if res.status_code == 200:
                data = res.json().get("data", [])
                if isinstance(data, list) and len(data) > 0:
                    for item in data:
                        m_id = item.get("id")
                        if m_id and m_id not in seen_ids:
                            seen_ids.add(m_id)
                            item["_base_api"] = base_api
                            matches.append(item)
                    break
        except Exception:
            continue

    def get_detail(item):
        m_id = item.get("id")
        base_api = item.get("_base_api", API_DOMAINS[0])
        try:
            res = session.get(f"{base_api}/matches/detail/{m_id}", timeout=6, verify=False)
            if res.status_code == 200:
                item["_detail"] = res.json()
        except Exception:
            pass

    if matches:
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(get_detail, item) for item in matches]
            for future in as_completed(futures):
                future.result()

    return matches

def generate_m3u():
    matches = fetch_data()
    m3u_lines = ["#EXTM3U\n"]
    
    tz_vn = timezone(timedelta(hours=7))
    now_vn = datetime.now(tz_vn).replace(tzinfo=None)

    total_channels = 0

    for item in matches:
        detail = item.get("_detail") or {}

        # 1. CHỈ LỌC CÁC TRẬN CÓ BLV
        blv = get_blv_name(item, detail)
        if not blv:
            continue

        dt_vn = parse_to_vn_time(item.get("start_date") or detail.get("start_date"))
        time_str = dt_vn.strftime("%H:%M %d/%m") if dt_vn else "00:00 00/00"

        team1 = str(item.get("team_1") or detail.get("team_1") or "").strip()
        team2 = str(item.get("team_2") or detail.get("team_2") or "").strip()
        title_raw = str(item.get("title") or detail.get("title") or item.get("name") or "").strip()

        if team1 and team2:
            match_title = f"{team1} vs {team2}"
        elif title_raw:
            match_title = re.sub(r'\s*\([^)]*\)', '', title_raw).replace(" - ", " vs ").strip()
        else:
            match_title = "Trận đấu Phá Làng TV"

        # Bỏ dấu ngoặc trùng trong tên BLV nếu có
        blv_clean = blv.replace("(", "").replace(")", "").strip()

        desc = str(item.get("desc") or detail.get("desc") or "").strip()
        logo = str(item.get("team_1_logo") or detail.get("team_1_logo") or item.get("logo") or "").strip()
        icon = get_sport_icon(f"{desc} {match_title}")

        # Gắn biểu tượng 🟢 nếu trận đang diễn ra
        is_live = "🟢 " if (dt_vn and dt_vn <= now_vn <= dt_vn + timedelta(minutes=150)) else ""

        # Lấy danh sách URL luồng
        urls = extract_m3u8_urls(detail) or extract_m3u8_urls(item)
        if not urls:
            continue

        # Nhân bản luồng chính & luồng HD2
        streams = []
        for u in urls:
            streams.append((u, ""))
            if "pull.digitalcdn.net" in u:
                hd2_url = u.replace("pull.digitalcdn.net", "pull1.digitalcdn.net")
                streams.append((hd2_url, " (HD2)"))

        for url, tag in streams:
            # Đúng chuẩn định dạng mẫu:
            # 🟢 07:00 03/10 🏐 Việt Nam vs Thái Lan (LÝ LIỀU LĨNH) [geo]
            # 🟢 07:00 03/10 🏐 Việt Nam vs Thái Lan (LÝ LIỀU LĨNH) (HD2) [geo]
            display_title = f"{is_live}{time_str} {icon} {match_title} ({blv_clean}){tag} [geo]"

            entry = (
                f'#EXTINF:-1 tvg-logo="{logo}" group-title="Phá Làng TV" , {display_title}\n'
                f'#EXTVLCOPT:http-referrer=https://phalang.live/\n'
                f'{url}\n'
            )
            m3u_lines.append(entry)
            total_channels += 1

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(m3u_lines)

    print(f"Đã xuất thành công {total_channels} kênh vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_m3u()
