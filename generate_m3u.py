import json
import re
from datetime import datetime, timedelta, timezone
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
    "Referer": "https://phalang1.tv/"
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
    "RACING": "🏎️", "F1": "🏎️"
}

INVALID_BLVS = ["nhà đài", "nha dai", "nhàđài", "none", "null", "undefined", "0", "đang cập nhật", ""]

def parse_to_vn_time(date_val):
    if not date_val:
        return None
    try:
        # Xử lý Unix Timestamp
        if isinstance(date_val, (int, float)) or (isinstance(date_val, str) and date_val.isdigit()):
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
    return "🏆"

def is_valid_time_window(dt_vn):
    if not dt_vn:
        return True
    
    tz_vn = timezone(timedelta(hours=7))
    now_vn = datetime.now(tz_vn).replace(tzinfo=None)
    
    today_start = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
    day_after_tomorrow_end = today_start + timedelta(days=3) - timedelta(seconds=1)
    
    # Giữ lại các trận đấu từ 4 tiếng trước cho tới hết 2 ngày tới
    if dt_vn < (now_vn - timedelta(hours=4)):
        return False
    if dt_vn > day_after_tomorrow_end:
        return False
        
    return True

def get_blv_from_obj(obj):
    if not obj or not isinstance(obj, dict):
        return ""
    for key in ["blv", "blv_name", "commentator", "caster", "streamer", "author"]:
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        elif isinstance(val, dict):
            name = val.get("name") or val.get("nickname") or val.get("title")
            if name and str(name).strip():
                return str(name).strip()
    return ""

def fetch_match_detail(session, base_api, match_id):
    url = f"{base_api}/matches/detail/{match_id}"
    try:
        res = session.get(url, headers=HEADERS, timeout=4, verify=False)
        if res.status_code == 200:
            res_json = res.json()
            return res_json.get("data") or res_json
    except Exception:
        pass
    return None

def extract_all_streams(item, detail_item=None):
    streams = []
    seen_urls = set()

    sources = [s for s in [detail_item, item] if s and isinstance(s, dict)]
    
    # Tìm tên BLV ưu tiên
    default_blv = ""
    for src in sources:
        blv = get_blv_from_obj(src)
        if blv:
            default_blv = blv
            break

    # 1. Trích xuất từ mảng danh sách luồng
    raw_servers = []
    for src in sources:
        for k in ["servers", "streams", "sources", "play_urls", "links", "channels", "relates", "list_link"]:
            val = src.get(k)
            if isinstance(val, list):
                raw_servers.extend(val)

    for s in raw_servers:
        if not s:
            continue
        s_url, s_name, s_blv = None, "", default_blv
        if isinstance(s, dict):
            s_url = s.get("url") or s.get("source") or s.get("link") or s.get("m3u8") or s.get("play_url") or s.get("stream")
            s_name = str(s.get("name") or s.get("label") or s.get("quality") or s.get("title") or s.get("type") or "").strip()
            s_blv = get_blv_from_obj(s) or default_blv
        elif isinstance(s, str):
            s_url = s

        if s_url and str(s_url).startswith("http") and s_url not in seen_urls:
            clean_name = s_name.upper()
            if clean_name in ["DEFAULT", "MAIN", "LUỒNG CHÍNH", "SERVER 1"]:
                clean_name = ""
            
            streams.append({
                "name": clean_name,
                "url": str(s_url).strip(),
                "blv": s_blv,
                "is_geo": True
            })
            seen_urls.add(str(s_url).strip())

    # 2. Trích xuất luồng chính trực tiếp
    for src in sources:
        for k in ["source_live", "play_url", "link", "m3u8", "url", "stream_url", "hls"]:
            val = str(src.get(k) or "").strip()
            if val and val.startswith("http") and val not in seen_urls:
                streams.insert(0, {
                    "name": "",
                    "url": val,
                    "blv": default_blv,
                    "is_geo": True
                })
                seen_urls.add(val)

    # 3. Tự động tạo luồng HD2 từ domain digitalcdn
    digitalcdn_streams = [s for s in streams if "pull.digitalcdn.net" in s["url"]]
    for st in digitalcdn_streams:
        pull1_url = st["url"].replace("pull.digitalcdn.net", "pull1.digitalcdn.net")
        if pull1_url not in seen_urls:
            streams.append({
                "name": "HD2",
                "url": pull1_url,
                "blv": st["blv"],
                "is_geo": True
            })
            seen_urls.add(pull1_url)

    return streams

def fetch_matches_by_post():
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
                        print(f" -> Lấy thành công Page {page} từ {base_api} ({len(data)} trận)")
                    else:
                        break
            except Exception as e:
                print(f" -> Lỗi gọi API {url}: {e}")
                break

        if fetched_any:
            break

    # Chỉ gọi API Detail cho các trận đấu nằm trong khung giờ hợp lệ
    print(" -> Đang tải dữ liệu chi tiết cho các trận trong khung giờ...")
    valid_count = 0
    for item in all_matches:
        dt_vn = parse_to_vn_time(item.get("start_date"))
        if is_valid_time_window(dt_vn):
            m_id = item.get("id")
            base_api = item.get("_base_api", API_DOMAINS[0])
            detail = fetch_match_detail(session, base_api, m_id)
            if detail:
                item["_detail"] = detail
            valid_count += 1

    print(f" -> Đã cập nhật chi tiết cho {valid_count} trận đấu hợp lệ.")
    return all_matches

def build_m3u(matches):
    m3u_lines = ["#EXTM3U\n"]
    total_channels = 0

    tz_vn = timezone(timedelta(hours=7))
    now_vn = datetime.now(tz_vn).replace(tzinfo=None)

    for item in matches:
        if not isinstance(item, dict):
            continue

        dt_vn = parse_to_vn_time(item.get("start_date"))
        
        if not is_valid_time_window(dt_vn):
            continue

        detail_item = item.get("_detail") or {}
        
        # Kiểm tra BLV Tiếng Việt
        main_blv = get_blv_from_obj(detail_item) or get_blv_from_obj(item)
        if main_blv.lower().strip() in INVALID_BLVS:
            continue

        streams = extract_all_streams(item, detail_item)
        if not streams:
            continue

        team1 = str(item.get("team_1") or detail_item.get("team_1") or "").strip()
        team2 = str(item.get("team_2") or detail_item.get("team_2") or "").strip()
        title_raw = str(item.get("title") or detail_item.get("title") or "").strip()

        if team1 and team2:
            match_name = f"{team1} vs {team2}"
        elif title_raw:
            match_name = title_raw.replace(" - ", " vs ")
        else:
            continue

        desc = str(item.get("desc") or detail_item.get("desc") or "").strip()
        logo = str(item.get("team_1_logo") or detail_item.get("team_1_logo") or item.get("logo") or "").strip()
        formatted_time = format_time_str(dt_vn)
        icon = get_sport_icon(desc, match_name)

        is_live = False
        if dt_vn and (dt_vn <= now_vn <= dt_vn + timedelta(minutes=150)):
            is_live = True
        
        live_prefix = "🟢 " if is_live else ""

        for st in streams:
            blv_name = st.get("blv") or main_blv
            blv_tag = f"({blv_name})" if blv_name else ""
            
            quality_str = str(st.get("name") or "").strip()
            quality_tag = f"({quality_str})" if quality_str else ""
            geo_tag = "[geo]" if st.get("is_geo") else ""

            title_parts = [f"{live_prefix}{formatted_time}".strip(), icon, match_name, blv_tag, quality_tag, geo_tag]
            display_title = " ".join([p for p in title_parts if p])
            display_title = re.sub(r'\s+', ' ', display_title)

            entry_lines = (
                f'#EXTINF:-1 tvg-logo="{logo}" group-title="Phá Làng TV" , {display_title}\n'
                f'#EXTVLCOPT:http-referrer=https://phalang.live/\n'
                f'{st["url"]}\n'
            )

            m3u_lines.append(entry_lines)
            total_channels += 1

    return "\n".join(m3u_lines), total_channels

def main():
    print("=== Bắt đầu cào dữ liệu Phá Làng TV (Đa luồng & Lọc BLV Tiếng Việt) ===")
    matches = fetch_matches_by_post()
    print(f"Tổng số trận thu thập: {len(matches)}")

    m3u_content, total_channels = build_m3u(matches)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"=== Xuất thành công {total_channels} luồng vào file: {OUTPUT_FILE} ===")

if __name__ == "__main__":
    main()
    
