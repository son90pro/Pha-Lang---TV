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
    "https://api.phalang.net",
    "https://api.phalang.live"
]

OUTPUT_FILE = "phalang.m3u"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Origin": "https://phalang1.tv",
    "Referer": "https://phalang1.tv/",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
}

SPORT_MAPPING = {
    "FOOTBALL": "⚽", "BONG DA": "⚽", "SOCCER": "⚽",
    "VOLLEYBALL": "🏐", "BONG CHUYEN": "🏐",
    "BASKETBALL": "🏀", "BONG RO": "🏀",
    "TENNIS": "🎾",
    "BADMINTON": "🏸", "CAU LONG": "🏸",
    "TABLE TENNIS": "🏓", "BONG BAN": "🏓",
    "BILLIARDS": "🎱", "POOL": "🎱",
    "ESPORTS": "🎮", "GAME": "🎮",
    "RACING": "🏎️", "F1": "🏎"
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

        val_str = str(date_val).strip()
        is_utc = "Z" in val_str or "+00" in val_str
        val_clean = val_str.replace("Z", "").replace("T", " ")
        if "." in val_clean:
            val_clean = val_clean.split(".")[0]

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(val_clean, fmt)
                if is_utc:
                    dt = dt + timedelta(hours=7)
                return dt
            except ValueError:
                pass
    except Exception:
        pass
    return None

def format_time_str(dt):
    return dt.strftime("%H:%M %d/%m") if dt else ""

def get_sport_icon(desc, title=""):
    text_check = f"{desc} {title}".upper()
    for key, icon in SPORT_MAPPING.items():
        if key in text_check:
            return icon
    return "⚽"

def extract_blv_name(obj):
    """Quét cực nhạy tên BLV từ JSON hoặc tiêu đề"""
    if not obj:
        return ""
    
    json_str = json.dumps(obj, ensure_ascii=False)
    
    # 1. Lọc theo dạng "(LÝ ...)"
    match = re.search(r'\((LÝ\s+[^)]+)\)', json_str, re.IGNORECASE)
    if match:
        return match.group(1).strip().upper()

    # 2. Tìm trong các key thông dụng
    if isinstance(obj, dict):
        for k in ["blv", "blv_name", "commentator", "caster", "streamer", "author", "nickname"]:
            val = obj.get(k)
            if isinstance(val, str) and val.strip():
                return val.strip().upper()
            elif isinstance(val, dict):
                name = val.get("name") or val.get("nickname") or val.get("title")
                if name and str(name).strip():
                    return str(name).strip().upper()
            elif isinstance(val, list) and len(val) > 0:
                first = val[0]
                if isinstance(first, str) and first.strip():
                    return first.strip().upper()
                elif isinstance(first, dict):
                    name = first.get("name") or first.get("nickname") or first.get("title")
                    if name and str(name).strip():
                        return str(name).strip().upper()

    return ""

def extract_stream_urls(obj):
    """Lấy danh sách URL phát sóng hoặc tự build từ Stream ID"""
    urls = []
    if not obj:
        return urls
    
    json_str = json.dumps(obj, ensure_ascii=False)
    
    # Quét URL m3u8 hoặc digitalcdn
    found_urls = re.findall(r'(?:https?:)?//[^\s"\'<>\\]*(?:digitalcdn\.net|\.m3u8)[^\s"\'<>\\]*', json_str)
    for u in found_urls:
        clean_u = u.strip().rstrip('",;')
        if clean_u.startswith("//"):
            clean_u = "https:" + clean_u
        if clean_u not in urls and not any(ext in clean_u.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp']):
            urls.append(clean_u)
            
    # Dự phòng: Bắt ID chuỗi live (32 ký tự hex)
    if not urls:
        stream_ids = re.findall(r'/live/([a-f0-9]{32})', json_str)
        for sid in set(stream_ids):
            urls.append(f"https://pull.digitalcdn.net/live/{sid}/index.m3u8")

    return urls

def fetch_matches():
    session = requests.Session()
    session.headers.update(HEADERS)
    
    all_matches = []
    seen_ids = set()

    for base_api in API_DOMAINS:
        # Thử POST trước
        url_post = f"{base_api}/matches/graph"
        payload = {"limit": 100, "page": 1, "order_asc": "start_date", "queries": [], "query_or": True}
        try:
            res = session.post(url_post, json=payload, timeout=8, verify=False)
            if res.status_code == 200:
                data = res.json().get("data", [])
                if isinstance(data, list) and len(data) > 0:
                    for item in data:
                        m_id = item.get("id")
                        if m_id and m_id not in seen_ids:
                            seen_ids.add(m_id)
                            item["_base_api"] = base_api
                            all_matches.append(item)
                    print(f"Lấy thành công {len(all_matches)} trận từ POST {base_api}", flush=True)
                    break
        except Exception:
            pass

        # Nếu POST lỗi, thử GET dự phòng
        url_get = f"{base_api}/matches"
        try:
            res = session.get(url_get, timeout=8, verify=False)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, dict):
                    data = data.get("data", [])
                if isinstance(data, list) and len(data) > 0:
                    for item in data:
                        m_id = item.get("id")
                        if m_id and m_id not in seen_ids:
                            seen_ids.add(m_id)
                            item["_base_api"] = base_api
                            all_matches.append(item)
                    print(f"Lấy thành công {len(all_matches)} trận từ GET {base_api}", flush=True)
                    break
        except Exception:
            pass

    # Lấy chi tiết song song cho từng trận
    def load_detail(item):
        m_id = item.get("id")
        base_api = item.get("_base_api", API_DOMAINS[0])
        url = f"{base_api}/matches/detail/{m_id}"
        try:
            res = session.get(url, timeout=6, verify=False)
            if res.status_code == 200:
                item["_detail"] = res.json()
        except Exception:
            pass

    if all_matches:
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(load_detail, item) for item in all_matches]
            for future in as_completed(futures):
                future.result()

    return all_matches

def build_m3u(matches):
    m3u_entries = ["#EXTM3U\n"]
    total_channels = 0

    tz_vn = timezone(timedelta(hours=7))
    now_vn = datetime.now(tz_vn).replace(tzinfo=None)

    for item in matches:
        if not isinstance(item, dict):
            continue

        detail_item = item.get("_detail") or {}
        combined_obj = {**item, **detail_item}

        # 1. Lọc trận CÓ BÌNH LUẬN VIÊN
        blv_name = extract_blv_name(combined_obj)
        if not blv_name:
            continue

        dt_vn = parse_to_vn_time(item.get("start_date") or detail_item.get("start_date"))
        
        # Chỉ lấy các trận trong khoảng 12h trước đến 48h tới
        if dt_vn:
            if dt_vn < (now_vn - timedelta(hours=12)) or dt_vn > (now_vn + timedelta(days=2)):
                continue

        formatted_time = format_time_str(dt_vn)

        team1 = str(item.get("team_1") or detail_item.get("team_1") or "").strip()
        team2 = str(item.get("team_2") or detail_item.get("team_2") or "").strip()
        title_raw = str(item.get("title") or detail_item.get("title") or item.get("name") or "").strip()

        if team1 and team2:
            match_name = f"{team1} vs {team2}"
        elif title_raw:
            clean_title = re.sub(r'\s*\([^)]*\)', '', title_raw)
            match_name = clean_title.replace(" - ", " vs ").strip()
        else:
            match_name = "Trận đấu Phá Làng TV"

        desc = str(item.get("desc") or detail_item.get("desc") or "").strip()
        logo = str(item.get("team_1_logo") or detail_item.get("team_1_logo") or item.get("logo") or "").strip()
        icon = get_sport_icon(desc, match_name)

        # Trận đang diễn ra gắn biểu tượng 🟢
        is_live = False
        if dt_vn and (dt_vn <= now_vn <= dt_vn + timedelta(minutes=150)):
            is_live = True
        live_prefix = "🟢 " if is_live else ""

        # Lấy danh sách URL luồng
        urls = extract_stream_urls(combined_obj)
        if not urls:
            continue

        # Tạo luồng Chuẩn & Luồng HD2
        stream_list = []
        for u in urls:
            stream_list.append({"url": u, "tag": ""})
            if "pull.digitalcdn.net" in u:
                hd2_url = u.replace("pull.digitalcdn.net", "pull1.digitalcdn.net")
                stream_list.append({"url": hd2_url, "tag": " (HD2)"})

        for st in stream_list:
            stream_url = st["url"]
            tag_hd = st["tag"]

            # Định dạng chính xác theo mẫu yêu cầu
            display_title = f"{live_prefix}{formatted_time} {icon} {match_name} ({blv_name}){tag_hd} [geo]"

            entry = (
                f'#EXTINF:-1 tvg-logo="{logo}" group-title="Phá Làng TV" , {display_title}\n'
                f'#EXTVLCOPT:http-referrer=https://phalang.live/\n'
                f'{stream_url}\n'
            )
            m3u_entries.append(entry)
            total_channels += 1

    return "\n".join(m3u_entries), total_channels

def main():
    print("=== Bắt đầu cào dữ liệu Phá Làng TV ===", flush=True)
    matches = fetch_matches()
    print(f"Tổng số trận thu thập được: {len(matches)}", flush=True)

    m3u_content, total_channels = build_m3u(matches)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"=== Xuất thành công {total_channels} luồng vào file {OUTPUT_FILE} ===", flush=True)

if __name__ == "__main__":
    main()
    
