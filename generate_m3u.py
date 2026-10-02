import json
import os
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

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
REFERER = "https://phalang.live/"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "User-Agent": USER_AGENT,
    "Origin": "https://phalang.live",
    "Referer": REFERER
}

GROUP_ORDER = [
    "Bóng Đá",
    "Bóng Chuyền",
    "Bóng Rổ",
    "Cầu Lông",
    "Quần Vợt (Tennis)",
    "Bida (Billiards)",
    "Bóng Bàn",
    "Thể Thao Điện Tử",
    "Đua Xe",
    "Thể Thao Khác"
]

SPORT_MAPPING = {
    "FOOTBALL": {"group": "Bóng Đá", "icon": "⚽"},
    "BONG DA": {"group": "Bóng Đá", "icon": "⚽"},
    "SOCCER": {"group": "Bóng Đá", "icon": "⚽"},
    
    "VOLLEYBALL": {"group": "Bóng Chuyền", "icon": "🏐"},
    "BONG CHUYEN": {"group": "Bóng Chuyền", "icon": "🏐"},
    
    "BASKETBALL": {"group": "Bóng Rổ", "icon": "🏀"},
    "BONG RO": {"group": "Bóng Rổ", "icon": "🏀"},
    
    "TENNIS": {"group": "Quần Vợt (Tennis)", "icon": "🎾"},
    
    "BADMINTON": {"group": "Cầu Lông", "icon": "🏸"},
    "CAU LONG": {"group": "Cầu Lông", "icon": "🏸"},
    
    "TABLE TENNIS": {"group": "Bóng Bàn", "icon": "🏓"},
    "BONG BAN": {"group": "Bóng Bàn", "icon": "🏓"},
    
    "BILLIARDS": {"group": "Bida (Billiards)", "icon": "🎱"},
    "POOL": {"group": "Bida (Billiards)", "icon": "🎱"},
    
    "ESPORTS": {"group": "Thể Thao Điện Tử", "icon": "🎮"},
    "GAME": {"group": "Thể Thao Điện Tử", "icon": "🎮"},
    
    "RACING": {"group": "Đua Xe", "icon": "🏎️"},
    "F1": {"group": "Đua Xe", "icon": "🏎️"}
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

def get_sport_info(desc, title=""):
    text_check = f"{desc} {title}".upper()
    for key, info in SPORT_MAPPING.items():
        if key in text_check:
            return info["group"], info["icon"]
    return "Thể Thao Khác", "🏆"

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

def fetch_match_detail(match_id):
    for base_api in API_DOMAINS:
        url = f"{base_api}/matches/detail/{match_id}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=4, verify=False)
            if res.status_code == 200:
                res_json = res.json()
                if isinstance(res_json, dict):
                    data = res_json.get("data")
                    if isinstance(data, dict) and data:
                        return data
                    return res_json
        except Exception:
            continue
    return {}

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
                                all_matches.append(item)
                        print(f" -> Lấy thành công Page {page} từ {base_api} ({len(data)} trận)")
                    else:
                        break
            except Exception as e:
                print(f" -> Lỗi gọi API {url}: {e}")
                break

        if len(all_matches) > 0:
            break

    if all_matches:
        print(f"=== Đang cào chi tiết luồng cho {len(all_matches)} trận đấu... ===")
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_match = {executor.submit(fetch_match_detail, item["id"]): item for item in all_matches if item.get("id")}
            for future in as_completed(future_to_match):
                item = future_to_match[future]
                try:
                    detail = future.result()
                    item["_detail"] = detail
                except Exception:
                    item["_detail"] = {}

    return all_matches

def create_match_streams(item):
    """
    Tạo chính xác các luồng phát dựa trên dữ liệu thực tế từ API.
    Thêm pipe header (|Referer=...&User-Agent=...) để vượt qua cơ chế chống Chơi Chùa của CDN.
    """
    detail = item.get("_detail") or {}

    main_blv = str(detail.get("blv") or item.get("blv") or "").strip()
    stream_key = str(detail.get("stream_key") or item.get("stream_key") or "").strip()
    
    source_live = str(detail.get("source_live") or item.get("source_live") or "").strip()

    servers = detail.get("servers") or detail.get("sources") or item.get("servers") or []
    if isinstance(servers, list):
        for s in servers:
            if isinstance(s, dict):
                s_url = s.get("url") or s.get("source") or s.get("m3u8")
                if s_url and str(s_url).startswith("http"):
                    source_live = str(s_url).strip()
                    break

    streams = []
    pipe_headers = f"|Referer={REFERER}&User-Agent={USER_AGENT}"

    # 1. Luồng BLV Web chính (Có logo Phá Làng TV)
    if source_live and source_live.startswith("http"):
        tag_main = f"({main_blv}) [geo]" if main_blv else "[geo]"
        streams.append({
            "url": source_live + pipe_headers,
            "tag": tag_main
        })

        # 2. Luồng HD2 Web (Dự phòng CDN pull1)
        if "pull.digitalcdn.net" in source_live:
            hd2_base = source_live.replace("pull.digitalcdn.net", "pull1.digitalcdn.net")
        elif "://pull." in source_live:
            hd2_base = source_live.replace("://pull.", "://pull1.")
        else:
            hd2_base = source_live

        tag_hd2 = f"({main_blv}) (HD2) [geo]" if main_blv else "(HD2) [geo]"
        streams.append({
            "url": hd2_base + pipe_headers,
            "tag": tag_hd2
        })

    # 3. Luồng Nhà đài gốc
    if stream_key:
        nhadai_url = f"https://lilive1.eu.cc/live/{stream_key}/playlist.m3u8"
        tag_nhadai = "(Nhà đài)"
        streams.append({
            "url": nhadai_url + pipe_headers,
            "tag": tag_nhadai
        })

    return streams, main_blv

def build_m3u(matches):
    m3u_lines = ['#EXTM3U']

    grouped_items = {grp: [] for grp in GROUP_ORDER}
    total_channels = 0

    tz_vn = timezone(timedelta(hours=7))
    now_vn = datetime.now(tz_vn).replace(tzinfo=None)

    for item in matches:
        if not isinstance(item, dict):
            continue

        dt_vn = parse_and_convert_to_vn_time(item.get("start_date"))
        if not is_valid_time_window(dt_vn):
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
        group_category, icon = get_sport_info(desc, match_name)

        streams, main_blv = create_match_streams(item)
        if not streams:
            continue

        has_web_blv = bool(main_blv and "nhà đài" not in main_blv.lower() and "nha dai" not in main_blv.lower())
        if group_category == "Bóng Đá" and not has_web_blv:
            continue

        logo = str(item.get("team_1_logo") or item.get("logo") or "").strip()
        formatted_time = format_time_str(dt_vn)

        is_live = False
        if dt_vn and (dt_vn <= now_vn <= dt_vn + timedelta(hours=2, minutes=30)):
            is_live = True
        live_prefix = "🟢 " if is_live else ""

        for st in streams:
            display_title = f"{live_prefix}{formatted_time} {icon} {match_name} {st['tag']}".strip()
            display_title = re.sub(r'\s+', ' ', display_title)

            channel_entry = [
                f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group_category}" , {display_title}',
                f'#EXTVLCOPT:http-user-agent={USER_AGENT}',
                f'#EXTVLCOPT:http-referrer={REFERER}',
                st["url"]
            ]

            if group_category in grouped_items:
                grouped_items[group_category].append(channel_entry)
            else:
                grouped_items["Thể Thao Khác"].append(channel_entry)

            total_channels += 1

    for grp in GROUP_ORDER:
        entries = grouped_items.get(grp, [])
        for entry in entries:
            m3u_lines.extend(entry)

    return "\n".join(m3u_lines), total_channels

def main():
    print("=== Bắt đầu cào dữ liệu Phá Làng TV ===")
    matches = fetch_matches_by_post()
    print(f"Tổng số trận cào được: {len(matches)}")

    m3u_content, total_channels = build_m3u(matches)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"=== Xuất thành công {total_channels} luồng vào file: {OUTPUT_FILE} ===")

if __name__ == "__main__":
    main()
    
