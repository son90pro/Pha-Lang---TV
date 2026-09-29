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
    1. Bóc tách chính xác GIỜ THI ĐẤU (ví dụ 13:00) từ dòng thông báo trận đấu.
    2. Bóc tách chính xác TÊN BLV nằm cạnh icon tai nghe (🎧).
    3. Click lần lượt nút HD1, HD2, Nhà đài để lấy link stream thực tế.
    """
    page = context.new_page()
    captured_streams = []
    current_m3u8 = None

    def handle_request(req):
        nonlocal current_m3u8
        url = req.url
        if ".m3u8" in url:
            if any(k in url for k in ["index", "playlist", "live", "stream", "chunk", "hls", "master"]):
                current_m3u8 = url

    page.on("request", handle_request)

    teams_title = ""
    blv_name = ""
    match_time = ""
    match_date = ""

    try:
        print(f"[*] Đang cào dữ liệu: {match_url}")
        page.goto(match_url, timeout=25000, wait_until="domcontentloaded")
        time.sleep(2)

        # Trích xuất dữ liệu chuẩn từ DOM trang chi tiết
        detail_data = page.evaluate('''() => {
            let t1 = '', t2 = '', blv = '', timeStr = '', dateStr = '';
            const bodyText = document.body.innerText || '';

            // 1. Trích xuất thời gian chuẩn từ dòng "Phát trực tiếp ... vào lúc HH:MM, ngày DD/MM"
            const matchInfo = bodyText.match(/Phát\\s+trực\\s+tiếp\\s+([A-Za-z0-9\\s]+?)\\s+vs\\s+([A-Za-z0-9\\s]+?)\\s+vào\\s+lúc\\s+(\\d{1,2}:\\d{2})[,\\s]+ngày\\s+(\\d{1,2}\\/\\d{1,2})/i);
            if (matchInfo) {
                t1 = matchInfo[1].trim();
                t2 = matchInfo[2].trim();
                timeStr = matchInfo[3].trim();
                dateStr = matchInfo[4].trim();
            } else {
                // Tìm thời gian trên bảng điểm / banner
                const timeMatch = bodyText.match(/(\\d{1,2}:\\d{2})\\s+(\\d{1,2}\\/\\d{1,2})/);
                if (timeMatch) {
                    timeStr = timeMatch[1];
                    dateStr = timeMatch[2];
                }
            }

            // 2. Trích xuất tên BLV (nằm cạnh icon tai nghe 🎧)
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

            if (!blv) {
                const blvMatch = bodyText.match(/(?:🎧|BLV|Caster)\\s*([A-Za-zÀ-ỹ0-9\\s]{2,20})/i);
                if (blvMatch) blv = blvMatch[1].trim();
            }

            // Loại bỏ chữ Nhà đài nếu bị lầm tưởng là BLV
            if (blv.toLowerCase().includes('nhà đài')) blv = '';

            return { team1: t1, team2: t2, blv: blv, time: timeStr, date: dateStr };
        }''')

        if detail_data['team1'] and detail_data['team2']:
            teams_title = f"{detail_data['team1']} vs {detail_data['team2']}"
        
        blv_name = detail_data['blv']
        match_time = detail_data['time']
        match_date = detail_data['date']

        # Tìm các nút chọn nguồn phát (HD1, HD2, Nhà đài)
        server_buttons = page.query_selector_all('button, div, a')
        valid_buttons = []
        for btn in server_buttons:
            try:
                txt = btn.inner_text().strip()
                if txt in ["HD1", "HD2", "HD3", "FHD", "SD", "Nhà đài"] and txt not in [b[0] for b in valid_buttons]:
                    valid_buttons.append((txt, btn))
            except:
                pass

        # Click lần lượt các nút nguồn để bắt link .m3u8 thực tế
        if valid_buttons:
            for label, btn in valid_buttons:
                current_m3u8 = None
                try:
                    btn.click()
                    time.sleep(1.8)

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
            if current_m3u8:
                captured_streams.append(("HD1", current_m3u8))

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

            # Lấy danh sách link trận đấu
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

            # XỬ LÝ CHI TIẾT TỪNG TRẬN
            parsed_items = []
            if raw_matches:
                print("\n[*] Đang bóc tách giờ chuẩn, BLV & luồng stream thực tế...")
                for item in raw_matches:
                    match_url = item['url']
                    card_text = item['rawText']
                    status = item['status']

                    teams_from_page, blv_from_page, time_from_page, date_from_page, streams = scrape_match_detail(context, match_url)

                    # Tên đội
                    teams_title = teams_from_page
                    if not teams_title:
                        match_vs = re.search(r'([A-Za-zÀ-ỹ0-9\s\.]{2,25})\s+vs\s+([A-Za-zÀ-ỹ0-9\s\.]{2,25})', card_text, re.I)
                        if match_vs:
                            teams_title = f"{match_vs.group(1).strip()} vs {match_vs.group(2).strip()}"
                        else:
                            teams_title = "Trận đấu Trực Tiếp"

                    # Giờ thi đấu chuẩn
                    extracted_time = time_from_page if time_from_page else "13:00"
                    match_date = date_from_page if date_from_page else today_str

                    # Icon môn thể thao
                    sport_icon = "⚽"
                    if any(k in card_text.lower() for k in ["bóng chuyền", "volleyball"]):
                        sport_icon = "🏐"
                    elif any(k in card_text.lower() for k in ["bóng rổ", "basketball"]):
                        sport_icon = "🏀"

                    status_dot = "🟢 " if status == 'live' else ("🟡 " if status == 'soon' else "")
                    card_logo = get_team_logo(teams_title, item['logo'])

                    try:
                        d, m = map(int, match_date.split('/'))
                        h, mins = map(int, extracted_time.split(':'))
                        dt_obj = datetime(datetime.now(vn_tz).year, m, d, h, mins, tzinfo=vn_tz)
                    except Exception:
                        dt_obj = datetime(2099, 1, 1, 0, 0, tzinfo=vn_tz)

                    # Định dạng hiển thị tên BLV & Nguồn phát (Tránh trùng lặp Nhà đài)
                    blv_part = f" ({blv_from_page})" if blv_from_page else ""

                    if streams:
                        for server_label, stream_url in streams:
                            full_title = f"{status_dot}{extracted_time} {match_date} {sport_icon} {teams_title}{blv_part} [{server_label}]"
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

    print(f"\n[*] Xuất thành công {len(parsed_items)} kênh/nguồn phát vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
