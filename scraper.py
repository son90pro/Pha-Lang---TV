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

KNOWN_BLVS = [
    "LÝ LINH LỰC", "LÝ LINH", "LÝ LÊN LỬA", "LÝ LA LÀNG", "LÝ BÒ", "LÝ THÔNG",
    "LÝ TƯỞNG", "LÝ BÉO", "LÝ ĐỨC", "CHUỐI CHIÊN", "CHUỐI CHAO", "TRỐC",
    "CỦ CỐT", "THỎ", "GÀ", "SÁY"
]

LOGOS = {
    "north korea": "https://flagcdn.com/w320/kp.png", "triều tiên": "https://flagcdn.com/w320/kp.png", "dprk": "https://flagcdn.com/w320/kp.png",
    "iran": "https://flagcdn.com/w320/ir.png",
    "philippines": "https://flagcdn.com/w320/ph.png",
    "pakistan": "https://flagcdn.com/w320/pk.png",
    "indonesia": "https://flagcdn.com/w320/id.png",
    "china": "https://flagcdn.com/w320/cn.png", "trung quốc": "https://flagcdn.com/w320/cn.png",
    "vietnam": "https://flagcdn.com/w320/vn.png", "việt nam": "https://flagcdn.com/w320/vn.png",
    "thailand": "https://flagcdn.com/w320/th.png", "thái lan": "https://flagcdn.com/w320/th.png",
    "malaysia": "https://flagcdn.com/w320/my.png",
    "japan": "https://flagcdn.com/w320/jp.png", "nhật bản": "https://flagcdn.com/w320/jp.png",
    "south korea": "https://flagcdn.com/w320/kr.png", "hàn quốc": "https://flagcdn.com/w320/kr.png",
    "australia": "https://flagcdn.com/w320/au.png", "úc": "https://flagcdn.com/w320/au.png",
    "brazil": "https://flagcdn.com/w320/br.png", "argentina": "https://flagcdn.com/w320/ar.png"
}

def sanitize_text(text: str) -> str:
    """Xóa bỏ hoàn toàn ký tự xuống dòng và khoảng trắng thừa"""
    if not text:
        return ""
    clean = re.sub(r'[\r\n\t]+', ' ', str(text))
    return re.sub(r'\s+', ' ', clean).strip()

def clean_teams_title(text: str) -> str:
    """Loại bỏ triệt để các cụm ngày giờ, từ rác để tránh trùng lặp tiêu đề"""
    if not text:
        return ""
    
    # Xóa cụm 'vào lúc HH:MM', 'ngày DD/MM', các định dạng giờ trùng
    text = re.sub(r'vào lúc\s*\d{1,2}[:h]\d{2}', '', text, flags=re.I)
    text = re.sub(r',?\s*ngày\s*\d{1,2}[/-]\d{1,2}', '', text, flags=re.I)
    text = re.sub(r'\b\d{1,2}[:h]\d{2}\b', '', text)
    text = re.sub(r'\b\d{1,2}[/-]\d{1,2}\b', '', text)
    
    # Xóa các cụm từ thừa từ web
    noise_patterns = [
        r'trực tiếp', r'phát trực tiếp', r'xem trực tiếp', r'xem bóng đá',
        r'theo bạn thì trận này đội nào sẽ thắng\??', r'chủ nhà', r'hòa', r'đội khách',
        r'lý linh lực', r'lý lên lửa', r'lý la làng', r'nhà đài'
    ]
    for pat in noise_patterns:
        text = re.sub(pat, '', text, flags=re.I)

    # Làm sạch ký tự nối thừa
    text = re.sub(r'^\s*vs\s+|\s+vs\s*$', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_team_logo(teams_str: str, raw_card_logo: str = "") -> str:
    t_lower = teams_str.lower()
    for key, url in LOGOS.items():
        if key in t_lower:
            return url
    if raw_card_logo and raw_card_logo.startswith("http") and "fire.svg" not in raw_card_logo:
        return raw_card_logo
    return DEFAULT_LOGO

def extract_blv_from_text(text: str) -> str:
    if not text:
        return ""
    text_upper = text.upper()
    for b in KNOWN_BLVS:
        if b in text_upper:
            return b
    m = re.search(r'(?:🎧|BLV|CASTER)\s*([A-ZÀ-Ỹ0-9\s]{2,15})', text_upper)
    if m:
        candidate = m.group(1).strip()
        if "NHÀ ĐÀI" not in candidate:
            return candidate
    m_ly = re.search(r'\b(LÝ\s+[A-ZÀ-Ỹ0-9\s]{2,12})\b', text_upper)
    if m_ly:
        return m_ly.group(1).strip()
    return ""

def scrape_match_detail(context, match_url: str, card_blv: str = ""):
    page = context.new_page()
    captured_streams = []
    m3u8_history = []

    def handle_request(req):
        url = req.url
        if ".m3u8" in url:
            if any(k in url for k in ["index", "playlist", "live", "stream", "chunk", "hls", "master"]):
                if url not in m3u8_history:
                    m3u8_history.append(url)

    page.on("request", handle_request)

    teams_title = ""
    blv_name = card_blv
    match_time = ""
    match_date = ""

    try:
        print(f"[*] Đang cào dữ liệu chi tiết: {match_url}")
        page.goto(match_url, timeout=25000, wait_until="domcontentloaded")
        time.sleep(2)

        detail_data = page.evaluate('''() => {
            let t1 = '', t2 = '', blv = '', timeStr = '', dateStr = '';
            const bodyText = document.body.innerText || '';

            const teamNodes = document.querySelectorAll('.team-name, .team_name, [class*="team"] .name, .club-name');
            if (teamNodes.length >= 2) {
                t1 = teamNodes[0].innerText || '';
                t2 = teamNodes[1].innerText || '';
            }

            if (!t1 || !t2) {
                const lines = bodyText.split('\\n');
                for (let line of lines) {
                    let l = line.trim();
                    if (/\\bvs\\b/i.test(l) && !l.includes('THEO BẠN') && l.length < 80) {
                        const parts = l.split(/\\s+vs\\s+/i);
                        if (parts.length === 2) {
                            t1 = parts[0].trim();
                            t2 = parts[1].trim();
                            break;
                        }
                    }
                }
            }

            const timeMatch = bodyText.match(/(\\d{1,2}:\\d{2})\\s+(\\d{1,2}\\/\\d{1,2})/);
            if (timeMatch) {
                timeStr = timeMatch[1];
                dateStr = timeMatch[2];
            }

            const allEls = document.querySelectorAll('*');
            for (let el of allEls) {
                if (el.children.length === 0 && el.innerText) {
                    const txt = el.innerText.trim();
                    if (txt.includes('🎧')) {
                        blv = txt.replace('🎧', '').trim();
                        break;
                    }
                }
            }

            return { team1: t1, team2: t2, blv: blv, time: timeStr, date: dateStr };
        }''')

        t1 = clean_teams_title(detail_data['team1'])
        t2 = clean_teams_title(detail_data['team2'])

        if t1 and t2 and t1.lower() != t2.lower():
            teams_title = f"{t1} vs {t2}"

        if not blv_name and detail_data['blv']:
            blv_name = extract_blv_from_text(detail_data['blv'])

        match_time = sanitize_text(detail_data['time'])
        match_date = sanitize_text(detail_data['date'])

        server_buttons = page.query_selector_all('button, div, a, li')
        valid_buttons = []
        for btn in server_buttons:
            try:
                txt = btn.inner_text().strip()
                if txt in ["HD1", "HD2", "HD3", "FHD", "SD", "Nhà đài", "Nguồn 1", "Nguồn 2", "GEO", "Full HD"]:
                    if txt not in [b[0] for b in valid_buttons]:
                        valid_buttons.append((txt, btn))
            except:
                pass

        if valid_buttons:
            for label, btn in valid_buttons:
                m3u8_history.clear()
                try:
                    btn.click()
                    time.sleep(1.8)

                    current_m3u8 = m3u8_history[-1] if m3u8_history else ""
                    if not current_m3u8:
                        current_m3u8 = page.evaluate('''() => {
                            const v = document.querySelector('video');
                            if (v && v.src && v.src.includes('.m3u8')) return v.src;
                            const iframes = document.querySelectorAll('iframe');
                            for (let f of iframes) {
                                if (f.src && f.src.includes('.m3u8')) return f.src;
                            }
                            return '';
                        }''')

                    if current_m3u8:
                        captured_streams.append((label, current_m3u8))
                except Exception as click_err:
                    print(f"[!] Lỗi click nút {label}: {click_err}")
        else:
            time.sleep(2)
            if m3u8_history:
                captured_streams.append(("HD1", m3u8_history[-1]))

        page.close()
    except Exception as e:
        print(f"[!] Lỗi cào chi tiết: {e}")
        try:
            page.close()
        except:
            pass

    return teams_title, blv_name, match_time, match_date, captured_streams

def run_scraper():
    vn_tz = timezone(timedelta(hours=7))
    today_str = datetime.now(vn_tz).strftime("%d/%m")
    all_extracted_matches = {}

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

                    # 1. TỰ ĐỘNG BẤM TẤT CẢ CÁC TAB DANH MỤC & NGÀY
                    tab_selectors = [
                        "//*[contains(text(), 'Tất cả')]",
                        "//*[contains(text(), 'Hôm nay')]",
                        "//*[contains(text(), 'Ngày mai')]",
                        "//*[contains(text(), 'Bóng đá')]",
                        "//*[contains(text(), 'Bóng chuyền')]",
                        "//*[contains(text(), 'Bóng rổ')]",
                        "//*[contains(text(), 'Esports')]"
                    ]

                    for tab_xpath in tab_selectors:
                        try:
                            tab_btn = page.query_selector(f"xpath={tab_xpath}")
                            if tab_btn and tab_btn.is_visible():
                                tab_btn.click()
                                time.sleep(1.5)
                        except:
                            pass

                        # 2. CUỘN SÂU & BẤM NÚT "XEM THÊM" ĐỂ TẢI HẾT TRẬN ĐẤU
                        for scroll_step in range(12):
                            page.evaluate("window.scrollBy(0, 1500)")
                            time.sleep(0.4)

                            # Tự động click nút 'Xem thêm' nếu có
                            try:
                                load_more = page.query_selector("xpath=//*[contains(text(), 'Xem thêm') or contains(text(), 'Tải thêm')]")
                                if load_more and load_more.is_visible():
                                    load_more.click()
                                    time.sleep(1)
                            except:
                                pass

                        # 3. RÚT TRÍCH TOÀN BỘ LINK TRẬN ĐẤU TRÊN TRANG
                        extracted = page.evaluate('''() => {
                            const results = [];
                            const links = document.querySelectorAll('a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/live/"], a[href*="/phong/"], a[href*="/xem/"]');

                            links.forEach(a => {
                                const href = a.getAttribute('href');
                                if (!href) return;
                                const fullUrl = href.startsWith('http') ? href : window.location.origin + href;

                                let container = a.parentElement;
                                while (container && container.tagName !== 'BODY') {
                                    if (container.innerText && container.innerText.length > 15 && container.innerText.length < 800) {
                                        break;
                                    }
                                    container = container.parentElement;
                                }

                                const text = container ? container.innerText : a.innerText;
                                let logoUrl = '';
                                const img = container ? container.querySelector('img') : null;
                                if (img) logoUrl = img.getAttribute('src') || img.getAttribute('data-src') || '';

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
                            });
                            return results;
                        }''')

                        for item in extracted:
                            all_extracted_matches[item['url']] = item

                    page.close()

                    if len(all_extracted_matches) > 0:
                        print(f"[+] Đã tìm thấy tổng cộng {len(all_extracted_matches)} trận đấu!")
                        break
                except Exception as err:
                    print(f"[!] Lỗi kết nối {base_url}: {err}")

            parsed_items = []
            raw_matches = list(all_extracted_matches.values())

            if raw_matches:
                print("\n[*] Đang bóc tách thông tin chi tiết từng trận đấu...")
                for item in raw_matches:
                    match_url = item['url']
                    card_text = sanitize_text(item['rawText'])
                    status = item['status']

                    card_blv = extract_blv_from_text(card_text)
                    teams_from_page, blv_from_page, time_from_page, date_from_page, streams = scrape_match_detail(context, match_url, card_blv)

                    # Xử lý tên hai đội (Làm sạch hoàn toàn ngày giờ trùng lặp)
                    teams_title = teams_from_page
                    if not teams_title:
                        match_vs = re.search(r'([A-Za-zÀ-ỹ0-9\s\.]{2,25})\s+vs\s+([A-Za-zÀ-ỹ0-9\s\.]{2,25})', card_text, re.I)
                        if match_vs:
                            teams_title = f"{clean_teams_title(match_vs.group(1))} vs {clean_teams_title(match_vs.group(2))}"
                        else:
                            teams_title = clean_teams_title(card_text)

                    teams_title = clean_teams_title(teams_title)
                    if not teams_title:
                        teams_title = "Trận đấu Trực Tiếp"

                    blv_final = blv_from_page if blv_from_page else card_blv

                    # Giờ & Ngày
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
                            is_geo = "digitalcdn" in stream_url.lower() or "geo" in stream_url.lower() or "geo" in match_url.lower() or server_label.upper() == "GEO"
                            geo_tag = " [geo]" if is_geo else ""

                            if server_label in ["HD1", "FHD", "SD", "Nguồn 1"]:
                                server_part = ""
                            else:
                                server_part = f" [{server_label}]" if server_label != "Nhà đài" else ""

                            if server_label == "Nhà đài":
                                blv_part = " (Nhà đài)"
                            else:
                                blv_part = f" ({blv_final})" if blv_final else ""

                            # ĐỊNH DẠNG CHUẨN GỌN GÀNG: KHÔNG BỊ TRÙNG LẶP NGÀY GIỜ VÀ CỤM "VÀO LÚC"
                            full_title = sanitize_text(f"{status_dot}{extracted_time} {match_date} {sport_icon} {teams_title}{blv_part}{server_part}{geo_tag}")

                            parsed_items.append({
                                "title": full_title,
                                "logo": card_logo,
                                "stream_url": stream_url,
                                "dt": dt_obj,
                                "status": status,
                                "match_url": f"{match_url}#{server_label}"
                            })

            browser.close()

    except Exception as e:
        print(f"[!] Lỗi hệ thống Playwright: {e}")

    # GHI FILE M3U
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

    print(f"\n[*] Đã xuất thành công {len(parsed_items)} luồng kênh vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
