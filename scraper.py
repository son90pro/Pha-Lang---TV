import time
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# CAU HINH TEN MIEN CHINH PHÁ LÀNG TV
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

# KHO LOGO & CỜ QUỐC GIA
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

def to_slug(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower().replace('đ', 'd')
    return re.sub(r'[^a-z0-9]', '', text)

def get_team_logo(teams_str: str, raw_card_logo: str = "") -> str:
    t_lower = teams_str.lower()
    for key, url in LOGOS.items():
        if key in t_lower:
            return url
    if raw_card_logo and raw_card_logo.startswith("http"):
        return raw_card_logo
    return DEFAULT_LOGO

def scrape_match_detail(context, match_url: str):
    """
    Truy cập trang chi tiết trận đấu:
    1. Bóc tách tên 2 đội & tên BLV từ giao diện thực tế.
    2. Click lần lượt các nút nguồn HD1, HD2, Nhà đài... để bắt link .m3u8 thực tế.
    """
    page = context.new_page()
    captured_streams = [] # Lưu [(server_label, m3u8_url)]
    current_m3u8 = None

    # Lắng nghe gói tin mạng để bắt đường dẫn .m3u8
    def handle_request(req):
        nonlocal current_m3u8
        url = req.url
        if ".m3u8" in url:
            # Ưu tiên các file playlist m3u8 chứa luồng phát video
            if any(k in url for k in ["index", "playlist", "live", "stream", "chunk", "hls", "master"]):
                current_m3u8 = url

    page.on("request", handle_request)

    teams_title = ""
    blv_name = ""

    try:
        print(f"[*] Đang cào dữ liệu chi tiết: {match_url}")
        page.goto(match_url, timeout=25000, wait_until="domcontentloaded")
        time.sleep(2)

        # 1. Bóc tách Tên 2 Đội bóng & BLV trực tiếp từ DOM giao diện web
        detail_data = page.evaluate('''() => {
            let t1 = '', t2 = '', blv = '';
            
            // Tìm tên đội bóng từ khung thông tin trận đấu
            const bodyText = document.body.innerText || '';
            const vsMatch = bodyText.match(/Phát trực tiếp\\s+([A-Za-z0-9\\s]+?)\\s+vs\\s+([A-Za-z0-9\\s]+?)\\s+vào/i);
            if (vsMatch) {
                t1 = vsMatch[1].strip ? vsMatch[1].strip() : vsMatch[1];
                t2 = vsMatch[2].strip ? vsMatch[2].strip() : vsMatch[2];
            }

            // Tìm tên BLV (thường đi kèm icon tai nghe hoặc chữ LÝ ...)
            const blvEl = document.querySelector('a[href*="caster"], .caster-name, [class*="caster"]');
            if (blvEl) {
                blv = blvEl.innerText.trim();
            } else {
                const blvMatch = bodyText.match(/(?:BLV|Caster|🎧)\\s*([A-Za-zÀ-ỹ0-9\\s]{2,15})/i);
                if (blvMatch) blv = blvMatch[1].trim();
            }

            return { team1: t1, team2: t2, blv: blv };
        }''')

        if detail_data['team1'] and detail_data['team2']:
            teams_title = f"{detail_data['team1']} vs {detail_data['team2']}"
        if detail_data['blv']:
            blv_name = detail_data['blv']

        # 2. Tìm tất cả các nút nguồn phát (HD1, HD2, Nhà đài, ...)
        server_buttons = page.query_selector_all('button:has-text("HD"), div:has-text("HD"), button:has-text("Nhà đài"), div:has-text("Nhà đài")')
        
        valid_buttons = []
        for btn in server_buttons:
            txt = btn.inner_text().strip()
            if txt in ["HD1", "HD2", "HD3", "FHD", "SD", "Nhà đài"] and txt not in [b[0] for b in valid_buttons]:
                valid_buttons.append((txt, btn))

        # Nếu không thấy nút dạng text ngắn, lấy các nút trong khung chọn nguồn
        if not valid_buttons:
            btn_els = page.query_selector_all('.server-item, .list-server *, button')
            for btn in btn_els:
                txt = btn.inner_text().strip()
                if txt in ["HD1", "HD2", "Nhà đài"] and txt not in [b[0] for b in valid_buttons]:
                    valid_buttons.append((txt, btn))

        # 3. Lần lượt click từng nút nguồn để bắt link .m3u8 tương ứng
        if valid_buttons:
            for label, btn in valid_buttons:
                current_m3u8 = None
                try:
                    btn.click()
                    time.sleep(1.8) # Chờ trình phát nạp stream m3u8 mới

                    # Nếu không bắt được qua network, kiểm tra src trong thẻ video / iframe
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
            # Nguồn mặc định nếu không bấm được nút
            time.sleep(2)
            if current_m3u8:
                captured_streams.append(("HD1", current_m3u8))

        page.close()
    except Exception as e:
        print(f"[!] Lỗi cào chi tiết trang {match_url}: {e}")
        try:
            page.close()
        except:
            pass

    return teams_title, blv_name, captured_streams

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

            # Lấy danh sách trận đấu từ trang chủ phalang.live
            for base_url in DOMAINS:
                print(f"[*] Kết nối trang chủ: {base_url}")
                try:
                    page = context.new_page()
                    page.goto(base_url, timeout=30000, wait_until="domcontentloaded")
                    time.sleep(2.5)

                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, 800)")
                        time.sleep(0.3)

                    extracted = page.evaluate('''() => {
                        const results = [];
                        const seenUrls = new Set();
                        const links = document.querySelectorAll('a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/live/"]');

                        links.forEach(a => {
                            const href = a.getAttribute('href');
                            if (!href) return;
                            const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                            if (seenUrls.has(fullUrl)) return;
                            seenUrls.add(fullUrl);

                            let container = a.parentElement;
                            while (container && container.tagName !== 'BODY') {
                                if (container.innerText && container.innerText.length > 20 && container.innerText.length < 500) {
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
                            } else if (text.includes('Sắp diễn ra')) {
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

                    page.close()

                    if extracted and len(extracted) > 0:
                        raw_matches = extracted
                        print(f"[+] Lấy thành công {len(raw_matches)} trận từ {base_url}")
                        break
                except Exception as err:
                    print(f"[!] Lỗi kết nối {base_url}: {err}")

            # CÀO CHI TIẾT TỪNG TRẬN ĐẤU & CÁC NGUỒN HD1, HD2, NHÀ ĐÀI
            parsed_items = []
            if raw_matches:
                print("\n[*] Bắt đầu cào luồng stream HD1, HD2, Nhà đài từng trận...")
                for item in raw_matches:
                    match_url = item['url']
                    card_text = item['rawText']
                    status = item['status']

                    teams_from_page, blv_from_page, streams = scrape_match_detail(context, match_url)

                    # Tên hai đội
                    teams_title = teams_from_page
                    if not teams_title:
                        match_vs = re.search(r'([A-Za-zÀ-ỹ0-9\s\.]{2,25})\s+vs\s+([A-Za-zÀ-ỹ0-9\s\.]{2,25})', card_text, re.I)
                        if match_vs:
                            teams_title = f"{match_vs.group(1).strip()} vs {match_vs.group(2).strip()}"
                        else:
                            teams_title = "Trận đấu Trực Tiếp"

                    # Tên BLV
                    blv_name = blv_from_page if blv_from_page else "Nhà đài"

                    # Icon thể thao
                    sport_icon = "⚽"
                    if any(k in card_text.lower() for k in ["bóng chuyền", "volleyball"]):
                        sport_icon = "🏐"
                    elif any(k in card_text.lower() for k in ["bóng rổ", "basketball"]):
                        sport_icon = "🏀"

                    # Thời gian
                    time_m = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', card_text)
                    extracted_time = f"{time_m.group(1).zfill(2)}:{time_m.group(2)}" if time_m else "13:00"

                    date_m = re.search(r'\b(\d{1,2})[/.-](\d{1,2})\b', card_text)
                    match_date = f"{date_m.group(1).zfill(2)}/{date_m.group(2).zfill(2)}" if date_m else today_str

                    status_dot = "🟢 " if status == 'live' else ("🟡 " if status == 'soon' else "")
                    card_logo = get_team_logo(teams_title, item['logo'])

                    try:
                        d, m = map(int, match_date.split('/'))
                        h, mins = map(int, extracted_time.split(':'))
                        dt_obj = datetime(datetime.now(vn_tz).year, m, d, h, mins, tzinfo=vn_tz)
                    except Exception:
                        dt_obj = datetime(2099, 1, 1, 0, 0, tzinfo=vn_tz)

                    # Tạo channel riêng cho từng nguồn (HD1, HD2, Nhà đài)
                    if streams:
                        for server_label, stream_url in streams:
                            full_title = f"{status_dot}{extracted_time} {match_date} {sport_icon} {teams_title} ({blv_name}) [{server_label}]"
                            parsed_items.append({
                                "title": full_title,
                                "logo": card_logo,
                                "stream_url": stream_url,
                                "dt": dt_obj,
                                "status": status,
                                "match_url": f"{match_url}#{server_label}"
                            })
                    else:
                        # Fallback nếu không bắt được nút
                        full_title = f"{status_dot}{extracted_time} {match_date} {sport_icon} {teams_title} ({blv_name})"
                        parsed_items.append({
                            "title": full_title,
                            "logo": card_logo,
                            "stream_url": match_url,
                            "dt": dt_obj,
                            "status": status,
                            "match_url": match_url
                        })

            browser.close()

    except Exception as e:
        print(f"[!] Lỗi hệ thống Playwright: {e}")

    # GHI FILE PLAYLIST M3U HOÀN CHỈNH CHO TIVIMATE / IPTV
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

    print(f"\n[*] Xuất thành công {len(parsed_items)} kênh/nguồn phát vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
