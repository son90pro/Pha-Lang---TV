import json
import re
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Danh sách API dự phòng chống bị GitHub Actions IP chặn
API_DOMAINS = [
    "https://api.plapi202624081158.com",
    "https://api.phalang.tv",
    "https://api.phalang1.tv",
    "https://api.phalang.net",
    "https://api.phalang.live"
]

OUTPUT_FILE = "phalang.m3u"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://phalang1.tv/",
    "Origin": "https://phalang1.tv"
}

SPORT_MAPPING = {
    "FOOTBALL": "⚽", "BONG DA": "⚽", "SOCCER": "⚽",
    "VOLLEYBALL": "🏐", "BONG CHUYEN": "🏐",
    "BASKETBALL": "🏀", "BONG RO": "🏀",
    "TENNIS": "🎾", "BADMINTON": "🏸", "CAU LONG": "🏸",
    "TABLE TENNIS": "🏓", "BONG BAN": "🏓",
    "BILLIARDS": "🎱", "POOL": "🎱", "ESPORTS": "🎮"
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
    """Lấy tên BLV từ các trường trong JSON hoặc từ tiêu đề/mô tả"""
    for src in [detail, item]:
        if not isinstance(src, dict):
            continue
        # 1. Kiểm tra các key thông dụng
        for k in ["blv", "blv_name", "commentator", "caster", "streamer", "author", "nickname"]:
            val = src.get(k)
            if isinstance(val, str) and val.strip():
                return val.strip()
            elif isinstance(val, dict):
                n = val.get("name") or val.get("nickname") or val.get("title")
                if n and str(n).strip():
                    return str(n).strip()
            elif isinstance(val, list) and len(val) > 0:
                first = val[0]
                if isinstance(first, str) and first.strip():
                    return first.strip()
                elif isinstance(first, dict):
                    n = first.get("name") or first.get("nickname")
                    if n and str(n).strip():
                        return str(n).strip()

    # 2. Quét trong tiêu đề/mô tả dạng (LÝ ...)
    full_text = f"{item.get('title', '')} {detail.get('title', '')} {item.get('desc', '')} {detail.get('desc', '')} {item.get('name', '')}"
    
    match = re.search(r'\((LÝ\s+[^)]+)\)', full_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    match_any = re.search(r'\(([^)]+)\)', full_text)
    if match_any:
        candidate = match_any.group(1).strip()
        if not re.search(r'^(HD|FHD|LIVE|U21|U23|NỮ|NAM|GEO)$', candidate, re.IGNORECASE):
            return candidate

    return ""

def extract_m3u8_urls(obj):
    """Trích xuất URL m3u8 hoặc dựng link từ Stream ID"""
    if not obj:
        return []
    json_str = json.dumps(obj, ensure_ascii=False)
    
    clean_urls = []
    urls = re.findall(r'(?:https?:)?//[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*', json_str)
    for u in urls:
        clean_u = u.strip().rstrip('",;')
        if clean_u.startswith("//"):
            clean_u = "https:" + clean_u
        if clean_u not in clean_urls:
            clean_urls.append(clean_u)
            
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
        print(f"Thử tải dữ liệu từ API: {base_api}", flush=True)
        # Thử POST /matches/graph
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
                    print(f" -> Lấy thành công {len(matches)} trận từ POST", flush=True)
                    break
        except Exception as e:
            print(f" -> POST lỗi: {e}", flush=True)

        # Thử GET /matches nếu POST thất bại
        try:
            res = session.get(f"{base_api}/matches", timeout=8, verify=False)
            if res.status_code == 200:
                res_data = res.json()
                data = res_data.get("data", []) if isinstance(res_data, dict) else res_data
                if isinstance(data, list) and len(data) > 0:
                    for item in data:
                        m_id = item.get("id")
                        if m_id and m_id not in seen_ids:
                            seen_ids.add(m_id)
                            item["_base_api"] = base_api
                            matches.append(item)
                    print(f" -> Lấy thành công {len(matches)} trận từ GET", flush=True)
                    break
        except Exception as e:
            print(f" -> GET lỗi: {e}", flush=True)

    def load_detail(item):
        m_id = item.get("id")
        base_api = item.get("_base_api", API_DOMAINS[0])
        try:
            res = session.get(f"{base_api}/matches/detail/{m_id}", timeout=6, verify=False)
            if res.status_code == 200:
                item["_detail"] = res.json()
        except Exception:
            pass

    if matches:
        print(f"Tải chi tiết cho {len(matches)} trận...", flush=True)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(load_detail, item) for item in matches]
            for future in as_completed(futures):
                future.result()

    return matches

def generate_m3u():
    matches = fetch_data()
    m3u_lines = ["#EXTM3U\n\n"]
    
    tz_vn = timezone(timedelta(hours=7))
    now_vn = datetime.now(tz_vn).replace(tzinfo=None)

    total_channels = 0

    for item in matches:
        detail = item.get("_detail") or {}

        # 1. CHỈ LỌC TRẬN CÓ BÌNH LUẬN VIÊN
        blv = get_blv_name(item, detail)
        if not blv:
            continue

        blv_clean = re.sub(r'[()]', '', blv).strip().upper()

        dt_vn = parse_to_vn_time(item.get("start_date") or detail.get("start_date"))
        time_str = dt_vn.strftime("%H:%M %d/%m") if dt_vn else "00:00 00/00"

        team1 = str(item.get("team_1") or detail.get("team_1") or "").strip()
        team2 = str(item.get("team_2") or detail.get("team_2") or "").strip()
        title_raw = str(item.get("title") or detail.get("title") or item.get("name") or "").strip()

        if team1 and team2:
            match_title = f"{team1} vs {team2}"
        elif title_raw:
            clean_title = re.sub(r'\s*\([^)]*\)', '', title_raw)
            match_title = clean_title.replace(" - ", " vs ").strip()
        else:
            match_title = "Trận đấu Phá Làng TV"

        desc = str(item.get("desc") or detail.get("desc") or "").strip()
        logo = str(item.get("team_1_logo") or detail.get("team_1_logo") or item.get("logo") or "").strip()
        icon = get_sport_icon(f"{desc} {match_title}")

        is_live = "🟢 " if (dt_vn and (dt_vn - timedelta(minutes=15)) <= now_vn <= (dt_vn + timedelta(minutes=150))) else ""

        urls = extract_m3u8_urls(detail) or extract_m3u8_urls(item)
        if not urls:
            continue

        streams = []
        for u in urls:
            streams.append((u, ""))
            if "pull.digitalcdn.net" in u:
                hd2_url = u.replace("pull.digitalcdn.net", "pull1.digitalcdn.net")
                streams.append((hd2_url, " (HD2)"))

        for url, tag in streams:
            display_title = f"{is_live}{time_str} {icon} {match_title} ({blv_clean}){tag} [geo]"

            entry = (
                f'#EXTINF:-1 tvg-logo="{logo}" group-title="Phá Làng TV" , {display_title}\n'
                f'#EXTVLCOPT:http-referrer=https://phalang.live/\n'
                f'{url}\n\n'
            )
            m3u_lines.append(entry)
            total_channels += 1

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(m3u_lines)

    print(f"Đã xuất thành công {total_channels} kênh vào file {OUTPUT_FILE}", flush=True)

if __name__ == "__main__":
    generate_m3u()
    
