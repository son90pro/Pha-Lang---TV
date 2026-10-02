import json
import os
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

SPORT_ICONS = {
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

def parse_and_convert_to_vn_time(date_val):
    if not date_val:
        return None
    try:
        val_str = str(date_val).strip().replace("T", " ")
        if "." in val_str:
            val_str = val_str.split(".")[0]
        
        dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(val_str, fmt)
                break
            except ValueError:
                pass
        
        if dt:
            return dt + timedelta(hours=7)
    except Exception:
        pass
    return None

def format_time_str(dt):
    if not dt:
        return ""
    return dt.strftime("%H:%M %d/%m")

def get_sport_icon(desc, title=""):
    text_check = f"{desc} {title}".upper()
    for key, icon in SPORT_ICONS.items():
        if key in text_check:
            return icon
    return "⚽"

def is_valid_time_window(dt_vn):
    if not dt_vn:
        return True
    
    tz_vn = timezone(timedelta(hours=7))
    now_vn = datetime.now(tz_vn).replace(tzinfo=None)
    
    today_start = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
    day_after_tomorrow_end = today_start + timedelta(days=2) - timedelta(seconds=1)
    
    if dt_vn < (now_vn - timedelta(hours=3)):
        return False
    if dt_vn > day_after_tomorrow_end:
        return False
        
    return True

def extract_hash_ids(item, detail_item=None):
    """
    Tách chính xác 2 Hash ID riêng biệt:
    1. digitalcdn_id (Luồng BLV) từ source_live
    2. nhadai_id (Luồng Nhà đài) từ stream_key
    """
    source_obj = detail_item if detail_item else item
    
    digitalcdn_id = None
    nhadai_id = None

    # Tìm digitalcdn_id
    for obj in [source_obj, item]:
        source_live = str(obj.get("source_live") or "")
        match = re.search(r'digitalcdn\.net/live/([a-f0-9]{32})', source_live)
        if match:
            digitalcdn_id = match.group(1)
            break
        elif re.match(r'^[a-f0-9]{32}$', source_live):
            digitalcdn_id = source_live
            break

    # Tìm nhadai_id
    for obj in [source_obj, item]:
        sk = str(obj.get("stream_key") or "").strip()
        if re.match(r'^[a-f0-9]{32}$', sk):
            nhadai_id = sk
            break
        match = re.search(r'lilive1\.eu\.cc/live/([a-f0-9]{32})', sk)
        if match:
            nhadai_id = match.group(1)
            break

    return digitalcdn_id, nhadai_id

def fetch_match_detail(session, base_api, match_id):
    url = f"{base_api}/matches/detail/{match_id}"
    try:
        res = session.get(url, headers=HEADERS, timeout=5, verify=False)
        if res.status_code == 200:
            res_json = res.json()
            return res_json.get("data") or res_json
    except Exception:
        pass
    return None

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
        for page in range(1, 10):
            payload["page"] = page
            try:
                res = session.post(url, headers=HEADERS, json=payload, timeout=10, verify=False)
                if res.status_code == 200:
                    res_json = res.json()
                    data = res_json.get("data", [])
                    if isinstance(data, list) and len(data) > 0:
                        for item in data:
                            m_id = item.get("id")
                            if m_id and m_id not in seen_ids:
                                seen_ids.add(m_id)
                                detail = fetch_match_detail(session, base_api, m_id)
                                item["_detail"] = detail
                                all_matches.append(item)
                        print(f" -> Lấy thành công Page {page} từ {base_api} ({len(data)} trận)")
                    else:
                        break
            except Exception as e:
                print(f" -> Lỗi gọi API {url}: {e}")
                break

        if len(all_matches) > 0:
            break

    return all_matches

def build_m3u(matches):
    m3u_lines = ["#EXTM3U\n"]
    REFERRER_TAG = "#EXTVLCOPT:http-referrer=https://phalang.live/"
    total_channels = 0

    for item in matches:
        if not isinstance(item, dict):
            continue

        dt_vn = parse_and_convert_to_vn_time(item.get("start_date"))
        if not is_valid_time_window(dt_vn):
            continue

        detail_item = item.get("_detail")
        digitalcdn_id, nhadai_id = extract_hash_ids(item, detail_item)

        if not digitalcdn_id and not nhadai_id:
            continue

        team1 = str(item.get("team_1") or "").strip()
        team2 = str(item.get("team_2") or "").strip()
        title_raw = str(item.get("title") or "").strip()

        if team1 and team2:
            match_name = f"{team1} vs {team2}"
        elif title_raw:
            match_name = title_raw.replace(" - ", " vs ")
        else:
            continue

        desc = str(item.get("desc") or "").strip()
        logo = str(item.get("team_1_logo") or item.get("logo") or "").strip()
        formatted_time = format_time_str(dt_vn)
        icon = get_sport_icon(desc, match_name)

        # Kiểm tra trận đang diễn ra
        is_live = item.get("is_live") or item.get("status") == "LIVE"
        live_prefix = "🟢 " if is_live else ""

        # Tên Bình luận viên
        blv_name = str(item.get("blv") or (detail_item.get("blv") if detail_item else "") or "").strip()
        blv_label = f"({blv_name})" if blv_name else ""

        # 1. Luồng BLV - Server chính
        if digitalcdn_id:
            title_s1 = f"{live_prefix}{formatted_time} {icon} {match_name} {blv_label} [geo]".strip()
            title_s1 = re.sub(r'\s+', ' ', title_s1)
            url_s1 = f"https://pull.digitalcdn.net/live/{digitalcdn_id}/index.m3u8"
            
            m3u_lines.extend([
                f'#EXTINF:-1 tvg-logo="{logo}" group-title="Phá Làng TV" , {title_s1}',
                REFERRER_TAG,
                url_s1,
                ""
            ])
            total_channels += 1

        # 2. Luồng BLV - Server dự phòng (HD2)
        if digitalcdn_id:
            title_s2 = f"{live_prefix}{formatted_time} {icon} {match_name} {blv_label} (HD2) [geo]".strip()
            title_s2 = re.sub(r'\s+', ' ', title_s2)
            url_s2 = f"https://pull1.digitalcdn.net/live/{digitalcdn_id}/index.m3u8"
            
            m3u_lines.extend([
                f'#EXTINF:-1 tvg-logo="{logo}" group-title="Phá Làng TV" , {title_s2}',
                REFERRER_TAG,
                url_s2,
                ""
            ])
            total_channels += 1

        # 3. Luồng Nhà đài
        if nhadai_id:
            title_s3 = f"{live_prefix}{formatted_time} {icon} {match_name} (Nhà đài)".strip()
            title_s3 = re.sub(r'\s+', ' ', title_s3)
            url_s3 = f"https://lilive1.eu.cc/live/{nhadai_id}/playlist.m3u8"
            
            m3u_lines.extend([
                f'#EXTINF:-1 tvg-logo="{logo}" group-title="Phá Làng TV" , {title_s3}',
                REFERRER_TAG,
                url_s3,
                ""
            ])
            total_channels += 1

    return "\n".join(m3u_lines), total_channels

def main():
    print("=== Bắt đầu cào dữ liệu Phá Làng TV (Chuẩn M3U) ===")
    matches = fetch_matches_by_post()
    print(f"Tổng số trận cào được: {len(matches)}")

    m3u_content, total_channels = build_m3u(matches)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"=== Xuất thành công {total_channels} luồng vào file: {OUTPUT_FILE} ===")

if __name__ == "__main__":
    main()
    
