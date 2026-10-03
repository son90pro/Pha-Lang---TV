import requests
from datetime import datetime, timezone, timedelta

API_URL = "https://api.plapi202624081158.com/matches/graph"

def parse_sport_category(desc):
    """
    Phân loại danh mục thể thao cho group-title và thiết lập thứ tự ưu tiên
    """
    desc_upper = (desc or "").upper()
    
    if any(k in desc_upper for k in ["FOOTBALL", "BÓNG ĐÁ", "SOCCER"]):
        return "⚽ BÓNG ĐÁ", "⚽", 1
    elif any(k in desc_upper for k in ["VOLLEYBALL", "BÓNG CHUYỀN"]):
        return "🏐 BÓNG CHUYỀN", "🏐", 2
    elif any(k in desc_upper for k in ["BASKETBALL", "BÓNG RỔ"]):
        return "🏀 BÓNG RỔ", "🏀", 3
    elif any(k in desc_upper for k in ["BADMINTON", "CẦU LÔNG"]):
        return "🏸 CẦU LÔNG", "🏸", 4
    elif any(k in desc_upper for k in ["BIDA", "BILLIARDS", "POOL", "SNOOKER"]):
        return "🎱 BIDA / BILLIARDS", "🎱", 5
    elif any(k in desc_upper for k in ["TABLE TENNIS", "BÓNG BÀN", "PING PONG"]):
        return "🏓 BÓNG BÀN", "🏓", 6
    elif any(k in desc_upper for k in ["TENNIS", "QUẦN VỢT"]):
        return "🎾 TENNIS", "🎾", 7
    else:
        return "🏆 THỂ THAO KHÁC", "🏆", 99

def format_time_vn(iso_str):
    """
    Chuyển đổi thời gian ISO từ API về Múi giờ Việt Nam (UTC+7)
    """
    try:
        if iso_str.endswith("Z"):
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(iso_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        
        # Chuyển đổi sang múi giờ UTC+7 (Việt Nam)
        vn_tz = timezone(timedelta(hours=7))
        dt_vn = dt.astimezone(vn_tz)
        return dt_vn.strftime("%H:%M %d/%m")
    except Exception:
        return "00:00 00/00"

def fetch_matches():
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
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
    
    processed_matches = []
    for item in matches:
        desc = item.get("desc", "")
        group_title, icon, priority = parse_sport_category(desc)
        item["_group_title"] = group_title
        item["_icon"] = icon
        item["_priority"] = priority
        processed_matches.append(item)
        
    # Sắp xếp: Ưu tiên Tab Bóng đá lên đầu -> Sau đó xếp theo thời gian thi đấu
    processed_matches.sort(key=lambda x: (x["_priority"], x.get("start_date", "")))

    m3u_content = ["#EXTM3U\n"]
    
    for item in processed_matches:
        is_live = item.get("is_live", False)
        live_tag = "🟢 " if is_live else ""
        time_str = format_time_vn(item.get("start_date", ""))
        sport_icon = item["_icon"]
        group_title = item["_group_title"]
        
        team_1 = item.get("team_1", "Team A")
        team_2 = item.get("team_2", "Team B")
        blv = item.get("blv") or "Unknown"
        logo = item.get("team_1_logo") or "https://sta.vnres.co/file/common/20261001/095833a8f2a539c9e27ac3170b659237.png"
        
        stream_key = item.get("stream_key")
        source_live = item.get("source_live")
        
        match_title_base = f"{time_str} {sport_icon} {team_1} vs {team_2}"
        
        # 1. Luồng FHD / Mặc định
        if stream_key:
            title_fhd = f"{live_tag}{match_title_base} ({blv}) [geo]"
            url_fhd = f"https://pull.digitalcdn.net/live/{stream_key}/index.m3u8"
            
            m3u_content.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group_title}" , {title_fhd}')
            m3u_content.append('#EXTVLCOPT:http-referrer=https://phalang.live/')
            m3u_content.append(f'{url_fhd}\n')

            # 2. Luồng Dự Phòng HD2
            title_hd2 = f"{live_tag}{match_title_base} ({blv}) (HD2) [geo]"
            url_hd2 = f"https://pull1.digitalcdn.net/live/{stream_key}/index.m3u8"
            
            m3u_content.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group_title}" , {title_hd2}')
            m3u_content.append('#EXTVLCOPT:http-referrer=https://phalang.live/')
            m3u_content.append(f'{url_hd2}\n')

        # 3. Luồng Nhà Đài / Source Live (nếu có)
        if source_live and source_live != "null":
            title_source = f"{live_tag}{match_title_base} (Nhà đài)"
            m3u_content.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group_title}" , {title_source}')
            m3u_content.append('#EXTVLCOPT:http-referrer=https://phalang.live/')
            m3u_content.append(f'{source_live}\n')

    with open("phalang.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_content))
    print("Đã cập nhật playlist m3u phân loại múi giờ VN thành công!")

if __name__ == "__main__":
    build_m3u()
    
