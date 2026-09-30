import json
import os
import re
from datetime import datetime, timedelta, timezone
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Danh sách API & Web Domain cập nhật mới nhất
API_DOMAINS = [
    "https://api.phalang.tv",
    "https://api.phalang1.tv",
    "https://api.plapi202624081158.com",
    "https://api.phalang.net",
    "https://api.phalang.live"
]

WEB_URLS = [
    "https://phalang1.tv",
    "https://phalang.tv",
    "https://phalang.live",
    "https://phalang.net"
]

OUTPUT_FILE = "phalang.m3u"
GROUP_TITLE = "Phá Làng TV"

# Headers giả lập thiết bị di động Việt Nam
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://phalang1.tv",
    "Referer": "https://phalang1.tv/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site"
}

SPORT_ICONS = {
    "FOOTBALL": "⚽", "BONG DA": "⚽",
    "VOLLEYBALL": "🏐", "BONG CHUYEN": "🏐",
    "BASKETBALL": "🏀", "BONG RO": "🏀",
    "TENNIS": "🎾", "BADMINTON": "🏸",
    "TABLE TENNIS": "🏓", "BILLIARDS": "🎱",
    "ESPORTS": "🎮"
}

def get_now_vietnam():
    vn_tz = timezone(timedelta(hours=7))
    return datetime.now(vn_tz).replace(tzinfo=None)

def parse_vietnam_datetime(date_val):
    if not date_val:
        return None
    try:
        if isinstance(date_val, (int, float)) or (isinstance(date_val, str) and str(date_val).isdigit()):
            ts = float(date_val)
            if ts > 1e11:
                ts /= 1000.0
            dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt_utc.astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)

        val_str = str(date_val).strip()
        if "Z" in val_str or "+00:00" in val_str:
            clean_iso = val_str.replace("Z", "+00:00").replace("T", " ")
            if "." in clean_iso:
                parts = clean_iso.split(".")
                clean_iso = parts[0] + ("+" + parts[1].split("+")[1] if "+" in parts[1] else "")
            dt_utc = datetime.fromisoformat(clean_iso)
            return dt_utc.astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)

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
    if not dt:
        return ""
    return dt.strftime("%H:%M %d/%m")

def extract_all_streams(item):
    streams = []
    seen_urls = set()
    default_blv = str(item.get("blv") or item.get("commentator") or item.get("mc") or "").strip()

    servers = []
    for key in ["servers", "streams", "sources", "play_urls", "links", "channels", "relate_matches", "links_play"]:
        val = item.get(key)
        if isinstance(val, list):
            servers.extend(val)

    for s in servers:
        s_url, s_name, s_blv, is_geo = None, "", default_blv, False

        if isinstance(s, dict):
            s_url = s.get("url") or s.get("source") or s.get("link") or s.get("m3u8") or s.get("play_url") or s.get("stream_url")
            s_name = str(s.get("name") or s.get("label") or s.get("title") or s.get("quality") or "").strip()
            if s.get("blv") or s.get("commentator"):
                s_blv = str(s.get("blv") or s.get("commentator")).strip()
            if s.get("is_geo") or "geo" in str(s_url).lower() or "geo" in str(s_name).lower():
                is_geo = True
        elif isinstance(s, str):
            s_url = s

        if s_url and str(s_url).startswith("http") and s_url not in seen_urls:
            streams.append({
                "name": s_name,
                "url": str(s_url).strip(),
                "blv": s_blv,
                "is_geo": is_geo
            })
            seen_urls.add(s_url)

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

def fetch_from_web_page():
    matches = []
    for web_url in WEB_URLS:
        try:
            res = requests.get(web_url, headers=HEADERS, timeout=10, verify=False)
            if res.status_code == 200:
                match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', res.text, re.DOTALL)
                if match:
                    json_data = json.loads(match.group(1))
                    props = json_data.get("props", {}).get("pageProps", {})
                    for key in ["matches", "matchList", "todayMatches", "liveMatches", "initialState", "data"]:
                        val = props.get(key)
                        if isinstance(val, list):
                            matches.extend(val)
                        elif isinstance(val, dict):
                            for sub in ["matches", "data", "rows"]:
                                if isinstance(val.get(sub), list):
                                    matches.extend(val.get(sub))

                if not matches:
                    json_matches = re.findall(r'(\{"id":".*?"team_1":.*?\})', res.text)
                    for jm in json_matches:
                        try:
                            matches.append(json.loads(jm))
                        except Exception:
                            pass

                if matches:
                    print(f" -> Cào Web thành công {len(matches)} trận từ: {web_url}")
                    break
        except Exception as e:
            print(f" -> Lỗi cào Web {web_url}: {e}")
    return matches

def fetch_all_matches():
    all_matches = []
    seen_ids = set()

    def add_items(data_list, source_name=""):
        count = 0
        if not isinstance(data_list, list):
            return
        for item in data_list:
            if isinstance(item, dict):
                m_id = item.get("id") or item.get("_id") or f"{item.get('title')}_{item.get('start_date')}"
                if m_id not in seen_ids:
                    seen_ids.add(m_id)
                    all_matches.append(item)
                    count += 1
        if source_name and count > 0:
            print(f" -> [{source_name}] Lấy {count} trận")

    for base_api in API_DOMAINS:
        for ep in ["/matches/live", "/matches/today", "/matches/upcoming", "/matches/hot", "/matches"]:
            url = f"{base_api}{ep}"
            try:
                res = requests.get(url, headers=HEADERS, timeout=6, verify=False)
                if res.status_code == 200:
                    add_items(unpack_api_data(res.json()), f"GET {ep}")
            except Exception:
                pass

        if len(all_matches) > 0:
            break

    if not all_matches:
        print("API bị chặn IP. Chuyển sang cào trực tiếp HTML Web...")
        web_matches = fetch_from_web_page()
        add_items(web_matches, "Web Scraper")

    return all_matches

def generate_fallback_channels():
    """Tạo kênh dự phòng trường hợp IP GitHub bị chặn hoàn toàn"""
    fallback_lines = []
    for i in range(1, 11):
        title = f"🟢 Kênh Trực Tiếp Phá Làng {i:02d} (Server Backup)"
        url = f"https://lilive1.eu.cc/live/phalang{i}/playlist.m3u8"
        fallback_lines.append(f'#EXTINF:-1 tvg-id="phalang_{i}" tvg-name="{title}" group-title="{GROUP_TITLE}", {title}')
        fallback_lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0')
        fallback_lines.append('#EXTVLCOPT:http-referrer=https://phalang1.tv/')
        fallback_lines.append(url)
    return "\n".join(fallback_lines), 10

def build_m3u(matches):
    m3u_lines = [
        '#EXTM3U url-tvg="" tvg-shift="0"',
        '# Cập nhật tự động Phá Làng TV M3U Playlist'
    ]

    processed_matches = []
    now_vn = get_now_vietnam()

    for item in matches:
        if not isinstance(item, dict):
            continue

        dt_vn = parse_vietnam_datetime(item.get("start_date") or item.get("time") or item.get("match_time"))
        is_live = bool(item.get("is_live"))
        is_ended = bool(item.get("is_ended")) or str(item.get("status", "")).lower() in ["ended", "finished", "3", "done"]

        if is_ended:
            continue

        if not is_live and dt_vn:
            if dt_vn < (now_vn - timedelta(hours=3)) or dt_vn > (now_vn + timedelta(hours=48)):
                continue

        streams = extract_all_streams(item)
        if not streams:
            continue

        team1 = str(item.get("team_1") or item.get("home_team") or "").strip()
        team2 = str(item.get("team_2") or item.get("away_team") or "").strip()
        title_raw = str(item.get("title") or item.get("name") or "").strip()

        match_name = f"{team1} vs {team2}" if (team1 and team2) else title_raw
        if not match_name:
            continue

        processed_matches.append({
            "item": item,
            "match_name": match_name,
            "dt_vn": dt_vn,
            "is_live": is_live,
            "streams": streams
        })

    processed_matches.sort(key=lambda x: (0 if x["is_live"] else 1, x["dt_vn"] if x["dt_vn"] else datetime.max))

    total_channels = 0
    for m in processed_matches:
        item = m["item"]
        match_name = m["match_name"]
        is_live = m["is_live"]
        streams = m["streams"]
        dt_vn = m["dt_vn"]

        desc = str(item.get("desc") or item.get("category") or "FOOTBALL").strip().upper()
        main_blv = str(item.get("blv") or item.get("commentator") or item.get("mc") or "").strip()
        logo = str(item.get("team_1_logo") or item.get("team_2_logo") or item.get("logo") or "").strip()
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
            quality_str = str(st.get("name") or "").strip()
            quality_tag = f" ({quality_str})" if quality_str and quality_str.upper() not in ["MẶC ĐỊNH", "DEFAULT"] else ""
            geo_tag = " [geo]" if st.get("is_geo") else ""

            display_title = f"{status_symbol} {formatted_time} {icon} {match_name} {blv_tag}{quality_tag}{geo_tag}".strip()
            display_title = re.sub(r'\s+', ' ', display_title)

            item_id = str(item.get("id") or "")
            m3u_lines.append(f'#EXTINF:-1 tvg-id="{item_id}" tvg-name="{display_title}" tvg-logo="{logo}" group-title="{GROUP_TITLE}", {display_title}')
            m3u_lines.append('#EXTVLCOPT:http-user-agent=Mozilla/5.0')
            m3u_lines.append('#EXTVLCOPT:http-referrer=https://phalang1.tv/')
            m3u_lines.append(st["url"])
            total_channels += 1

    if total_channels == 0:
        print("Không cào được trận nào do chặn IP. Khởi tạo danh sách luồng dự phòng Backup...")
        fb_content, fb_count = generate_fallback_channels()
        m3u_lines.append(fb_content)
        total_channels = fb_count

    return "\n".join(m3u_lines), total_channels

def main():
    print("=== Bắt đầu cào dữ liệu Phá Làng TV ===")
    matches = fetch_all_matches()
    print(f"Tổng số trận lấy được: {len(matches)}")

    m3u_content, total_channels = build_m3u(matches)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"=== Xuất thành công {total_channels} luồng vào file: {OUTPUT_FILE} ===")

if __name__ == "__main__":
    main()
        
