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

# Thứ tự ưu tiên hiển thị Nhóm (Bóng Đá xếp đầu tiên)
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
            # Quy đổi UTC -> Múi giờ Việt Nam (GMT+7)
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

def extract_all_streams(item, detail_item=None):
    streams = []
    seen_urls = set()
    
    source_obj = detail_item if detail_item else item
    default_blv = str(source_obj.get("blv") or item.get("blv") or "").strip()

    # 1. Luồng source_live chính
    for obj in [source_obj, item]:
        source_live = obj.get("source_live")
        if source_live and str(source_live).startswith("http") and source_live not in seen_urls:
            streams.append({
                "name": "FHD",
                "url": str(source_live).strip(),
                "blv": default_blv,
                "is_geo": True
            })
            seen_urls.add(source_live)

    # 2. Các luồng server phụ
    servers = []
    for obj in [source_obj, item]:
        for key in ["servers", "streams", "sources", "play_urls", "links", "channels"]:
            val = obj.get(key)
            if isinstance(val, list):
                servers.extend(val)

    for s in servers:
        s_url, s_name, s_blv, is_geo = None, "", default_blv, True
        if isinstance(s, dict):
            s_url = s.get("url") or s.get("source") or s.get("link") or s.get("m3u8")
            s_name = str(s.get("name") or s.get("label") or s.get("quality") or s.get("title") or "").strip()
            if s.get("blv"):
                s_blv = str(s.get("blv")).strip()
        elif isinstance(s, str):
            s_url = s

        if s_url and str(s_url).startswith("http") and s_url not in seen_urls:
            streams.append({
                "name": s_name,
                "url": str(s_url).strip(),
                "blv": s_blv,
                "is_geo": is_geo
            })
            seen_urls.add(s_url)

    # 3. Stream_key dự phòng
    stream_key = source_obj.get("stream_key") or item.get("stream_key")
    if stream_key and len(streams) == 0:
        sk_url = f"https://lilive1.eu.cc/live/{stream_key}/playlist.m3u8"
        streams.append({
            "name": "HD",
            "url": sk_url,
            "blv": default_blv,
            "is_geo": True
        })

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
    m3u_lines = [
        '#EXTM3U url-tvg="" tvg-shift="0"',
        '# Playlist Tự Động Phá Làng TV - Lọc Bỏ Luồng Nhà Đài Bóng Đá'
    ]

    grouped_items = {grp: [] for grp in GROUP_ORDER}
    total_channels = 0

    for item in matches:
        if not isinstance(item, dict):
            continue

        dt_vn = parse_and_convert_to_vn_time(item.get("start_date"))
        
        if not is_valid_time_window(dt_vn):
            continue

        detail_item = item.get("_detail")
        streams = extract_all_streams(item, detail_item)
        
        if not streams:
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
        main_blv = str(item.get("blv") or "").strip()
        logo = str(item.get("team_1_logo") or item.get("logo") or "").strip()
        formatted_time = format_time_str(dt_vn)

        group_category, icon = get_sport_info(desc, match_name)

        for st in streams:
            blv_name = st.get("blv") or main_blv
            
            # --- LỌC BỎ LUỒNG NHÀ ĐÀI CHO MỤC BÓNG ĐÁ ---
            if group_category == "Bóng Đá" and not blv_name:
                continue
            # ---------------------------------------------

            blv_tag = f" ({blv_name})" if blv_name else " (Nhà đài)"
            
            quality_str = str(st.get("name") or "").strip()
            quality_tag = f" ({quality_str})" if quality_str else ""
            geo_tag = " [geo]" if st.get("is_geo") else ""

            display_title = f"{formatted_time} {icon} {match_name}{blv_tag}{quality_tag}{geo_tag}".strip()
            display_title = re.sub(r'\s+', ' ', display_title)

            item_id = str(item.get("id") or "")
            
            channel_entry = [
                f'#EXTINF:-1 tvg-id="{item_id}" tvg-name="{display_title}" tvg-logo="{logo}" group-title="{group_category}", {display_title}',
                '#EXTVLCOPT:http-user-agent=Mozilla/5.0',
                '#EXTVLCOPT:http-referrer=https://phalang1.tv/',
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
    print("=== Bắt đầu cào dữ liệu Phá Làng TV (Lọc bỏ Nhà đài Bóng Đá) ===")
    matches = fetch_matches_by_post()
    print(f"Tổng số trận cào được: {len(matches)}")

    m3u_content, total_channels = build_m3u(matches)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"=== Xuất thành công {total_channels} luồng vào file: {OUTPUT_FILE} ===")

if __name__ == "__main__":
    main()
    
