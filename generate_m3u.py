import json
import os
import re
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_DOMAINS = [
    "https://api.plapi202624081158.com",
    "https://api.phalang.tv",
    "https://api.phalang1.tv",
    "https://api.phalang.net"
]

OUTPUT_FILE = "phalang.m3u"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Origin": "https://phalang.live",
    "Referer": "https://phalang.live/"
}

GROUP_ORDER = [
    "Bóng Đá",
    "Bóng Chuyền",
    "Bóng Rổ",
    "Cầu Lông",
    "Quần Vợt (Tennis)",
    "Bida (Billiards)",
    "Bóng Bàn",
    "Thể Thao Điện Tử",
    "Đua Xe",
    "Thể Thao Khác"
]

SPORT_MAPPING = {
    "FOOTBALL": {"group": "Bóng Đá", "icon": "⚽"},
    "BONG DA": {"group": "Bóng Đá", "icon": "⚽"},
    "SOCCER": {"group": "Bóng Đá", "icon": "⚽"},
    "VOLLEYBALL": {"group": "Bóng Chuyền", "icon": "🏐"},
    "BONG CHUYEN": {"group": "Bóng Chuyền", "icon": "🏐"},
    "BASKETBALL": {"group": "Bóng Rổ", "icon": "🏀"},
    "BONG RO": {"group": "Bóng Rổ", "icon": "🏀"},
    "TENNIS": {"group": "Quần Vợt (Tennis)", "icon": "🎾"},
    "BADMINTON": {"group": "Cầu Lông", "icon": "🏸"},
    "CAU LONG": {"group": "Cầu Lông", "icon": "🏸"},
    "TABLE TENNIS": {"group": "Bóng Bàn", "icon": "🏓"},
    "BONG BAN": {"group": "Bóng Bàn", "icon": "🏓"},
    "BILLIARDS": {"group": "Bida (Billiards)", "icon": "🎱"},
    "POOL": {"group": "Bida (Billiards)", "icon": "🎱"},
    "ESPORTS": {"group": "Thể Thao Điện Tử", "icon": "🎮"},
    "GAME": {"group": "Thể Thao Điện Tử", "icon": "🎮"},
    "RACING": {"group": "Đua Xe", "icon": "🏎️"},
    "F1": {"group": "Đua Xe", "icon": "🏎️"}
}

def parse_and_convert_to_vn_time(date_val):
    if not date_val:
        return None
    try:
        val_str = str(date_val).strip().replace("T", " ")
        if "." in val_str:
            val_str = val_str.split(".")[0]
        
        dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(val_str, fmt)
                break
            except ValueError:
                pass
        
        if dt:
            return dt + timedelta(hours=7)
    except Exception:
        pass
    return None

def format_time_str(dt):
    if not dt:
        return ""
    return dt.strftime("%H:%M %d/%m")

def get_sport_info(desc, title=""):
    text_check = f"{desc} {title}".upper()
    for key, info in SPORT_MAPPING.items():
        if key in text_check:
            return info["group"], info["icon"]
    return "Thể Thao Khác", "🏆"

def is_valid_time_window(dt_vn):
    if not dt_vn:
        return True
    
    tz_vn = timezone(timedelta(hours=7))
    now_vn = datetime.now(tz_vn).replace(tzinfo=None)
    
    today_start = now_vn.replace(hour=0, minute=0, second=0, microsecond=0)
    day_after_tomorrow_end = today_start + timedelta(days=2) - timedelta(seconds=1)
    
    if dt_vn < (now_vn - timedelta(hours=3)):
        return False
    if dt_vn > day_after_tomorrow_end:
        return False
        
    return True

def fetch_match_detail(match_id):
    """Lấy chi tiết trận đấu từ API để bóc tách mảng servers chứa link BLV tiếng Việt"""
    for base_api in API_DOMAINS:
        url = f"{base_api}/matches/detail/{match_id}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=5, verify=False)
            if res.status_code == 200:
                res_json = res.json()
                if isinstance(res_json, dict):
                    data = res_json.get("data")
                    if isinstance(data, dict) and data:
                        return data
                    elif "servers" in res_json or "sources" in res_json:
                        return res_json
        except Exception:
            continue
    return {}

def fetch_matches_by_post():
    all_matches = []
    seen_ids = set()

    payload = {
        "limit": 100,
        "page": 1,
        "order_asc": "start_date",
        "queries": [],
        "query_or": True
    }

    session = requests.Session()

    for base_api in API_DOMAINS:
        url = f"{base_api}/matches/graph"
        for page in range(1, 10):
            payload["page"] = page
            try:
                res = session.post(url, headers=HEADERS, json=payload, timeout=10, verify=False)
                if res.status_code == 200:
                    res_json = res.json()
                    data = res_json.get("data", [])
                    if isinstance(data, list) and len(data) > 0:
                        for item in data:
                            m_id = item.get("id")
                            if m_id and m_id not in seen_ids:
                                seen_ids.add(m_id)
                                all_matches.append(item)
                        print(f" -> Lấy thành công Page {page} từ {base_api} ({len(data)} trận)")
                    else:
                        break
            except Exception as e:
                print(f" -> Lỗi gọi API {url}: {e}")
                break

        if len(all_matches) > 0:
            break

    if all_matches:
        print(f"=== Đang cào chi tiết luồng cho {len(all_matches)} trận đấu... ===")
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_match = {executor.submit(fetch_match_detail, item["id"]): item for item in all_matches if item.get("id")}
            for future in as_completed(future_to_match):
                item = future_to_match[future]
                try:
                    detail = future.result()
                    item["_detail"] = detail
                except Exception:
                    item["_detail"] = {}

    return all_matches

def process_streams_for_match(item, detail_item):
    """Bóc tách chính xác link BLV Tiếng Việt (DigitalCDN) và link Nhà đài (Lilive)"""
    servers = []
    if isinstance(detail_item, dict):
        servers = detail_item.get("servers") or detail_item.get("sources") or detail_item.get("streams") or []
    if not servers and isinstance(item, dict):
        servers = item.get("servers") or item.get("sources") or []

    main_blv = str(detail_item.get("blv") or item.get("blv") or "").strip()
    stream_key = str(detail_item.get("stream_key") or item.get("stream_key") or "").strip()

    result_streams = []
    seen_urls = set()

    # 1. Trích xuất từ mảng servers chuẩn của API Detail
    if isinstance(servers, list) and len(servers) > 0:
        for s in servers:
            if not isinstance(s, dict):
                continue
            s_url = s.get("url") or s.get("source") or s.get("link") or s.get("m3u8")
            s_name = str(s.get("name") or s.get("label") or "").strip()
            s_blv = str(s.get("blv") or "").strip()
            is_geo = bool(s.get("is_geo", True))

            if s_url and str(s_url).startswith("http") and s_url not in seen_urls:
                seen_urls.add(s_url)

                blv_curr = s_blv if s_blv else main_blv
                is_nhadai = ("nhà đài" in s_name.lower() or "nha dai" in s_name.lower() or 
                             "nhà đài" in blv_curr.lower() or "nha dai" in blv_curr.lower())

                if is_nhadai:
                    tag = "(Nhà đài)"
                else:
                    blv_tag = f"({blv_curr})" if blv_curr else ""
                    hd2_tag = " (HD2)" if "hd2" in s_name.lower() else ""
                    geo_tag = " [geo]" if is_geo else ""
                    tag = f"{blv_tag}{hd2_tag}{geo_tag}".strip()

                result_streams.append({
                    "url": str(s_url).strip(),
                    "tag": tag,
                    "blv": blv_curr
                })

    # 2. Bổ sung luồng BLV nếu trong servers thiếu
    source_live = str(detail_item.get("source_live") or item.get("source_live") or "").strip()
    has_digitalcdn = any("digitalcdn.net" in st["url"] for st in result_streams)

    if not has_digitalcdn and source_live and source_live.startswith("http"):
        blv_tag = f"({main_blv}) [geo]" if main_blv else "[geo]"
        if source_live not in seen_urls:
            seen_urls.add(source_live)
            result_streams.insert(0, {
                "url": source_live,
                "tag": blv_tag,
                "blv": main_blv
            })

    # 3. Nhân bản luồng HD2 từ Luồng BLV chính (thay pull. -> pull1.)
    blv_digitalcdn_streams = [st for st in result_streams if "pull.digitalcdn.net" in st["url"]]
    for st in blv_digitalcdn_streams:
        hd2_url = st["url"].replace("pull.digitalcdn.net", "pull1.digitalcdn.net")
        if hd2_url not in seen_urls:
            seen_urls.add(hd2_url)
            hd2_tag = f"({st['blv']}) (HD2) [geo]" if st['blv'] else "(HD2) [geo]"
            result_streams.append({
                "url": hd2_url,
                "tag": hd2_tag,
                "blv": st['blv']
            })

    # 4. Thêm luồng Nhà đài từ stream_key
    has_nhadai = any("(Nhà đài)" in st["tag"] or "lilive1.eu.cc" in st["url"] for st in result_streams)
    if not has_nhadai and stream_key:
        nhadai_url = f"https://lilive1.eu.cc/live/{stream_key}/playlist.m3u8"
        if nhadai_url not in seen_urls:
            seen_urls.add(nhadai_url)
            result_streams.append({
                "url": nhadai_url,
                "tag": "(Nhà đài)",
                "blv": ""
            })

    return result_streams, main_blv

def build_m3u(matches):
    m3u_lines = ['#EXTM3U']

    grouped_items = {grp: [] for grp in GROUP_ORDER}
    total_channels = 0

    tz_vn = timezone(timedelta(hours=7))
    now_vn = datetime.now(tz_vn).replace(tzinfo=None)

    for item in matches:
        if not isinstance(item, dict):
            continue

        dt_vn = parse_and_convert_to_vn_time(item.get("start_date"))
        if not is_valid_time_window(dt_vn):
            continue

        detail_item = item.get("_detail") or {}

        team1 = str(item.get("team_1") or "").strip()
        team2 = str(item.get("team_2") or "").strip()
        title_raw = str(item.get("title") or "").strip()

        if team1 and team2:
            match_name = f"{team1} vs {team2}"
        elif title_raw:
            match_name = title_raw.replace(" - ", " vs ")
        else:
            continue

        desc = str(item.get("desc") or "").strip()
        group_category, icon = get_sport_info(desc, match_name)

        streams, main_blv = process_streams_for_match(item, detail_item)
        if not streams:
            continue

        # Lọc bỏ trận Bóng Đá KHÔNG có BLV tiếng Việt
        has_web_blv = bool(main_blv and "nhà đài" not in main_blv.lower() and "nha dai" not in main_blv.lower())
        if group_category == "Bóng Đá" and not has_web_blv:
            continue

        logo = str(item.get("team_1_logo") or item.get("logo") or "").strip()
        formatted_time = format_time_str(dt_vn)

        is_live = False
        if dt_vn and (dt_vn <= now_vn <= dt_vn + timedelta(hours=2, minutes=30)):
            is_live = True
        live_prefix = "🟢 " if is_live else ""

        for st in streams:
            display_title = f"{live_prefix}{formatted_time} {icon} {match_name} {st['tag']}".strip()
            display_title = re.sub(r'\s+', ' ', display_title)

            channel_entry = [
                f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group_category}" , {display_title}',
                '#EXTVLCOPT:http-referrer=https://phalang.live/',
                st["url"]
            ]

            if group_category in grouped_items:
                grouped_items[group_category].append(channel_entry)
            else:
                grouped_items["Thể Thao Khác"].append(channel_entry)

            total_channels += 1

    for grp in GROUP_ORDER:
        entries = grouped_items.get(grp, [])
        for entry in entries:
            m3u_lines.extend(entry)

    return "\n".join(m3u_lines), total_channels

def main():
    print("=== Bắt đầu cào dữ liệu Phá Làng TV ===")
    matches = fetch_matches_by_post()
    print(f"Tổng số trận cào được: {len(matches)}")

    m3u_content, total_channels = build_m3u(matches)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print(f"=== Xuất thành công {total_channels} luồng vào file: {OUTPUT_FILE} ===")

if __name__ == "__main__":
    main()
    
