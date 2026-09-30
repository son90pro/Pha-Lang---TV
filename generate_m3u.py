import requests
import json
import re
import os
from datetime import datetime, timedelta

# Cấu hình API Phá Làng TV
API_URL = "https://api.plapi202624081158.com/matches/graph"
OUTPUT_FILE = "phalang.m3u"
GROUP_TITLE = "Phá Làng TV"  # Tất cả gom chung vào 1 danh mục theo mẫu

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://phalang1.tv",
    "Referer": "https://phalang1.tv/"
}

SPORT_ICONS = {
    "FOOTBALL": "⚽",
    "BONG DA": "⚽",
    "VOLLEYBALL": "🏐",
    "BONG CHUYEN": "🏐",
    "BASKETBALL": "🏀",
    "BONG RO": "🏀",
    "TENNIS": "🎾",
    "BADMINTON": "🏸",
    "TABLE TENNIS": "🏓",
    "BILLIARDS": "🎱",
    "SNOOKER": "🎱",
    "BOXING": "🥊",
    "MMA": "🥊",
    "ESPORTS": "🎮",
    "RACING": "🏎️"
}

def parse_vietnam_time(date_str):
    """Chuyển đổi ngày giờ về múi giờ Việt Nam (UTC+7) - Định dạng: HH:MM DD/MM"""
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

        dt_vn = dt + timedelta(hours=7)
        return dt_vn.strftime("%H:%M %d/%m")
    except Exception:
        return str(date_str)

def extract_all_streams(item):
    """Trích xuất đầy đủ tất cả các luồng phát / server phụ / link M3U8"""
    streams = []
    seen_urls = set()
    default_blv = (item.get("blv") or item.get("commentator") or "").strip()

    # Quét tất cả các mảng chứa server / luồng phát từ API
    extra_servers = []
    for key in ["servers", "streams", "sources", "play_urls", "links", "channels", "relate_matches"]:
        val = item.get(key)
        if isinstance(val, list) and val:
            extra_servers.extend(val)

    for s in extra_servers:
        s_url = None
        s_name = ""
        s_blv = default_blv
        is_geo = False
        
        if isinstance(s, dict):
            s_url = s.get("url") or s.get("source") or s.get("link") or s.get("m3u8") or s.get("play_url") or s.get("stream_url")
            s_name = s.get("name") or s.get("label") or s.get("title") or s.get("quality") or ""
            if s.get("blv") or s.get("commentator"):
                s_blv = (s.get("blv") or s.get("commentator") or "").strip()
            if s.get("is_geo") or s.get("geo") or "geo" in str(s_url).lower():
                is_geo = True
        elif isinstance(s, str):
            s_url = s

        if s_url and str(s_url).startswith("http") and s_url not in seen_urls:
            streams.append({
                "name": str(s_name).strip(),
                "url": str(s_url).strip(),
                "blv": s_blv,
                "is_geo": is_geo
            })
            seen_urls.add(s_url)

    # Quét các nguồn luồng chính trực tiếp
    main_urls = [
        item.get("source_live"),
        item.get("stream_url"),
        item.get("m3u8")
    ]
    if item.get("stream_key"):
        main_urls.append(f"https://lilive1.eu.cc/live/{item['stream_key']}/playlist.m3u8")

    for m_url in main_urls:
        if m_url and str(m_url).startswith("http") and m_url not in seen_urls:
            streams.insert(0, {
                "name": "",
                "url": str(m_url).strip(),
                "blv": default_blv,
                "is_geo": "geo" in str(m_url).lower() or bool(item.get("is_geo"))
            })
            seen_urls.add(m_url)

    return streams

def fetch_all_matches():
    """Tự động phân trang để lấy TOÀN BỘ trận đấu (không bị giới hạn 100 trận)"""
    all_matches = []
    seen_ids = set()
    page = 1
    
    while True:
        payload = {
            "limit": 100,
            "page": page,
            "order_asc": "start_date",
            "queries": [],
            "query_or": True
        }
        try:
            response = requests.post(API_URL, json=payload, headers=HEADERS, timeout=20)
            if response.status_code != 200:
                print(f"Trang {page}: Lỗi HTTP {response.status_code}")
                break
                
            res_json = response.json()
            data = res_json.get("data", [])
            
            if not data or not isinstance(data, list):
                break
                
            new_count = 0
            for item in data:
                if isinstance(item, dict):
                    m_id = item.get("id") or item.get("_id") or f"{item.get('title')}_{item.get('start_date')}"
                    if m_id not in seen_ids:
                        seen_ids.add(m_id)
                        all_matches.append(item)
                        new_count += 1
            
            print(f"Lấy thành công Trang {page}: +{new_count} trận (Tống cộng: {len(all_matches)} trận)")
            
            # Nếu số lượng trả về ít hơn 100 tức là đã hết trận
            if len(data) < 100:
                break
                
            page += 1
            if page > 10:  # Giới hạn an toàn tránh lặp vô tận
                break
                
        except Exception as e:
            print(f"Lỗi khi kết nối API ở trang {page}: {e}")
            break
            
    return all_matches

def build_m3u(matches):
    m3u_lines = [
        '#EXTM3U url-tvg="" tvg-shift="0"',
        '# Cập nhật tự động Phá Làng TV M3U Playlist'
    ]

    for item in matches:
        if not isinstance(item, dict):
            continue

        team1 = (item.get("team_1") or "").strip()
        team2 = (item.get("team_2") or "").strip()
        title_raw = (item.get("title") or "").strip()
        
        # Xác định tên trận
        if team1 and team2:
            match_name = f"{team1} vs {team2}"
        elif title_raw:
            match_name = title_raw
        else:
            continue

        desc = (item.get("desc") or "FOOTBALL").strip().upper()
        main_blv = (item.get("blv") or item.get("commentator") or "").strip()
        logo = item.get("team_1_logo") or item.get("team_2_logo") or item.get("logo") or ""
        start_date = item.get("start_date") or ""
        is_live = item.get("is_live", False)

        streams = extract_all_streams(item)
        if not streams:
            continue

        formatted_time = parse_vietnam_time(start_date)
        
        # Biểu tượng môn thể thao
        icon = "⚽"
        for key, val in SPORT_ICONS.items():
            if key in desc:
                icon = val
                break
                
        status_symbol = "🟢" if is_live else "🟡"

        for st in streams:
            # 1. Tên BLV (In hoa)
            blv_name = st.get("blv") or main_blv
            blv_tag = f"({blv_name.upper()})" if blv_name else "(Nhà đài)"

            # 2. Chất lượng / Server (vd: HD2, HD3)
            quality_str = st.get("name", "").strip()
            quality_tag = f" ({quality_str})" if quality_str else ""

            # 3. Thẻ [geo]
            geo_tag = " [geo]" if st.get("is_geo") else ""

            # Định dạng đúng chuẩn hình mẫu:
            # 🟡 23:00 30/09 ⚽ Eritrea vs South Africa (LÝ LINH LỰC) (HD2) [geo]
            display_title = f"{status_symbol} {formatted_time} {icon} {match_name} {blv_tag}{quality_tag}{geo_tag}".strip()

            m3u_lines.append(
                f'#EXTINF:-1 tvg-id="{item.get("id") or ""}" tvg-name="{display_title}" tvg-logo="{logo}" group-title="{GROUP_TITLE}", {display_title}'
            )
            m3u_lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0')
            m3u_lines.append('#EXTVLCOPT:http-referrer=https://phalang1.tv/')
            m3u_lines.append(st["url"])

    return "\n".join(m3u_lines)

def main():
    print("Đang cào dữ liệu toàn bộ các trận đấu từ Phá Làng TV...")
    matches = fetch_all_matches()
    
    if not matches:
        print("Không lấy được dữ liệu. Giữ nguyên file cũ để không gián đoạn dịch vụ.")
        return

    print(f"==> Tổng số trận đấu hợp lệ thu được: {len(matches)}")
    m3u_content = build_m3u(matches)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)
        
    print(f"Đã xuất thành công toàn bộ vào file: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
    
