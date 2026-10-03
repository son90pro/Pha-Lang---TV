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
    
    # Giờ hiện tại theo múi giờ Việt Nam (UTC+7)
    now_vn = datetime.now(timezone(timedelta(hours=7)))
    today_date = now_vn.date()
    tomorrow_date = today_date + timedelta(days=1)
    
    processed_matches = []
    
    for item in matches:
        # 1. LỌC BLV: Loại bỏ các trận không có BLV hoặc BLV là 'Unknown'
        blv = item.get("blv")
        if not blv or str(blv).strip().lower() in ["unknown", "none", "null", ""]:
            continue

        # 2. CHUYỂN ĐỔI MÚI GIỜ
        dt_vn = parse_vn_time(item.get("start_date", ""))
        if not dt_vn:
            continue
            
        match_date = dt_vn.date()
        is_live = item.get("is_live", False)
        
        # 3. LỌC NGÀY: Chỉ lấy các trận diễn ra trong HÔM NAY và NGÀY MAI
        if match_date < today_date or match_date > tomorrow_date:
            continue
            
        # 4. LỌC TRẬN ĐÃ KẾT THÚC:
        # Nếu trận không ở trạng thái Live và giờ bắt đầu đã qua quá 2.5 tiếng -> Ẩn khỏi playlist
        if not is_live and dt_vn < (now_vn - timedelta(hours=2, minutes=30)):
            continue

        desc = item.get("desc", "")
        group_title, icon, priority = parse_sport_category(desc)
        
        item["_dt_vn"] = dt_vn
        item["_time_str"] = dt_vn.strftime("%H:%M %d/%m")
        item["_group_title"] = group_title
        item["_icon"] = icon
        item["_priority"] = priority
        item["_blv_clean"] = str(blv).strip()
        
        processed_matches.append(item)
        
    # Sắp xếp: Ưu tiên Tab Bóng đá lên đầu -> Sau đó xếp theo thời gian đá
    processed_matches.sort(key=lambda x: (x["_priority"], x["_dt_vn"]))

    m3u_content = ["#EXTM3U\n"]
    
    for item in processed_matches:
        is_live = item.get("is_live", False)
        live_tag = "🟢 " if is_live else ""
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
        
        # Luồng FHD / Mặc định
        if stream_key:
            title_fhd = f"{live_tag}{match_title_base} ({blv}) [geo]"
            url_fhd = f"https://pull.digitalcdn.net/live/{stream_key}/index.m3u8"
            
            m3u_content.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group_title}" , {title_fhd}')
            m3u_content.append('#EXTVLCOPT:http-referrer=https://phalang.live/')
            m3u_content.append(f'{url_fhd}\n')

            # Luồng Dự Phòng HD2
            title_hd2 = f"{live_tag}{match_title_base} ({blv}) (HD2) [geo]"
            url_hd2 = f"https://pull1.digitalcdn.net/live/{stream_key}/index.m3u8"
            
            m3u_content.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group_title}" , {title_hd2}')
            m3u_content.append('#EXTVLCOPT:http-referrer=https://phalang.live/')
            m3u_content.append(f'{url_hd2}\n')

        # Luồng Nhà Đài / Source Live (nếu có)
        if source_live and source_live != "null":
            title_source = f"{live_tag}{match_title_base} (Nhà đài)"
            m3u_content.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group_title}" , {title_source}')
            m3u_content.append('#EXTVLCOPT:http-referrer=https://phalang.live/')
            m3u_content.append(f'{source_live}\n')

    with open("phalang.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(m3u_content))
    print(f"Đã xuất thành công {len(processed_matches)} trận đấu hợp lệ vào phalang.m3u")

if __name__ == "__main__":
    build_m3u()
    
