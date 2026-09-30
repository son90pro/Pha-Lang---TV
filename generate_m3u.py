import requests
import json
import re
import os
from datetime import datetime, timedelta

# Cấu hình API Phá Làng TV
API_URL = "https://api.plapi202624081158.com/matches/graph"
OUTPUT_FILE = "phalang.m3u"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://phalang1.tv",
    "Referer": "https://phalang1.tv/"
}

PAYLOAD = {
    "limit": 100,
    "page": 1,
    "order_asc": "start_date",
    "queries": [],
    "query_or": True
}

# Regex nhận diện các lứa trẻ U14 - U23 để lọc bỏ
YOUTH_REGEX = re.compile(r'\b(U-?1[4-9]|U-?2[0-3]|UNDER-?1[4-9]|UNDER-?2[0-3])\b', re.IGNORECASE)

SPORT_ICONS = {
    "FOOTBALL": "⚽",
    "VOLLEYBALL": "🏐",
    "BASKETBALL": "🏀",
    "TENNIS": "🎾",
    "BADMINTON": "🏸"
}

def parse_vietnam_time(date_str):
    """
    Chuyển đổi chuỗi ngày giờ từ API về múi giờ Việt Nam (UTC+7)
    Định dạng hiển thị: HH:MM DD/MM
    """
    if not date_str:
        return ""
    
    try:
        clean_str = str(date_str).replace("T", " ")
        if "." in clean_str:
            clean_str = clean_str.split(".")[0]
        if "+" in clean_str:
            clean_str = clean_str.split("+")[0]
        clean_str = clean_str.strip()
            
        dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(clean_str, fmt)
                break
            except ValueError:
                pass

        if not dt:
            return str(date_str)

        # Quy đổi về giờ Việt Nam (UTC+7)
        dt_vn = dt + timedelta(hours=7)
        return dt_vn.strftime("%H:%M %d/%m")
    except Exception:
        return str(date_str)

def is_youth_match(item):
    """Kiểm tra xem tên giải/đội bóng có thuộc lứa trẻ hay không"""
    check_text = f"{item.get('league', '')} {item.get('title', '')} {item.get('team_1', '')} {item.get('team_2', '')}"
    return bool(YOUTH_REGEX.search(check_text))

def extract_all_streams(item):
    """
    Trích xuất toàn bộ luồng phát (chính & phụ như HD1, HD2, FHD...)
    """
    streams = []
    seen_urls = set()

    # 1. Luồng chính
    main_url = item.get("source_live")
    if not main_url and item.get("stream_key"):
        main_url = f"https://lilive1.eu.cc/live/{item['stream_key']}/playlist.m3u8"
    
    if main_url:
        streams.append({"name": "", "url": main_url})
        seen_urls.add(main_url)

    # 2. Các luồng phụ/server khác
    extra_servers = (
        item.get("servers") or 
        item.get("streams") or 
        item.get("sources") or 
        item.get("play_urls") or []
    )
    
    for idx, s in enumerate(extra_servers, start=1):
        s_url = None
        s_name = f"HD{idx}"
        
        if isinstance(s, dict):
            s_url = s.get("url") or s.get("source") or s.get("link") or s.get("m3u8")
            s_name = s.get("name") or s.get("label") or s.get("title") or f"HD{idx}"
        elif isinstance(s, str):
            s_url = s

        if s_url and s_url not in seen_urls:
            streams.append({"name": f"[{s_name}]", "url": s_url})
            seen_urls.add(s_url)
            
    return streams

def fetch_matches():
    try:
        response = requests.post(API_URL, json=PAYLOAD, headers=HEADERS, timeout=20)
        if response.status_code == 200:
            return response.json().get("data", [])
        else:
            print(f"API trả về mã lỗi HTTP: {response.status_code}")
            return []
    except Exception as e:
        print(f"Lỗi khi kết nối API: {e}")
        return []

def build_m3u(matches):
    m3u_lines = [
        '#EXTM3U url-tvg="" tvg-shift="0"',
        '# Cập nhật tự động Phá Làng TV M3U Playlist'
    ]

    for item in matches:
        # Lọc bỏ các trận đấu lứa trẻ (U14 đến U23)
        if is_youth_match(item):
            continue

        team1 = item.get("team_1", "").strip()
        team2 = item.get("team_2", "").strip()
        title_raw = item.get("title", "").strip()
        league = item.get("league", "Phá Làng TV")
        desc = item.get("desc", "FOOTBALL").upper()
        blv = item.get("blv", "").strip()
        logo = item.get("team_1_logo") or item.get("team_2_logo") or ""
        start_date = item.get("start_date", "")
        is_live = item.get("is_live", False)

        streams = extract_all_streams(item)
        if not streams:
            continue

        formatted_time = parse_vietnam_time(start_date)
        icon = SPORT_ICONS.get(desc, "⚽")
        status_symbol = "🟢" if is_live else "⏳"
        
        match_name = f"{team1} vs {team2}" if (team1 and team2) else title_raw
        blv_text = f" ({blv})" if blv else ""

        for st in streams:
            quality_tag = f" {st['name']}" if st['name'] else ""
            display_title = f"{status_symbol} {formatted_time} {icon} {match_name}{blv_text}{quality_tag}"

            m3u_lines.append(f'#EXTINF:-1 tvg-id="{item.get("id", "")}" tvg-name="{display_title}" tvg-logo="{logo}" group-title="{league}", {display_title}')
            m3u_lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0')
            m3u_lines.append('#EXTVLCOPT:http-referrer=https://phalang1.tv/')
            m3u_lines.append(st["url"])

    return "\n".join(m3u_lines)

def main():
    print("Đang cào dữ liệu trận đấu từ Phá Làng TV...")
    matches = fetch_matches()
    
    if not matches:
        print("Không lấy được dữ liệu mới từ API. Giữ nguyên file hiện tại để tránh làm gián đoạn ứng dụng.")
        return

    print(f"Tổng số trận lấy về: {len(matches)}")
    m3u_content = build_m3u(matches)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)
        
    print(f"Đã xuất thành công danh sách M3U vào file: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
    
