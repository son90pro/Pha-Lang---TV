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
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
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

def get_blv_name(item, detail):
    """Lấy tên BLV từ chi tiết trận đấu"""
    for src in [detail, item]:
        if not isinstance(src, dict):
            continue
        for k in ["blv", "blv_name", "commentator", "caster", "streamer", "author"]:
            val = src.get(k)
            if isinstance(val, str) and val.strip():
                return val.strip()
            elif isinstance(val, dict):
                name = val.get("name") or val.get("nickname") or val.get("title")
                if name and str(name).strip():
                    return str(name).strip()
    return ""

def extract_urls(obj):
    """Tự động trích xuất các link m3u8 từ JSON"""
    urls = []
    if not obj:
        return urls
    json_str = json.dumps(obj, ensure_ascii=False)
    matches = re.findall(r'(?:https?:)?//[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*', json_str)
    for u in matches:
        clean_u = u.strip()
        if clean_u.startswith("//"):
            clean_u = "https:" + clean_u
        if clean_u not in urls:
            urls.append(clean_u)
    return urls

def fetch_match_detail(session, base_api, match_id):
    if not match_id:
        return None
    url = f"{base_api}/matches/detail/{match_id}"
    try:
        res = session.get(url, headers=HEADERS, timeout=6, verify=False)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None

def fetch_single_detail(item, session):
    dt_vn = parse_to_vn_time(item.get("start_date"))
    if dt_vn:
        tz_vn = timezone(timedelta(hours=7))
        now_vn = datetime.now(tz_vn).replace(tzinfo=None)
        if dt_vn < (now_vn - timedelta(hours=6)) or dt_vn > (now_vn + timedelta(days=2)):
            return False
    
    m_id = item.get("id")
    base_api = item.get("_base_api", API_DOMAINS[0])
    detail = fetch_match_detail(session, base_api, m_id)
    if detail:
        item["_detail"] = detail
    return True

def fetch_matches():
    all_matches = []
    seen_ids = set()

    payload = {
        "limit": 100,
        "page": 1,
        "order_asc": "start_date",
        "queries": [],
        "query_or": True
    }

    session = requests.Session()

    for base_api in API_DOMAINS:
        url = f"{base_api}/matches/graph"
        fetched_any = False
        for page in range(1, 10):
            payload["page"] = page
            try:
                res = session.post(url, headers=HEADERS, json=payload, timeout=8, verify=False)
                if res.status_code == 200:
                    res_json = res.json()
                    data = res_json.get("data", [])
                    if isinstance(data, list) and len(data) > 0:
                        for item in data:
                            m_id = item.get("id")
                            if m_id and m_id not in seen_ids:
                                seen_ids.add(m_id)
                                item["_base_api"] = base_api
                                all_matches.append(item)
                        fetched_any = True
                    else:
                        break
            except Exception:
                break

        if fetched_any:
            break

    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(fetch_single_detail, item, session) for item in all_matches]
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

        # 1. Chỉ lọc trận CÓ BLV (nếu không có BLV thì bỏ qua)
        blv_name = get_blv_name(item, detail_item)
        if not blv_name:
            continue

        dt_vn = parse_to_vn_time(item.get("start_date"))
        formatted_time = format_time_str(dt_vn)

        team1 = str(item.get("team_1") or detail_item.get("team_1") or "").strip()
        team2 = str(item.get("team_2") or detail_item.get("team_2") or "").strip()
        title_raw = str(item.get("title") or detail_item.get("title") or item.get("name") or "").strip()

        if team1 and team2:
            match_name = f"{team1} vs {team2}"
        elif title_raw:
            match_name = title_raw.replace(" - ", " vs ")
        else:
            match_name = "Trận đấu Phá Làng TV"

        desc = str(item.get("desc") or detail_item.get("desc") or "").strip()
        logo = str(item.get("team_1_logo") or detail_item.get("team_1_logo") or item.get("logo") or "").strip()
        icon = get_sport_icon(desc, match_name)

        # Trận đang diễn ra có icon 🟢
        is_live = False
        if dt_vn and (dt_vn <= now_vn <= dt_vn + timedelta(minutes=150)):
            is_live = True
        live_prefix = "🟢 " if is_live else ""

        # Lấy danh sách URL m3u8
        urls = extract_urls(detail_item) or extract_urls(item)
        if not urls:
            continue

        # Tạo luồng Chuẩn và HD2
        stream_list = []
        for u in urls:
            stream_list.append({"url": u, "tag": ""})
            if "pull.digitalcdn.net" in u:
                hd2_url = u.replace("pull.digitalcdn.net", "pull1.digitalcdn.net")
                stream_list.append({"url": hd2_url, "tag": " (HD2)"})

        for st in stream_list:
            stream_url = st["url"]
            tag_hd = st["tag"]

            # Format chính xác theo yêu cầu:
            # 🟢 07:00 03/10 🏐 Việt Nam vs Thái Lan (LÝ LIỀU LĨNH) [geo]
            # 🟢 07:00 03/10 🏐 Việt Nam vs Thái Lan (LÝ LIỀU LĨNH) (HD2) [geo]
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
    print("Đang tải dữ liệu Phá Làng TV...", flush=True)
    matches = fetch_matches()
    m3u_content, total_channels = build_m3u(matches)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"Đã xuất thành công {total_channels} luồng vào {OUTPUT_FILE}", flush=True)

if __name__ == "__main__":
    main()
    
