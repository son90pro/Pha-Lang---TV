import json
import os
import re
from datetime import datetime, timedelta, timezone
import requests
import urllib3

# Tắt cảnh báo SSL không an toàn
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Danh sách API Domain dự phòng
API_DOMAINS = [
    "https://api.plapi202624081158.com",
    "https://api.phalang.tv",
    "https://api.phalang1.tv",
    "https://api.phalang.net"
]

OUTPUT_FILE = "phalang.m3u"
GROUP_TITLE = "Phá Làng TV"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Origin": "https://phalang1.tv",
    "Referer": "https://phalang1.tv/"
}

# Icon theo môn thể thao
SPORT_ICONS = {
    "FOOTBALL": "⚽", "BONG DA": "⚽",
    "VOLLEYBALL": "🏐", "BONG CHUYEN": "🏐",
    "BASKETBALL": "🏀", "BONG RO": "🏀",
    "TENNIS": "🎾", "BADMINTON": "🏸",
    "TABLE TENNIS": "🏓", "BILLIARDS": "🎱",
    "ESPORTS": "🎮", "RACING": "🏎️"
}

def parse_vietnam_datetime(date_val):
    if not date_val:
        return None
    try:
        val_str = str(date_val).strip()
        clean_str = val_str.replace("T", " ")
        if "." in clean_str:
            clean_str = clean_str.split(".")[0]
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(clean_str, fmt)
            except ValueError:
                pass
    except Exception:
        pass
    return None

def format_time_str(dt):
    if not dt:
        return ""
    return dt.strftime("%H:%M %d/%m")

def extract_all_streams(item):
    streams = []
    seen_urls = set()
    default_blv = str(item.get("blv") or "").strip()

    # 1. Ưu tiên source_live trực tiếp từ API nếu có
    source_live = item.get("source_live")
    if source_live and str(source_live).startswith("http"):
        streams.append({
            "name": "",
            "url": str(source_live).strip(),
            "blv": default_blv,
            "is_geo": True
        })
        seen_urls.add(source_live)

    # 2. Quét mảng servers / streams chứa các chất lượng HD, FHD, HD1, HD2...
    servers = []
    for key in ["servers", "streams", "sources", "play_urls", "links"]:
        val = item.get(key)
        if isinstance(val, list):
            servers.extend(val)

    for s in servers:
        s_url, s_name, s_blv, is_geo = None, "", default_blv, True
        if isinstance(s, dict):
            s_url = s.get("url") or s.get("source") or s.get("link") or s.get("m3u8")
            s_name = str(s.get("name") or s.get("label") or s.get("quality") or "").strip()
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

    # 3. Tạo link tự động qua stream_key nếu chưa có link phát nào
    stream_key = item.get("stream_key")
    if stream_key and len(streams) == 0:
        sk_url = f"https://lilive1.eu.cc/live/{stream_key}/playlist.m3u8"
        streams.append({
            "name": "",
            "url": sk_url,
            "blv": default_blv,
            "is_geo": True
        })

    return streams

def fetch_matches_by_post():
    all_matches = []
    seen_ids = set()

    # Payload lấy danh sách trận HOT & TOP & LIVE
    payload = {
        "limit": 50,
        "page": 1,
        "order_asc": "start_date",
        "queries": [
            {"field": "is_hot", "type": "equal", "value": True},
            {"field": "is_top", "type": "equal", "value": True},
            {"field": "is_live", "type": "equal", "value": True}
        ],
        "query_or": True
    }

    session = requests.Session()

    for base_api in API_DOMAINS:
        url = f"{base_api}/matches/graph"
        for page in range(1, 4):  # Quét tối đa 3 trang
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

    return all_matches

def build_m3u(matches):
    m3u_lines = [
        '#EXTM3U url-tvg="" tvg-shift="0"',
        '# Playlist Tự Động Phá Làng TV'
    ]

    total_channels = 0

    for item in matches:
        if not isinstance(item, dict):
            continue

        dt_vn = parse_vietnam_datetime(item.get("start_date"))
        streams = extract_all_streams(item)
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

        desc = str(item.get("desc") or "FOOTBALL").strip().upper()
        main_blv = str(item.get("blv") or "").strip()
        logo = str(item.get("team_1_logo") or item.get("logo") or "").strip()
        formatted_time = format_time_str(dt_vn)

        icon = "⚽"
        for key, val in SPORT_ICONS.items():
            if key in desc:
                icon = val
                break

        for st in streams:
            blv_name = st.get("blv") or main_blv
            blv_tag = f" ({blv_name})" if blv_name else " (Nhà đài)"
            
            quality_str = str(st.get("name") or "").strip()
            quality_tag = f" ({quality_str})" if quality_str else ""

            geo_tag = " [geo]" if st.get("is_geo") else ""

            # Cấu trúc tiêu đề chuẩn như hình: 17:00 01/10 ⚽ Japan vs Ecuador (LÝ LA LÀNG) [geo]
            display_title = f"{formatted_time} {icon} {match_name}{blv_tag}{quality_tag}{geo_tag}".strip()
            display_title = re.sub(r'\s+', ' ', display_title)

            item_id = str(item.get("id") or "")
            
            m3u_lines.append(
                f'#EXTINF:-1 tvg-id="{item_id}" tvg-name="{display_title}" tvg-logo="{logo}" group-title="{GROUP_TITLE}", {display_title}'
            )
            m3u_lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0')
            m3u_lines.append('#EXTVLCOPT:http-referrer=https://phalang1.tv/')
            m3u_lines.append(st["url"])
            total_channels += 1

    return "\n".join(m3u_lines), total_channels

def main():
    print("=== Bắt đầu cào dữ liệu Phá Làng TV via POST API ===")
    matches = fetch_matches_by_post()
    print(f"Tổng số trận lấy được: {len(matches)}")

    m3u_content, total_channels = build_m3u(matches)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"=== Xuất thành công {total_channels} luồng vào file: {OUTPUT_FILE} ===")

if __name__ == "__main__":
    main()
