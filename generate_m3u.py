import requests
from datetime import datetime, timezone, timedelta

API_URL = "https://api.plapi202624081158.com/matches/graph"

def parse_sport_category(desc):
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

def parse_vn_time(iso_str):
    try:
        if not iso_str:
            return None
        if iso_str.endswith("Z"):
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(iso_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        vn_tz = timezone(timedelta(hours=7))
        return dt.astimezone(vn_tz)
    except Exception:
        return None

def fetch_matches():
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    # Nâng giới hạn lên 400 trận để đảm bảo quét sạch các trận hot/đang live và toàn bộ lịch ngày mai
    payload = {
        "limit": 400,
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
    
    # Múi giờ Việt Nam (UTC+7)
    now_vn = datetime.now(timezone(timedelta(hours=7)))
    
    # Mốc thời gian kết thúc: Hết 23:59:59 của ngày mai
    max_time = (now_vn + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    
    processed_matches = []
    
    for item in matches:
        dt_vn = parse_vn_time(item.get("start_date", ""))
        if not dt_vn:
            continue
            
        is_live = bool(item.get("is_live", False))
        is_end = bool(item.get("is_end", False)) or str(item.get("status", "")).lower() in ["finished", "ended", "2"]
        
        # 1. BỎ CÁC TRẬN ĐÃ DIỄN RA:
        # - Bỏ nếu API đánh dấu đã kết thúc
        if is_end:
            continue
            
        # - Bỏ nếu trận không đang live và thời gian bắt đầu đã vượt quá 110 phút (thời gian trung bình 1 trận bóng)
        if not is_live and (now_vn - dt_vn) > timedelta(minutes=110):
            continue

        # - Bỏ các trận vượt quá ngày mai
        if dt_vn >= max_time:
            continue

        # 2. XỬ LÝ TRẬN HOT & TÊN BLV PHÁ LÀNG TV:
        is_hot = bool(item.get("is_hot") or item.get("hot") or item.get("pin"))
        
        desc = item.get("desc", "")
        group_title, icon, priority = parse_sport_category(desc)
        
        raw_blv = item.get("blv")
        if not raw_blv or str(raw_blv).strip().lower() in ["unknown", "none", "null", ""]:
            blv_display = "Phá Làng TV"
        else:
            blv_clean = str(raw_blv).strip()
            blv_display = f"BLV {blv_clean}" if not blv_clean.upper().startswith("BLV") else blv_clean
        
        item["_dt_vn"] = dt_vn
        item["_time_str"] = dt_vn.strftime("%H:%M %d/%m")
        item["_group_title"] = group_title
        item["_icon"] = icon
        item["_priority"] = priority
        item["_blv_clean"] = blv_display
        item["_is_hot"] = is_hot
        item["_is_live"] = is_live
        
        processed_matches.append(item)
        
    # 3. SẮP XẾP ƯU TIÊN:
    # Môn thể thao -> Đang LIVE -> Trận HOT -> Thời gian thi đấu
    processed_matches.sort(key=lambda x: (
        x["_priority"], 
        not x["_is_live"], 
        not x["_is_hot"], 
        x["_dt_vn"]
    ))

    m3u_content = ["#EXTM3U\n"]
    
    for item in processed_matches:
        is_live = item["_is_live"]
        is_hot = item["_is_hot"]
        
        # Gắn biểu tượng LIVE (🟢) và HOT (🔥)
        prefix_tags = ""
        if is_live:
            prefix_tags += "🟢 "
        if is_hot:
            prefix_tags += "🔥 "
            
        time_str = item["_time_str"]
        sport_icon = item["_icon"]
        group_title = item["_group_title"]
        blv = item["_blv_clean"]
        
        team_1 = item.get("team_1", "Team A")
        team_2 = item.get("team_2", "Team B")
        logo = item.get("team_1_logo") or "https://sta.vnres.co/file/common/20261001/095833a8f2a539c9e27ac3170b659237.png"
        
        stream_key = item.get("stream_key")
        source_live = item.get("source_live")
        
        match_title_base = f"{time_str} {sport_icon} {team_1} vs {team_2}"
        
        # 1. Luồng FHD / Mặc định
        if stream_key:
            title_fhd = f"{prefix_tags}{match_title_base} ({blv}) [geo]"
            url_fhd = f"https://pull.digitalcdn.net/live/{stream_key}/index.m3u8"
            
            m3u_content.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group_title}" , {title_fhd}')
            m3u_content.append('#EXTVLCOPT:http-referrer=https://phalang.live/')
            m3u_content.append(f'{url_fhd}\n')

            # 2. Luồng Dự Phòng HD2
            title_hd2 = f"{prefix_tags}{match_title_base} ({blv}) (HD2) [geo]"
            url_hd2 = f"https://pull1.digitalcdn.net/live/{stream_key}/index.m3u8"
            
            m3u_content.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group_title}" , {title_hd2}')
            m3u_content.append('#EXTVLCOPT:http-referrer=https://phalang.live/')
            m3u_content.append(f'{url_hd2}\n')

        # 3. Luồng Nhà Đài / Source Live (nếu có)
        if source_live and str(source_live).strip().lower() not in ["null", "none", ""]:
            title_source = f"{prefix_tags}{match_title_base} (Nhà đài)"
            m3u_content.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group_title}" , {title_source}')
            m3u_content.append('#EXTVLCOPT:http-referrer=https://phalang.live/')
            m3u_content.append(f'{source_live}\n')

    with open("phalang.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_content))
    print(f"Đã cập nhật thành công {len(processed_matches)} trận đấu (đang live & sắp diễn ra đến hết ngày mai) vào phalang.m3u")

if __name__ == "__main__":
    build_m3u()
    
