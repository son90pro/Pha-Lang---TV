import requests
import json
import re
import os
from datetime import datetime, timedelta, timezone

# Cấu hình API Phá Làng TV
API_URL = "https://api.plapi202624081158.com/matches/graph"
API_BASE = "https://api.plapi202624081158.com/matches"
OUTPUT_FILE = "phalang.m3u"
GROUP_TITLE = "Phá Làng TV"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": "https://phalang1.tv",
    "Referer": "https://phalang1.tv/"
}

SPORT_ICONS = {
    "FOOTBALL": "⚽", "BONG DA": "⚽",
    "VOLLEYBALL": "🏐", "BONG CHUYEN": "🏐",
    "BASKETBALL": "🏀", "BONG RO": "🏀",
    "TENNIS": "🎾", "BADMINTON": "🏸",
    "TABLE TENNIS": "🏓", "BILLIARDS": "🎱",
    "SNOOKER": "🎱", "BOXING": "🥊",
    "MMA": "🥊", "ESPORTS": "🎮", "RACING": "🏎️"
}

def get_now_vietnam():
    """Lấy thời gian hiện tại theo múi giờ Việt Nam (UTC+7)"""
    vn_tz = timezone(timedelta(hours=7))
    return datetime.now(vn_tz).replace(tzinfo=None)

def parse_vietnam_datetime(date_str):
    """Chuyển đổi chuỗi ngày giờ API về object datetime theo múi giờ Việt Nam (UTC+7)"""
    if not date_str:
        return None
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
        if dt:
            return dt + timedelta(hours=7)
    except Exception:
        pass
    return None

def format_time_str(dt):
    """Định dạng hiển thị: HH:MM DD/MM"""
    if not dt:
        return ""
    return dt.strftime("%H:%M %d/%m")

def is_match_past_or_ended(item, dt_vn):
    """
    Kiểm tra xem trận đấu đã kết thúc hoặc đã trôi qua giờ đá chưa.
    """
    is_live = bool(item.get("is_live"))
    
    # 1. Đang LIVE -> Giữ lại 100%
    if is_live:
        return False

    # 2. Đã đánh dấu kết thúc trong API -> Loại bỏ
    if item.get("is_ended") or item.get("status") in ["ended", "finished", "3", 3]:
        return True
    
    # 3. Trận không LIVE và đã trôi qua quá 15 phút so với giờ bắt đầu -> Loại bỏ (đã đá xong hoặc hủy)
    if dt_vn:
        now_vn = get_now_vietnam()
        if dt_vn < (now_vn - timedelta(minutes=15)):
            return True
            
    return False

def is_today_or_tomorrow(dt_vn, is_live=False):
    """Kiểm tra trận đấu có thuộc Hôm Nay hoặc Ngày Mai hay không"""
    if is_live:
        return True
    if not dt_vn:
        return False

    now_vn = get_now_vietnam()
    today_date = now_vn.date()
    tomorrow_date = today_date + timedelta(days=1)

    return dt_vn.date() in (today_date, tomorrow_date)

def extract_all_streams(item):
    """Trích xuất đầy đủ tất cả các luồng phát / server phụ / link M3U8"""
    streams = []
    seen_urls = set()
    default_blv = (item.get("blv") or item.get("commentator") or "").strip()

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
    """Quét danh sách trận đấu từ API"""
    all_matches = []
    seen_ids = set()

    def add_items(data_list):
        count = 0
        if not isinstance(data_list, list):
            return count
        for item in data_list:
            if isinstance(item, dict):
                m_id = item.get("id") or item.get("_id") or f"{item.get('title')}_{item.get('start_date')}"
                if m_id not in seen_ids:
                    seen_ids.add(m_id)
                    all_matches.append(item)
                    count += 1
        return count

    # 1. Endpoint Live / Hot / Today
    for ep in ["/live", "/hot", "/today"]:
        try:
            res = requests.get(f"{API_BASE}{ep}", headers=HEADERS, timeout=10)
            if res.status_code == 200:
                d = res.json().get("data", [])
                add_items(d)
        except Exception:
            pass

    # 2. Graph API (Trận Live)
    for page in range(1, 4):
        payload = {
            "limit": 100,
            "page": page,
            "order_desc": "is_live",
            "queries": [],
            "query_or": True
        }
        try:
            res = requests.post(API_URL, json=payload, headers=HEADERS, timeout=15)
            if res.status_code == 200:
                data = res.json().get("data", [])
                add_items(data)
                if len(data) < 100:
                    break
        except Exception:
            break

    # 3. Graph API (Thời gian)
    for page in range(1, 5):
        payload = {
            "limit": 100,
            "page": page,
            "order_asc": "start_date",
            "queries": [],
            "query_or": True
        }
        try:
            res = requests.post(API_URL, json=payload, headers=HEADERS, timeout=15)
            if res.status_code == 200:
                data = res.json().get("data", [])
                add_items(data)
                if len(data) < 100:
                    break
        except Exception:
            break

    return all_matches

def build_m3u(matches):
    m3u_lines = [
        '#EXTM3U url-tvg="" tvg-shift="0"',
        '# Cập nhật tự động Phá Làng TV M3U Playlist'
    ]

    processed_matches = []

    for item in matches:
        if not isinstance(item, dict):
            continue

        dt_vn = parse_vietnam_datetime(item.get("start_date"))
        is_live = bool(item.get("is_live"))

        # 1. Loại bỏ các trận đã kết thúc hoặc đã trôi qua thời gian thi đấu mà không LIVE
        if is_match_past_or_ended(item, dt_vn):
            continue

        # 2. Chỉ giữ lại trận thuộc Hôm nay hoặc Ngày mai (hoặc đang LIVE)
        if not is_today_or_tomorrow(dt_vn, is_live):
            continue

        streams = extract_all_streams(item)
        if not streams:
            continue

        team1 = (item.get("team_1") or "").strip()
        team2 = (item.get("team_2") or "").strip()
        title_raw = (item.get("title") or "").strip()

        if team1 and team2:
            match_name = f"{team1} vs {team2}"
        elif title_raw:
            match_name = title_raw
        else:
            continue

        processed_matches.append({
            "item": item,
            "match_name": match_name,
            "dt_vn": dt_vn,
            "is_live": is_live,
            "streams": streams
        })

    # Sắp xếp: Ưu tiên trận LIVE (🟢) lên đầu, tiếp theo là các trận sắp diễn ra (🟡) theo thời gian
    processed_matches.sort(
        key=lambda x: (
            0 if x["is_live"] else 1,
            x["dt_vn"] if x["dt_vn"] else datetime.max
        )
    )

    for m in processed_matches:
        item = m["item"]
        match_name = m["match_name"]
        is_live = m["is_live"]
        streams = m["streams"]
        dt_vn = m["dt_vn"]

        desc = (item.get("desc") or "FOOTBALL").strip().upper()
        main_blv = (item.get("blv") or item.get("commentator") or "").strip()
        logo = item.get("team_1_logo") or item.get("team_2_logo") or item.get("logo") or ""
        formatted_time = format_time_str(dt_vn)

        icon = "⚽"
        for key, val in SPORT_ICONS.items():
            if key in desc:
                icon = val
                break

        status_symbol = "🟢" if is_live else "🟡"

        for st in streams:
            blv_name = st.get("blv") or main_blv
            blv_tag = f"({blv_name.upper()})" if blv_name else "(Nhà đài)"

            quality_str = st.get("name", "").strip()
            quality_tag = f" ({quality_str})" if quality_str else ""

            geo_tag = " [geo]" if st.get("is_geo") else ""

            display_title = f"{status_symbol} {formatted_time} {icon} {match_name} {blv_tag}{quality_tag}{geo_tag}".strip()

            m3u_lines.append(
                f'#EXTINF:-1 tvg-id="{item.get("id") or ""}" tvg-name="{display_title}" tvg-logo="{logo}" group-title="{GROUP_TITLE}", {display_title}'
            )
            m3u_lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0')
            m3u_lines.append('#EXTVLCOPT:http-referrer=https://phalang1.tv/')
            m3u_lines.append(st["url"])

    return "\n".join(m3u_lines)

def main():
    print("Đang cào dữ liệu trận đấu từ Phá Làng TV...")
    matches = fetch_all_matches()
    
    if not matches:
        print("Không lấy được dữ liệu. Giữ nguyên file cũ để không gián đoạn dịch vụ.")
        return

    m3u_content = build_m3u(matches)
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)
        
    print(f"Đã xuất thành công danh sách M3U vào file: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
    
