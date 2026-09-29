import time
import re
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

DOMAINS = [
    "https://phalang.live/",
    "https://phalang.tv/",
    "https://phalang1.tv/"
]
REFERER_URL = "https://phalang.live/"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phá Làng TV"
DEFAULT_LOGO = "https://flagcdn.com/w320/vn.png"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# DANH SÁCH TÊN BLV PHÁ LÀNG TV
KNOWN_BLVS = [
    "LÝ LINH LỰC", "LÝ LINH", "LÝ LÊN LỬA", "LÝ LA LÀNG", "LÝ BÒ", "LÝ THÔNG",
    "LÝ TƯỞNG", "LÝ BÉO", "LÝ ĐỨC", "LÝ LIỀU LĨNH", "LÝ LÀNG LÁ", "LÝ LẮC LÉO",
    "CHUỐI CHIÊN", "CHUỐI CHAO", "TRỐC", "CỦ CỐT", "THỎ", "GÀ", "SÁY"
]

LOGOS = {
    "north korea": "https://flagcdn.com/w320/kp.png", "triều tiên": "https://flagcdn.com/w320/kp.png",
    "iran": "https://flagcdn.com/w320/ir.png",
    "philippines": "https://flagcdn.com/w320/ph.png",
    "pakistan": "https://flagcdn.com/w320/pk.png",
    "indonesia": "https://flagcdn.com/w320/id.png",
    "china": "https://flagcdn.com/w320/cn.png", "trung quốc": "https://flagcdn.com/w320/cn.png",
    "vietnam": "https://flagcdn.com/w320/vn.png", "việt nam": "https://flagcdn.com/w320/vn.png",
    "thailand": "https://flagcdn.com/w320/th.png", "thái lan": "https://flagcdn.com/w320/th.png",
    "south korea": "https://flagcdn.com/w320/kr.png", "hàn quốc": "https://flagcdn.com/w320/kr.png",
    "australia": "https://flagcdn.com/w320/au.png", "úc": "https://flagcdn.com/w320/au.png",
    "japan": "https://flagcdn.com/w320/jp.png", "nhật bản": "https://flagcdn.com/w320/jp.png",
    "brazil": "https://flagcdn.com/w320/br.png"
}

SERVER_PRIORITY = {
    "HD1": 1, "FHD": 1, "SD": 1, "Nguồn 1": 1,
    "HD2": 2, "Nguồn 2": 2,
    "HD3": 3,
    "Nhà đài": 4
}

def clean_garbage_text(text: str) -> str:
    """Làm sạch triệt để các chữ rác UI/Menu/Kèo nhà cái"""
    if not text:
        return ""
    
    # Loại bỏ các từ rác giao diện web
    garbage_keywords = [
        "CHỦ NHÀ", "HÒA", "ĐỘI KHÁCH", "TRỰC TIẾP", "MÔ PHỎNG", "CHIA SẺ",
        "Phát trực tiếp", "Xem ngay", "Lịch thi đấu", "Tỷ lệ", "Kèo nhà cái",
        "XEM TRỰC TIẾP", "TRỰC TIẾP BÓNG ĐÁ"
    ]
    
    cleaned = text
    for kw in garbage_keywords:
        cleaned = re.sub(re.escape(kw), "", cleaned, flags=re.IGNORECASE)
        
    # Xóa toàn bộ ký tự xuống dòng, tab và khoảng trắng thừa
    cleaned = re.sub(r'[\r\n\t]+', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def extract_blv_from_text(text: str) -> str:
    """Trích xuất tên BLV chuẩn xác"""
    if not text:
        return ""
    text_upper = text.upper()
    
    for b in KNOWN_BLVS:
        if b in text_upper:
            return b

    m_bracket = re.search(r'\((LÝ\s+[^\)]+)\)', text_upper)
    if m_bracket:
        return m_bracket.group(1).strip()

    m_ly = re.search(r'\b(LÝ\s+[A-ZÀ-Ỹ0-9]{2,10})\b', text_upper)
    if m_ly:
        return m_ly.group(1).strip()
        
    return ""

def extract_clean_teams(text: str) -> str:
    """Tách tên 2 đội thi đấu dạng 'Đội A vs Đội B' chuẩn sạch"""
    cleaned = clean_garbage_text(text)
    
    # Tìm mẫu "A vs B"
    match = re.search(r'([A-Za-z0-9\sÀ-ỹ\.\-]{2,30})\s+vs\s+([A-Za-z0-9\sÀ-ỹ\.\-]{2,30})', cleaned, re.IGNORECASE)
    if match:
        t1 = clean_garbage_text(match.group(1))
        t2 = clean_garbage_text(match.group(2))
        return f"{t1} vs {t2}"
    return ""

def get_team_logo(teams_str: str, raw_card_logo: str = "") -> str:
    t_lower = teams_str.lower()
    for key, url in LOGOS.items():
        if key in t_lower:
            return url
    if raw_card_logo and raw_card_logo.startswith("http"):
        return raw_card_logo
    return DEFAULT_LOGO

def scrape_match_detail(context, match_url: str, card_blv: str = ""):
    page = context.new_page()
    captured_streams = []
    m3u8_log = []

    def handle_request(req):
        url = req.url
        if ".m3u8" in url and any(k in url for k in ["index", "playlist", "live", "stream", "chunk", "hls", "master", "m3u8"]):
            m3u8_log.append(url)

    page.on("request", handle_request)

    teams_title = ""
    blv_name = card_blv
    match_time = ""
    match_date = ""

    try:
        print(f"[*] Cào trang chi tiết: {match_url}")
        page.goto(match_url, timeout=25000, wait_until="domcontentloaded")
        time.sleep(2.5) # Chờ tải player & lấy m3u8 HD1

        initial_m3u8 = m3u8_log[-1] if m3u8_log else ""

        detail_data = page.evaluate('''() => {
            const bodyText = document.body.innerText || '';
            let blv = '', timeStr = '', dateStr = '';

            const timeMatch = bodyText.match(/(\\d{1,2}:\\d{2})\\s+(\\d{1,2}\\/\\d{1,2})/);
            if (timeMatch) {
                timeStr = timeMatch[1];
                dateStr = timeMatch[2];
            }

            const allEls = document.querySelectorAll('*');
            for (let el of allEls) {
                if (el.children.length === 0 && el.innerText) {
                    const txt = el.innerText.trim();
                    if (txt.includes('🎧') || txt.startsWith('LÝ ')) {
                        blv = txt.replace('🎧', '').trim();
                        break;
                    }
                }
            }

            return { bodyText: bodyText, blv: blv, time: timeStr, date: dateStr };
        }''')

        # Tách tên 2 đội bằng hàm lọc sạch
        teams_title = extract_clean_teams(detail_data['bodyText'])
            
        if not blv_name and detail_data['blv']:
            blv_name = extract_blv_from_text(detail_data['blv'])
            
        match_time = detail_data['time']
        match_date = detail_data['date']

        # Bóc tách nút server (HD1, HD2, Nhà đài...)
        server_buttons = page.query_selector_all('button, div, a, li')
        valid_buttons = []
        for btn in server_buttons:
            try:
                txt = btn.inner_text().strip()
                if txt in ["HD1", "HD2", "HD3", "FHD", "SD", "Nhà đài", "Nguồn 1", "Nguồn 2"]:
                    if txt not in [b[0] for b in valid_buttons]:
                        valid_buttons.append((txt, btn))
            except:
                pass

        if valid_buttons:
            for label, btn in valid_buttons:
                log_len_before = len(m3u8_log)
                try:
                    btn.click()
                    time.sleep(1.8)

                    new_m3u8 = ""
                    if len(m3u8_log) > log_len_before:
                        new_m3u8 = m3u8_log[-1]
                    else:
                        new_m3u8 = page.evaluate('''() => {
                            const v = document.querySelector('video');
                            if (v && v.src && v.src.includes('.m3u8')) return v.src;
                            const iframes = document.querySelectorAll('iframe');
                            for (let f of iframes) {
                                if (f.src && f.src.includes('.m3u8')) return f.src;
                            }
                            return '';
                        }''')

                    if not new_m3u8 and label in ["HD1", "FHD", "Nguồn 1"] and initial_m3u8:
                        new_m3u8 = initial_m3u8

                    if new_m3u8:
                        captured_streams.append((label, new_m3u8))
                except Exception as click_err:
                    print(f"[!] Lỗi click {label}: {click_err}")
        else:
            if initial_m3u8:
                captured_streams.append(("HD1", initial_m3u8))

        page.close()
    except Exception as e:
        print(f"[!] Lỗi cào chi tiết: {e}")
        try:
            page.close()
        except:
            pass

    # Giữ luồng HD1 nếu bị thiếu
    has_hd1 = any(lbl in ["HD1", "FHD", "Nguồn 1"] for lbl, _ in captured_streams)
    if not has_hd1 and initial_m3u8:
        captured_streams.insert(0, ("HD1", initial_m3u8))

    return teams_title, blv_name, match_time, match_date, captured_streams

def run_scraper():
    vn_tz = timezone(timedelta(hours=7))
    today_str = datetime.now(vn_tz).strftime("%d/%m")
    raw_matches = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-setuid-sandbox"]
            )
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 720},
                timezone_id="Asia/Ho_Chi_Minh",
                locale="vi-VN"
            )

            for base_url in DOMAINS:
                print(f"[*] Kết nối trang chủ: {base_url}")
                try:
                    page = context.new_page()
                    page.goto(base_url, timeout=30000, wait_until="domcontentloaded")
                    time.sleep(3)

                    # Cuộn trang từ từ để tải hết danh sách tất cả các trận
                    for i in range(12):
                        page.evaluate(f"window.scrollTo(0, {i * 450});")
                        time.sleep(0.3)

                    extracted = page.evaluate('''() => {
                        const results = [];
                        const seenUrls = new Set();
                        const links = Array.from(document.querySelectorAll('a')).filter(a => {
                            const href = a.getAttribute('href') || '';
                            return href.includes('/truc-tiep/') || href.includes('/match/') || href.includes('/live/') || href.includes('/phong/');
                        });

                        links.forEach(a => {
                            let fullUrl = a.href;
                            if (!fullUrl) return;
                            fullUrl = fullUrl.split('#')[0];
                            if (seenUrls.has(fullUrl)) return;

                            let container = a;
                            for (let i = 0; i < 5; i++) {
                                if (container.parentElement && container.parentElement.tagName !== 'BODY') {
                                    container = container.parentElement;
                                    if (container.innerText && container.innerText.length > 20 && container.innerText.length < 1000) {
                                        if (container.innerText.includes('vs') || container.innerText.includes(':')) break;
                                    }
                                }
                            }

                            const text = container ? container.innerText : a.innerText;
                            let logoUrl = '';
                            const img = container ? container.querySelector('img') : null;
                            if (img) logoUrl = img.src || img.getAttribute('data-src') || '';

                            let status = 'upcoming';
                            const htmlAll = container ? container.innerHTML.toLowerCase() : '';
                            if (htmlAll.includes('live') || text.includes('Đang diễn ra') || text.includes('Hiệp 1') || text.includes('Hiệp 2')) {
                                status = 'live';
                            } else if (text.includes('Sắp diễn ra') || text.includes('Chưa bắt đầu')) {
                                status = 'soon';
                            }

                            results.push({
                                url: fullUrl,
                                rawText: text,
                                logo: logoUrl,
                                status: status
                            });
                            seenUrls.add(fullUrl);
                        });
                        return results;
                    }''')

                    page.close()

                    if extracted and len(extracted) > 0:
                        raw_matches = extracted
                        print(f"[+] Lấy thành công {len(raw_matches)} trận đấu từ trang chủ!")
                        break
                except Exception as err:
                    print(f"[!] Lỗi kết nối {base_url}: {err}")

            parsed_items = []
            if raw_matches:
                print("\n[*] Đang cào dữ liệu chi tiết & bóc tách tên BLV...")
                for item in raw_matches:
                    match_url = item['url']
                    card_text = item['rawText']
                    status = item['status']

                    card_blv = extract_blv_from_text(card_text)
                    teams_from_page, blv_from_page, time_from_page, date_from_page, streams = scrape_match_detail(context, match_url, card_blv)

                    # Lấy tên cặp đấu đã lọc sạch rác
                    teams_title = teams_from_page
                    if not teams_title:
                        teams_title = extract_clean_teams(card_text)
                    if not teams_title:
                        teams_title = "Trận đấu Trực Tiếp"

                    # Giữ lại tên BLV
                    blv_final = blv_from_page if blv_from_page else card_blv
                    if not blv_final:
                        blv_final = extract_blv_from_text(teams_title)

                    extracted_time = time_from_page
                    if not extracted_time:
                        time_m = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', card_text)
                        extracted_time = f"{time_m.group(1).zfill(2)}:{time_m.group(2)}" if time_m else "13:00"

                    match_date = date_from_page
                    if not match_date:
                        date_m = re.search(r'\b(\d{1,2})[/.-](\d{1,2})\b', card_text)
                        match_date = f"{date_m.group(1).zfill(2)}/{date_m.group(2).zfill(2)}" if date_m else today_str

                    sport_icon = "⚽"
                    if any(k in card_text.lower() for k in ["bóng chuyền", "volleyball"]):
                        sport_icon = "🏐"
                    elif any(k in card_text.lower() for k in ["bóng rổ", "basketball"]):
                        sport_icon = "🏀"

                    geo_tag = " [geo]" if "geo" in card_text.lower() or "geo" in match_url.lower() else ""
                    status_dot = "🟢 " if status == 'live' else "🟡 "
                    card_logo = get_team_logo(teams_title, item['logo'])

                    try:
                        d, m = map(int, match_date.split('/'))
                        h, mins = map(int, extracted_time.split(':'))
                        dt_obj = datetime(datetime.now(vn_tz).year, m, d, h, mins, tzinfo=vn_tz)
                    except Exception:
                        dt_obj = datetime(2099, 1, 1, 0, 0, tzinfo=vn_tz)

                    if streams:
                        for server_label, stream_url in streams:
                            blv_str = f" ({blv_final})" if blv_final else ""

                            if server_label == "Nhà đài":
                                title_suffix = " (Nhà đài)"
                            elif server_label in ["HD1", "FHD", "SD", "Nguồn 1"]:
                                title_suffix = f"{blv_str}"
                            else:
                                title_suffix = f"{blv_str} [{server_label}]"

                            full_title = f"{status_dot}{extracted_time} {match_date} {sport_icon} {teams_title}{title_suffix}{geo_tag}"
                            
                            parsed_items.append({
                                "title": full_title,
                                "logo": card_logo,
                                "stream_url": stream_url,
                                "dt": dt_obj,
                                "teams_title": teams_title,
                                "server_label": server_label,
                                "match_url": f"{match_url}#{server_label}"
                            })

            browser.close()

    except Exception as e:
        print(f"[!] Lỗi hệ thống Playwright: {e}")

    # Sắp xếp danh sách theo giờ thi đấu
    parsed_items.sort(
        key=lambda x: (
            x['dt'],
            x['teams_title'],
            SERVER_PRIORITY.get(x['server_label'], 99)
        )
    )

    # Ghi ra file M3U chuẩn sạch
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U\n\n')
        seen_urls = set()
        for item in parsed_items:
            if item['match_url'] in seen_urls:
                continue
            seen_urls.add(item['match_url'])

            f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{GROUP_NAME}" , {item["title"]}\n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERER_URL}\n')
            f.write(f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n')
            f.write(f'#EXTVLCOPT:http-origin={REFERER_URL}\n')
            f.write(f'{item["stream_url"]}\n\n')

    print(f"\n[*] Đã xuất thành công {len(parsed_items)} kênh vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
