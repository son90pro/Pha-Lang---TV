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
    "RACING": "🏎️", "F1": "🏎️️"
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
    return "🏆"

def is_valid_time_window(dt_vn):
    if not dt_vn:
        return True
    
    tz_vn = timezone(timedelta(hours=7))
    now_vn = datetime.now(tz_vn).replace(tzinfo=None)
    
    today_start = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = today_start + timedelta(days=2) - timedelta(seconds=1)
    
    if dt_vn < (now_vn - timedelta(hours=6)):
        return False
    if dt_vn > tomorrow_end:
        return False
        
    return True

def get_blv_from_obj(obj):
    if not isinstance(obj, dict):
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

def extract_streams_regex(obj_list):
    """
    Sử dụng Regex quét toàn bộ URL xuất hiện trong JSON (bao gồm key path, file, embed, m3u8...)
    """
    found_streams = []
    seen_urls = set()

    for obj in obj_list:
        if not obj:
            continue
        json_str = json.dumps(obj, ensure_ascii=False)
        
        # Regex tìm mọi URL dạng http(s):// hoặc //...
        urls = re.findall(r'(?:https?:)?//[^\s"\'<>\\]+', json_str)
        
        for url in urls:
            clean_url = url.strip()
            if clean_url.startswith("//"):
                clean_url = "https:" + clean_url
            
            # Bỏ qua hình ảnh, logo, CSS, JS
            if any(ext in clean_url.lower() for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".css", ".js", ".ico"]):
                continue
            
            if clean_url not in seen_urls:
                seen_urls.add(clean_url)
                found_streams.append({
                    "url": clean_url,
                    "name": "",
                    "blv": get_blv_from_obj(obj) if isinstance(obj, dict) else ""
                })

    # Tự động tạo luồng dự phòng HD2 nếu là domain digitalcdn
    digitalcdn_additions = []
    for st in found_streams:
        if "pull.digitalcdn.net" in st["url"]:
            alt_url = st["url"].replace("pull.digitalcdn.net", "pull1.digitalcdn.net")
            if alt_url not in seen_urls:
                seen_urls.add(alt_url)
                digitalcdn_additions.append({
                    "url": alt_url,
                    "name": "HD2",
                    "blv": st["blv"]
                })
    found_streams.extend(digitalcdn_additions)

    return found_streams

def fetch_single_detail(item, session):
    dt_vn = parse_to_vn_time(item.get("start_date"))
    if is_valid_time_window(dt_vn):
        m_id = item.get("id")
        base_api = item.get("_base_api", API_DOMAINS[0])
        detail = fetch_match_detail(session, base_api, m_id)
        if detail:
            item["_detail"] = detail
        return True
    return False

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
                        print(f" -> Lấy thành công Page {page} từ {base_api} ({len(data)} trận)", flush=True)
                    else:
                        break
            except Exception as e:
                print(f" -> Lỗi gọi API {url}: {e}", flush=True)
                break

        if fetched_any:
            break

    print(" -> Đang tải dữ liệu chi tiết đa luồng cho các trận đấu...", flush=True)
    
    valid_count = 0
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(fetch_single_detail, item, session) for item in all_matches]
        for future in as_completed(futures):
            if future.result():
                valid_count += 1

    print(f" -> Đã cập nhật chi tiết thành công cho {valid_count} trận hợp lệ.", flush=True)
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

        # Quét đệ quy + Regex lấy toàn bộ URL luồng phát
        streams = extract_streams_regex([detail_item, item])
        if not streams:
            continue

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
        formatted_time = format_time_str(dt_vn)
        icon = get_sport_icon(desc, match_name)

        is_live = False
        if dt_vn and (dt_vn <= now_vn <= dt_vn + timedelta(minutes=150)):
            is_live = True
        
        live_prefix = "🟢 " if is_live else ""
        main_blv = get_blv_from_obj(detail_item) or get_blv_from_obj(item)

        for st in streams:
            blv_name = st.get("blv") or main_blv
            blv_tag = f"({blv_name})" if blv_name else ""
            
            quality_str = str(st.get("name") or "").strip()
            quality_tag = f"({quality_str})" if quality_str else ""

            title_parts = [f"{live_prefix}{formatted_time}".strip(), icon, match_name, blv_tag, quality_tag, "[geo]"]
            display_title = " ".join([p for p in title_parts if p])
            display_title = re.sub(r'\s+', ' ', display_title)

            entry_lines = (
                f'#EXTINF:-1 tvg-logo="{logo}" group-title="Phá Làng TV" , {display_title}\n'
                f'#EXTVLCOPT:http-referrer=https://phalang.live/\n'
                f'{st["url"]}\n'
            )

            m3u_lines.append(entry_lines)
            total_channels += 1

    # In Debug nếu vẫn ra 0 luồng
    if total_channels == 0 and matches:
        print("\n[DEBUG CẢNH BÁO] Không tìm thấy luồng phát nào! Mẫu JSON phản hồi từ API:", flush=True)
        sample = matches[0].get("_detail") or matches[0]
        print(json.dumps(sample, ensure_ascii=False, indent=2)[:1000], flush=True)

    return "\n".join(m3u_lines), total_channels

def main():
    print("=== Bắt đầu cào dữ liệu Phá Làng TV ===", flush=True)
    matches = fetch_matches_by_post()
    print(f"Tổng số trận thu thập: {len(matches)}", flush=True)

    m3u_content, total_channels = build_m3u(matches)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"=== Xuất thành công {total_channels} luồng vào file: {OUTPUT_FILE} ===", flush=True)

if __name__ == "__main__":
    main()
    
