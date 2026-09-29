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
DEFAULT_LOGO = "https://sta.vnres.co/file/common/20260926/e852329be4add16641d68cfb8aa233ad.png"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

KNOWN_BLVS = [
    "LÝ LINH LỰC", "LÝ LINH", "LÝ LÊN LỬA", "LÝ LA LÀNG", "LÝ BÒ", "LÝ THÔNG",
    "LÝ TƯỞNG", "LÝ BÉO", "LÝ ĐỨC", "LÝ LIỀU LĨNH", "LÝ LÀNG LÁ", "LÝ LẮC LÉO",
    "LÝ LONG", "CHUỐI CHIÊN", "CHUỐI CHAO", "TRỐC", "CỦ CỐT", "THỎ", "GÀ", "SÁY"
]

SERVER_PRIORITY = {
    "HD1": 1, "FHD": 1, "SD": 1, "Nguồn 1": 1,
    "HD2": 2, "Nguồn 2": 2,
    "HD3": 3,
    "Nhà đài": 4
}

def clean_teams_title(raw_text: str) -> str:
    """Bóc tách chính xác 'Đội A vs Đội B' - Xóa sạch rác chữ"""
    if not raw_text:
        return ""
    
    cleaned = re.sub(r'^(Phát\s+trực\s+tiếp|Trực\s+tiếp|Xem|Lịch|Phát)\s*', '', raw_text, flags=re.IGNORECASE)
    
    m = re.search(r'([A-Za-z0-9\sÀ-ỹ\.\-]{2,35})\s+vs\s+([A-Za-z0-9\sÀ-ỹ\.\-]{2,35})', cleaned, re.IGNORECASE)
    if m:
        t1 = m.group(1).strip()
        t2 = m.group(2).strip()
        
        t1 = re.sub(r'^(Phát\s+trực\s+tiếp|Trực\s+tiếp|Xem|Phát)\s*', '', t1, flags=re.IGNORECASE).strip()
        t2 = re.split(r'\s+(vào\s+lúc|ngày|lúc|\(|\[|\d{1,2}:\d{2})', t2, flags=re.IGNORECASE)[0].strip()
        
        garbage = ["CHỦ NHÀ", "HÒA", "ĐỘI KHÁCH", "TRỰC TIẾP", "MÔ PHỎNG", "CHIA SẺ"]
        for g in garbage:
            t1 = re.sub(re.escape(g), "", t1, flags=re.IGNORECASE).strip()
            t2 = re.sub(re.escape(g), "", t2, flags=re.IGNORECASE).strip()
            
        if t1 and t2:
            return f"{t1} vs {t2}"
            
    return ""

def extract_blv_from_text(text: str) -> str:
    """Rút gọn tên BLV chuẩn mẫu"""
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
        page.goto(match_url, timeout=25000, wait_until="domcontentloaded")
        time.sleep(2.5)

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

        teams_title = clean_teams_title(detail_data['bodyText'])
            
        if not blv_name and detail_data['blv']:
            blv_name = extract_blv_from_text(detail_data['blv'])
            
        match_time = detail_data['time']
        match_date = detail_data['date']

        # Bóc tách nút chọn Server phát
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
                except Exception:
                    pass
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

    has_hd1 = any(lbl in ["HD1", "FHD", "Nguồn 1"] for lbl, _ in captured_streams)
    if not has_hd1 and initial_m3u8:
        captured_streams.insert(0, ("HD1", initial_m3u8))

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

                    # TỰ ĐỘNG CHUYỂN CÁC TAB ĐỂ QUÉT TOÀN BỘ TRẬN ĐẤU (HÔM NAY, NGÀY MAI, TẤT CẢ)
                    tab_names = ["Tất cả", "Hôm nay", "Ngày mai", "Bóng đá", "Bóng chuyền", "Bóng rổ"]
                    for t_name in tab_names:
                        try:
                            tab_btn = page.query_selector(f"xpath=//*[contains(text(), '{t_name}')]")
                            if tab_btn:
                                tab_btn.click()
                                time.sleep(1.5)
                        except:
                            pass

                        # Cuộn trang liên tục để kích hoạt Lazy Loading
                        for scroll in range(10):
                            page.evaluate(f"window.scrollTo(0, {scroll * 500});")
                            time.sleep(0.15)

                        extracted = page.evaluate('''() => {
                            const results = [];
                            const links = Array.from(document.querySelectorAll('a')).filter(a => {
                                const href = a.getAttribute('href') || '';
                                return href.includes('/truc-tiep/') || href.includes('/match/') || href.includes('/live/') || href.includes('/phong/');
                            });

                            links.forEach(a => {
                                let fullUrl = a.href;
                                if (!fullUrl) return;
                                fullUrl = fullUrl.split('#')[0];

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
                            });
                            return results;
                        }''')

                        for item in extracted:
                            all_extracted_matches[item['url']] = item

                    page.close()

                    if all_extracted_matches:
                        print(f"[+] Lấy thành công {len(all_extracted_matches)} trận đấu duy nhất!")
                        break
                except Exception as err:
                    print(f"[!] Lỗi kết nối {base_url}: {err}")

            parsed_items = []
            raw_matches = list(all_extracted_matches.values())

            if raw_matches:
                print("\n[*] Đang cào dữ liệu chi tiết từng trận & bóc tách stream...")
                for item in raw_matches:
                    match_url = item['url']
                    card_text = item['rawText']
                    status = item['status']

                    card_blv = extract_blv_from_text(card_text)
                    teams_from_page, blv_from_page, time_from_page, date_from_page, streams = scrape_match_detail(context, match_url, card_blv)

                    teams_title = teams_from_page if teams_from_page else clean_teams_title(card_text)
                    if not teams_title:
                        teams_title = "Trận đấu Trực Tiếp"

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

                    # Biểu tượng môn thể thao
                    sport_icon = "⚽"
                    if any(k in card_text.lower() for k in ["bóng chuyền", "volleyball"]):
                        sport_icon = "🏐"
                    elif any(k in card_text.lower() for k in ["bóng rổ", "basketball"]):
                        sport_icon = "🏀"

                    # Chấm trạng thái chuẩn M3U
                    if status == 'live':
                        status_prefix = "🟢 "
                    elif status == 'soon':
                        status_prefix = "🟡 "
                    else:
                        status_prefix = ""

                    # Ưu tiên lấy Logo gốc của web
                    card_logo = item['logo'] if item['logo'] and item['logo'].startswith("http") else DEFAULT_LOGO

                    try:
                        d, m = map(int, match_date.split('/'))
                        h, mins = map(int, extracted_time.split(':'))
                        dt_obj = datetime(datetime.now(vn_tz).year, m, d, h, mins, tzinfo=vn_tz)
                    except Exception:
                        dt_obj = datetime(2099, 1, 1, 0, 0, tzinfo=vn_tz)

                    if streams:
                        for server_label, stream_url in streams:
                            # Hậu tố vị trí Geo
                            is_geo = "digitalcdn" in stream_url.lower() or "geo" in stream_url.lower() or "geo" in match_url.lower()
                            geo_suffix = " [geo]" if is_geo else ""

                            # Hậu tố Server & BLV khớp 100% mẫu
                            if server_label == "Nhà đài":
                                server_suffix = " (Nhà đài)"
                            else:
                                blv_str = blv_final if blv_final else "Unknown"
                                if server_label in ["HD2", "Nguồn 2", "HD 2"]:
                                    server_suffix = f" ({blv_str}) (HD2)"
                                else:
                                    server_suffix = f" ({blv_str})"

                            full_title = f"{status_prefix}{extracted_time} {match_date} {sport_icon} {teams_title}{server_suffix}{geo_suffix}"
                            
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

    # Sắp xếp danh sách kênh theo thời gian & server
    parsed_items.sort(
        key=lambda x: (
            x['dt'],
            x['teams_title'],
            SERVER_PRIORITY.get(x['server_label'], 99)
        )
    )

    # ĐỊNH DẠNG XUẤT FILE M3U CHUẨN MẪU 100%
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U\n\n')
        seen_urls = set()
        for item in parsed_items:
            if item['match_url'] in seen_urls:
                continue
            seen_urls.add(item['match_url'])

            f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{GROUP_NAME}" , {item["title"]} \n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERER_URL}\n')
            f.write(f'{item["stream_url"]}\n\n')

    print(f"\n[*] Đã xuất thành công {len(parsed_items)} kênh vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
