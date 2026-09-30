import requests
import json
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

# Các từ khóa giải trẻ cần lọc bỏ
EXCLUDE_YOUTH_KEYWORDS = [
    "U14", "U15", "U16", "U17", "U18", "U19", "U20", "U21", "U22", "U23",
    "UNDER 15", "UNDER 16", "UNDER 17", "UNDER 18", "UNDER 19", "UNDER 20"
]

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
    Định dạng đầu ra: HH:MM DD/MM
    """
    if not date_str:
        return ""
    
    try:
        # Xử lý cả định dạng ISO (2026-09-30T10:00:00) lẫn tiêu chuẩn (2026-09-30 10:00:00)
        clean_str = date_str.replace("T", " ")
        if "." in clean_str:
            clean_str = clean_str.split(".")[0]
        if "+" in clean_str:
            clean_str = clean_str.split("+")[0]
            
        dt = datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S")
        
        # Nếu giờ API gửi sang ở chuẩn UTC (thường là 10:00 UTC = 17:00 VN), cộng 7 tiếng
        dt_vn = dt + timedelta(hours=7)
        return dt_vn.strftime("%H:%M %d/%m")
    except Exception:
        return date_str

def is_youth_match(item):
    """Kiểm tra xem trận đấu có phải giải trẻ hay không"""
    check_text = f"{item.get('league', '')} {item.get('title', '')} {item.get('team_1', '')} {item.get('team_2', '')}".upper()
    for kw in EXCLUDE_YOUTH_KEYWORDS:
        if kw in check_text:
            return True
    return False

def extract_all_streams(item):
    """
    Lấy toàn bộ các luồng phát (HD, HD1, HD2, FHD, Nhà đài...)
    """
    streams = []
    
    # 1. Luồng chính
    main_url = item.get("source_live")
    if not main_url and item.get("stream_key"):
        main_url = f"https://lilive1.eu.cc/live/{item['stream_key']}/playlist.m3u8"
    
    if main_url:
        streams.append({
            "name": "",  # Luồng chuẩn gốc
            "url": main_url
        })

    # 2. Các luồng phụ/chất lượng khác trong thuộc tính 'servers', 'streams', 'sources' (nếu API có trả về)
    extra_servers = item.get("servers") or item.get("streams") or item.get("sources") or []
    for idx, s in enumerate(extra_servers, start=1):
        if isinstance(s, dict):
            s_url = s.get("url") or s.get("source") or s.get("link")
            s_name = s.get("name") or s.get("label") or f"HD{idx}"
        elif isinstance(s, str):
            s_url = s
            s_name = f"HD{idx}"
        else:
            continue
            
        if s_url and s_url != main_url:
            streams.append({
                "name": f"[{s_name}]",
                "url": s_url
            })
            
    return streams

def fetch_matches():
    try:
        response = requests.post(API_URL, json=PAYLOAD, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])
    except Exception as e:
        print(f"Lỗi kết nối API: {e}")
        return []

def build_m3u(matches):
    m3u_lines = [
        '#EXTM3U url-tvg="" tvg-shift="0"',
        '# Cập nhật tự động Phá Làng TV M3U Playlist'
    ]

    for item in matches:
        # Lọc bỏ giải trẻ (U15, U16, U17, U18, U19, U21...)
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

        # Lấy danh sách toàn bộ luồng phát
        streams = extract_all_streams(item)
        if not streams:
            continue

        # Định dạng ngày giờ VN & Biểu tượng
        formatted_time = parse_vietnam_time(start_date)
        icon = SPORT_ICONS.get(desc, "⚽")
        status_symbol = "🟢" if is_live else "⏳"
        
        match_name = f"{team1} vs {team2}" if (team1 and team2) else title_raw
        blv_text = f" ({blv})" if blv else ""

        # Xuất từng luồng phát thành 1 kênh riêng biệt trong M3U
        for st in streams:
            quality_tag = f" {st['name']}" if st['name'] else ""
            
            # Cấu trúc hiển thị giống 100% hình mẫu: 16:00 30/09 ⚽ Timor Leste vs Cambodia (LÝ LÊN LỬA) [HD2]
            display_title = f"{status_symbol} {formatted_time} {icon} {match_name}{blv_text}{quality_tag}"

            m3u_lines.append(f'#EXTINF:-1 tvg-id="{item.get("id", "")}" tvg-name="{display_title}" tvg-logo="{logo}" group-title="{league}", {display_title}')
            m3u_lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0')
            m3u_lines.append('#EXTVLCOPT:http-referrer=https://phalang1.tv/')
            m3u_lines.append(st["url"])

    return "\n".join(m3u_lines)

def main():
    print("Đang cào dữ liệu trận đấu từ Phá Làng TV...")
    matches = fetch_matches()
    print(f"Tổng số trận lấy về: {len(matches)}")
    
    m3u_content = build_m3u(matches)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)
        
    print(f"Đã xuất file M3U thành công: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
    
