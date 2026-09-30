import requests
import json
from datetime import datetime

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

# Payload lấy toàn bộ trận đấu (limit=100)
PAYLOAD = {
    "limit": 100,
    "page": 1,
    "order_asc": "start_date",
    "queries": [],
    "query_or": True
}

# Icon môn thể thao
SPORT_ICONS = {
    "FOOTBALL": "⚽",
    "VOLLEYBALL": "🏐",
    "BASKETBALL": "🏀",
    "TENNIS": "🎾",
    "BADMINTON": "🏸"
}

def format_date(date_str):
    """Chuyển đổi YYYY-MM-DD HH:MM:SS thành HH:MM DD/MM"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%H:%M %d/%m")
    except Exception:
        return date_str

def fetch_matches():
    try:
        response = requests.post(API_URL, json=PAYLOAD, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])
    except Exception as e:
        print(f"Lỗi khi kết nối API: {e}")
        return []

def build_m3u(matches):
    m3u_lines = [
        '#EXTM3U url-tvg="" tvg-shift="0"',
        '# Cập nhật tự động Phá Làng TV M3U Playlist'
    ]

    for item in matches:
        title_raw = item.get("title", "")
        team1 = item.get("team_1", "")
        team2 = item.get("team_2", "")
        league = item.get("league", "Phá Làng TV")
        desc = item.get("desc", "FOOTBALL").upper()
        blv = item.get("blv", "")
        logo = item.get("team_1_logo") or item.get("team_2_logo") or ""
        start_date = item.get("start_date", "")
        is_live = item.get("is_live", False)
        
        # Xác định link luồng phát
        stream_url = item.get("source_live")
        if not stream_url and item.get("stream_key"):
            stream_url = f"https://lilive1.eu.cc/live/{item['stream_key']}/playlist.m3u8"
            
        if not stream_url:
            continue

        # Định dạng thời gian & Biểu tượng
        formatted_time = format_date(start_date) if start_date else ""
        icon = SPORT_ICONS.get(desc, "⚽")
        status_symbol = "🟢" if is_live else "⏳"
        
        # Tên BLV
        blv_text = f" ({blv})" if blv else ""
        
        # Tạo tên kênh hiển thị chuẩn như mẫu TiviMate (Thời gian + Môn + Trận đấu + BLV)
        if team1 and team2:
            match_name = f"{team1} vs {team2}"
        else:
            match_name = title_raw
            
        display_title = f"{status_symbol} {formatted_time} {icon} {match_name}{blv_text}"

        # Thêm header VLC/TiviMate nếu cần Referer
        m3u_lines.append(f'#EXTINF:-1 tvg-id="{item.get("id", "")}" tvg-name="{display_title}" tvg-logo="{logo}" group-title="{league}", {display_title}')
        m3u_lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0')
        m3u_lines.append('#EXTVLCOPT:http-referrer=https://phalang1.tv/')
        m3u_lines.append(stream_url)

    return "\n".join(m3u_lines)

def main():
    print("Đang tải dữ liệu trận đấu...")
    matches = fetch_matches()
    print(f"Tìm thấy {len(matches)} trận đấu.")
    
    m3u_content = build_m3u(matches)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)
        
    print(f"Đã lưu playlist vào file: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
  
