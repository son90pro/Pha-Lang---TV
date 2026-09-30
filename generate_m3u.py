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

def parse_vietnam_datetime(date_val):
    """
    Chuyển đổi chuỗi/timestamp từ API về datetime giờ Việt Nam (UTC+7)
    Lưu ý: API Phá Làng trả về dạng chuỗi đã là giờ VN, KHÔNG cộng thêm 7 tiếng.
    """
    if not date_val:
        return None
    try:
        # 1. Trường hợp Unix Timestamp (Số)
        if isinstance(date_val, (int, float)) or (isinstance(date_val, str) and date_val.isdigit()):
            ts = float(date_val)
            if ts > 1e11:  # Mili-giây
                ts /= 1000.0
            dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt_utc.astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)

        val_str = str(date_val).strip()

        # 2. Chuỗi ISO có đuôi UTC (Z hoặc +00:00)
        if "Z" in val_str or "+00:00" in val_str:
            clean_iso = val_str.replace("Z", "+00:00").replace("T", " ")
            if "." in clean_iso:
                parts = clean_iso.split(".")
                clean_iso = parts[0] + ("+" + parts[1].split("+")[1] if "+" in parts[1] else "")
            dt_utc = datetime.fromisoformat(clean_iso)
            return dt_utc.astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)

        # 3. Chuỗi dạng YYYY-MM-DD HH:MM:SS (Đã là giờ VN chuẩn từ API)
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
    """Định dạng hiển thị: HH:MM DD/MM"""
    if not dt:
        return ""
    return dt.strftime("%H:%M %d/%m")

def is_today_or_tomorrow(dt_vn, is_live=False):
    """
    Lọc danh sách: Giữ lại tất cả trận LIVE + Toàn bộ trận thuộc HÔM NAY và NGÀY MAI
    """
    if is_live:
        return True
    if not dt_vn:
        return True  # Nếu không parse được giờ thì vẫn giữ lại để không bỏ sót

    now_vn = get_now_vietnam()
    today_date = now_vn.date()
    tomorrow_date = today_date + timedelta(days=1)

    # Loại bỏ các trận trong quá khứ đã trôi qua quá 2 tiếng
    if dt_vn < (now_vn - timedelta(hours=2)):
        return False

    return dt_vn.date() in (today_date, tomorrow_date)

def extract_all_streams(item):
    """Trích xuất danh sách luồng phát, BLV, Chất lượng và Thẻ Geo"""
    streams = []
    seen_urls = set()
    default_blv = (item.get("blv") or item.get("commentator") or item.get("mc") or "").strip()

    servers = []
    for key in ["servers", "streams", "sources", "play_urls", "links", "channels", "relate_matches", "links_play"]:
        val = item.get(key)
        if isinstance(val, list):
            servers.extend(val)

    for s in servers:
        s_url, s_name, s_blv, is_geo = None, "", default_blv, False

        if isinstance(s, dict):
            s_url = s.get("url") or s.get("source") or s.get("link") or s.get("m3u8") or s.get("play_url") or s.get("stream_url")
            s_name = s.get("name") or s.get("label") or s.get("title") or s.get("quality") or s.get("type") or ""
            if s.get("blv") or s.get("commentator"):
                s_blv = (s.get("blv") or s.get("commentator")).strip()
            if s.get("is_geo") or s.get("geo") or "geo" in str(s_url).lower() or "geo" in str(s_name).lower():
                is_geo = True
        elif isinstance(s, str):
            s_url = s

        if s_url and str(s_url).startswith("http") and s_url not in seen_urls:
            if "geo" in str(s_url).lower():
                is_geo = True
            streams.append({
                "name": str(s_name).strip(),
                "url": str(s_url).strip(),
                "blv": s_blv,
                "is_geo": is_geo
            })
            seen_urls.add(s_url)

    # Lấy các link stream ở cấp root
    for key in ["source_live", "stream_url", "m3u8", "link", "play_url", "url"]:
        u = item.get(key)
        if u and str(u).startswith("http") and u not in seen_urls:
            streams.append({
                "name": "",
                "url": str(u).strip(),
                "blv": default_blv,
                "is_geo": "geo" in str(u).lower() or bool(item.get("is_geo"))
            })
            seen_urls.add(u)

    if item.get("stream_key"):
        sk_url = f"https://lilive1.eu.cc/live/{item['stream_key']}/playlist.m3u8"
        if sk_url not in seen_urls:
            streams.append({
                "name": "",
                "url": sk_url,
                "blv": default_blv,
                "is_geo": bool(item.get("is_geo"))
            })
            seen_urls.add(sk_url)

    return streams

def unpack_api_data(res_json):
    """Bóc tách mảng danh sách trận đấu từ JSON API"""
    if isinstance(res_json, list):
        return res_json
    if isinstance(res_json, dict):
        d = res_json.get("data")
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            for sub_key in ["items", "rows", "matches", "list", "data"]:
                if isinstance(d.get(sub_key), list):
                    return d.get(sub_key)
        for key in ["items", "rows", "matches", "list"]:
            if isinstance(res_json.get(key), list):
                return res_json.get(key)
    return []

def fetch_all_matches():
    """Lấy dữ liệu toàn bộ trận đấu từ Phá Làng TV"""
    all_matches = []
    seen_ids = set()

    def add_items(data_list):
        for item in data_list:
            if isinstance(item, dict):
                m_id = item.get("id") or item.get("_id") or f"{item.get('title')}_{item.get('start_date')}"
                if m_id not in seen_ids:
                    seen_ids.add(m_id)
                    all_matches.append(item)

    # 1. Gọi các endpoint REST
    for ep in ["", "/live", "/hot", "/today", "/upcoming", "/schedule"]:
        try:
            res = requests.get(f"{API_BASE}{ep}", headers=HEADERS, timeout=10)
            if res.status_code == 200:
                add_items(unpack_api_data(res.json()))
        except Exception:
            pass

    # 2. Gọi Graph API phân trang
    for page in range(1, 10):
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
                items = unpack_api_data(res.json())
                add_items(items)
                if not items or len(items) < 100:
                    break
            else:
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

        dt_vn = parse_vietnam_datetime(item.get("start_date") or item.get("time") or item.get("match_time"))
        is_live = bool(item.get("is_live"))
        is_ended = bool(item.get("is_ended")) or str(item.get("status")).lower() in ["ended", "finished", "3", "done"]

        # Bỏ qua các trận đã kết thúc hẳn
        if is_ended:
            continue

        # Lọc chỉ lấy hôm nay và ngày mai (hoặc trận đang Live)
        if not is_today_or_tomorrow(dt_vn, is_live):
            continue

        streams = extract_all_streams(item)
        if not streams:
            continue

        team1 = (item.get("team_1") or item.get("home_team") or "").strip()
        team2 = (item.get("team_2") or item.get("away_team") or "").strip()
        title_raw = (item.get("title") or item.get("name") or "").strip()

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

    # SẮP XẾP: Trận LIVE (🟢) lên đầu -> Các trận tiếp theo (🟡) sắp xếp tăng dần theo Thời gian + Ngày tháng
    processed_matches.sort(
        key=lambda x: (
            0 if x["is_live"] else 1,
            x["dt_vn"] if x["dt_vn"] else datetime.max
        )
    )

    total_channels = 0
    for m in processed_matches:
        item = m["item"]
        match_name = m["match_name"]
        is_live = m["is_live"]
        streams = m["streams"]
        dt_vn = m["dt_vn"]

        desc = (item.get("desc") or item.get("category") or "FOOTBALL").strip().upper()
        main_blv = (item.get("blv") or item.get("commentator") or item.get("mc") or "").strip()
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
            quality_tag = f" ({quality_str})" if quality_str and quality_str.upper() not in ["MẶC ĐỊNH", "DEFAULT"] else ""

            geo_tag = " [geo]" if st.get("is_geo") else ""

            # Ghép tên hiển thị chuẩn theo mẫu ảnh người dùng
            display_title = f"{status_symbol} {formatted_time} {icon} {match_name} {blv_tag}{quality_tag}{geo_tag}".strip()
            display_title = re.sub(r'\s+', ' ', display_title)

            m3u_lines.append(
                f'#EXTINF:-1 tvg-id="{item.get("id") or ""}" tvg-name="{display_title}" tvg-logo="{logo}" group-title="{GROUP_TITLE}", {display_title}'
            )
            m3u_lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0')
            m3u_lines.append('#EXTVLCOPT:http-referrer=https://phalang1.tv/')
            m3u_lines.append(st["url"])
            total_channels += 1

    return "\n".join(m3u_lines), total_channels

def main():
    print("Đang cào dữ liệu trận đấu hôm nay & ngày mai từ Phá Làng TV...")
    matches = fetch_all_matches()
    
    m3u_content, total_channels = build_m3u(matches)
    
    # Luôn ghi file ra disk để GitHub Workflow không bị lỗi missing file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)
        
    print(f"Đã cập nhật thành công {total_channels} luồng vào file: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
    
