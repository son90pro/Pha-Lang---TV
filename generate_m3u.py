import requests
import json
from datetime import datetime, timedelta

API_URL = "https://api.plapi202624081158.com/matches/graph"

def get_sport_icon(desc):
    desc = (desc or "").upper()
    if "FOOTBALL" in desc or "BÓNG ĐÁ" in desc:
        return "⚽"
    elif "VOLLEYBALL" in desc or "BÓNG CHUYỀN" in desc:
        return "🏐"
    elif "BASKETBALL" in desc or "BÓNG RỔ" in desc:
        return "🏀"
    elif "TENNIS" in desc or "QUẦN VỢT" in desc:
        return "🎾"
    return "⚽"

def format_time(iso_str):
    try:
        # Chuyển đổi định dạng giờ ISO sang HH:MM DD/MM
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        # Giả định giờ API đã ở UTC+7 hoặc điều chỉnh timezone nếu cần
        return dt.strftime("%H:%M %d/%m")
    except Exception:
        return "00:00 00/00"

def fetch_matches():
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    # Lấy tối đa 200 trận mới nhất / sắp diễn ra
    payload = {
        "limit": 200,
        "page": 1,
        "order_asc": "start_date",
        "queries": []
    }
    
    try:
        res = requests.post(API_URL, json=payload, headers=headers, timeout=15)
        if res.status_code == 200:
            return res.json().get("data", [])
    except Exception as e:
        print(f"Lỗi khi gọi API: {e}")
    return []

def build_m3u():
    matches = fetch_matches()
    m3u_content = ["#EXTM3U\n"]
    
    for item in matches:
        is_live = item.get("is_live", False)
        live_tag = "🟢 " if is_live else ""
        time_str = format_time(item.get("start_date", ""))
        sport_icon = get_sport_icon(item.get("desc", ""))
        
        team_1 = item.get("team_1", "Team A")
        team_2 = item.get("team_2", "Team B")
        blv = item.get("blv") or "Unknown"
        logo = item.get("team_1_logo") or "https://sta.vnres.co/file/common/20261001/095833a8f2a539c9e27ac3170b659237.png"
        
        stream_key = item.get("stream_key")
        source_live = item.get("source_live")
        
        match_title_base = f"{time_str} {sport_icon} {team_1} vs {team_2}"
        
        # 1. Luồng Chính (DigitalCDN - FHD/Full)
        if stream_key:
            title_fhd = f"{live_tag}{match_title_base} ({blv}) [geo]"
            url_fhd = f"https://pull.digitalcdn.net/live/{stream_key}/index.m3u8"
            
            m3u_content.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="Phá Làng TV" , {title_fhd}')
            m3u_content.append('#EXTVLCOPT:http-referrer=https://phalang.live/')
            m3u_content.append(f'{url_fhd}\n')

            # 2. Luồng Dự Phòng HD2
            title_hd2 = f"{live_tag}{match_title_base} ({blv}) (HD2) [geo]"
            url_hd2 = f"https://pull1.digitalcdn.net/live/{stream_key}/index.m3u8"
            
            m3u_content.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="Phá Làng TV" , {title_hd2}')
            m3u_content.append('#EXTVLCOPT:http-referrer=https://phalang.live/')
            m3u_content.append(f'{url_hd2}\n')

        # 3. Luồng Nhà Đài / Source Live (nếu có)
        if source_live and source_live != "null":
            title_source = f"{live_tag}{match_title_base} (Nhà đài)"
            m3u_content.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="Phá Làng TV" , {title_source}')
            m3u_content.append('#EXTVLCOPT:http-referrer=https://phalang.live/')
            m3u_content.append(f'{source_live}\n')

    with open("phalang.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_content))
    print("Đã cập nhật phalang.m3u thành công!")

if __name__ == "__main__":
    build_m3u()
    
