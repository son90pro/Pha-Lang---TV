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

# Logo mặc định chất lượng cao cho các CLB không phải ĐTQG
DEFAULT_LOGO = "https://images.unicourt.com/sports/soccer.png"
DEFAULT_BLV = "LÝ LINH LỰC"  # BLV mặc định khi trang web bỏ trống

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

KNOWN_BLVS = [
    "LÝ LINH LỰC", "LÝ LINH", "LÝ LÊN LỬA", "LÝ LA LÀNG", "LÝ BÒ", "LÝ THÔNG",
    "LÝ TƯỞNG", "LÝ BÉO", "LÝ ĐỨC", "CHUỐI CHIÊN", "CHUỐI CHAO", "TRỐC",
    "CỦ CỐT", "THỎ", "GÀ", "SÁY", "LÝ LIỄU LĨNH", "LÝ LÀNG LÁ", "LÝ TRẮNG"
]

# Bảng tra cứu cờ quốc gia mở rộng (FlagCDN ISO Codes)
COUNTRY_FLAGS = {
    # Châu Á & Đông Nam Á
    "vietnam": "vn", "việt nam": "vn",
    "thailand": "th", "thái lan": "th",
    "indonesia": "id", "malaysia": "my", "philippines": "ph", "singapore": "sg",
    "myanmar": "mm", "cambodia": "kh", "campuchia": "kh", "laos": "la",
    "timor": "tl", "timor leste": "tl", "brunei": "bn",
    "japan": "jp", "nhật bản": "jp", "nhật": "jp",
    "south korea": "kr", "hàn quốc": "kr", "hàn": "kr", "korea": "kr",
    "north korea": "kp", "triều tiên": "kp",
    "china": "cn", "trung quốc": "cn", "trung": "cn", "hong kong": "hk",
    "uzbekistan": "uz", "saudi arabia": "sa", "saudi": "sa", "ả rập xê út": "sa",
    "iraq": "iq", "iran": "ir", "qatar": "qa", "uae": "ae", "jordan": "jo",
    "syria": "sy", "bahrain": "bh", "kuwait": "kw", "oman": "om", "palestine": "ps",
    "india": "in", "indian": "in", "ấn độ": "in", "pakistan": "pk", "australia": "au", "úc": "au",

    # Châu Âu
    "england": "gb-eng", "anh": "gb-eng", "spain": "es", "tây ban nha": "es",
    "france": "fr", "pháp": "fr", "germany": "de", "đức": "de", "italy": "it", "ý": "it",
    "portugal": "pt", "bồ đào nha": "pt", "netherlands": "nl", "hà lan": "nl",
    "belgium": "be", "bỉ": "be", "croatia": "hr", "slovenia": "si", "finland": "fi", "phần lan": "fi",
    "belarus": "by", "czechia": "cz", "czech": "cz", "séc": "cz", "scotland": "gb-sct",
    "switzerland": "ch", "thụy sĩ": "ch", "sweden": "se", "thụy điển": "se",
    "norway": "no", "na uy": "no", "denmark": "dk", "đan mạch": "dk",
    "poland": "pl", "ba lan": "pl", "israel": "il", "russia": "ru", "nga": "ru",
    "ukraine": "ua", "turkey": "tr", "thổ nhĩ kỳ": "tr", "greece": "gr", "hy lạp": "gr",
    "austria": "at", "áo": "at", "hungary": "hu",

    # Châu Mỹ
    "brazil": "br", "argentina": "ar", "uruguay": "uy", "colombia": "co",
    "chile": "cl", "usa": "us", "mỹ": "us", "mexico": "mx",

    # Châu Phi
    "egypt": "eg", "ai cập": "eg", "morocco": "ma", "ma rốc": "ma", "senegal": "sn",
    "nigeria": "ng", "ghana": "gh", "cameroon": "cm", "algeria": "dz", "tunisia": "tn",
    "botswana": "bw", "mozambique": "mz", "eritrea": "er", "south africa": "za", "nam phi": "za",

    # Châu Đại Dương
    "fiji": "fj", "new caledonia": "nc", "new zealand": "nz"
}

def sanitize_text(text: str) -> str:
    if not text:
        return ""
    clean = re.sub(r'[\r\n\t]+', ' ', str(text))
    return re.sub(r'\s+', ' ', clean).strip()

def is_ad_or_junk(text: str) -> bool:
    if not text:
        return True
    junk_keywords = ["nhà cái", "fb88", "cược", "trang chủ", "quảng cáo", "gmail.com", "top nhà cái", "lịch thi đấu"]
    t_lower = text.lower()
    return any(k in t_lower for k in junk_keywords)

def clean_teams_title(text: str) -> str:
    if not text:
        return ""
    
    text = re.sub(r'vào lúc\s*\d{1,2}[:h]\d{2}', '', text, flags=re.I)
    text = re.sub(r',?\s*ngày\s*\d{1,2}[/-]\d{1,2}', '', text, flags=re.I)
    text = re.sub(r'\b\d{1,2}[:h]\d{2}\b', '', text)
    text = re.sub(r'\b\d{1,2}[/-]\d{1,2}\b', '', text)
    
    noise_patterns = [
        r'trực tiếp', r'phát trực tiếp', r'xem trực tiếp', r'xem bóng đá', r'phát',
        r'theo bạn thì trận này đội nào sẽ thắng\??', r'chủ nhà', r'hòa', r'đội khách',
        r'lý linh lực', r'lý lên lửa', r'lý la làng', r'nhà đài'
    ]
    for pat in noise_patterns:
        text = re.sub(pat, '', text, flags=re.I)

    text = re.sub(r'^\s*vs\s+|\s+vs\s*$', '', text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip()

def get_team_logo(teams_str: str, raw_card_logo: str = "") -> str:
    # 1. Nếu có logo trực tiếp từ web (không phải icon lửa/default)
    if raw_card_logo and raw_card_logo.startswith("http") and not any(x in raw_card_logo for x in ["fire.svg", "default", "logo.png"]):
        return raw_card_logo

    # 2. Làm sạch tên trận đấu để tra cứu quốc gia (loại bỏ bớt từ phụ như U21, U23, Women...)
    clean_str = re.sub(r'\b(u21|u23|u19|u17|women|fc|vđqg|premier league|league)\b', '', teams_str, flags=re.I).lower()

    for country_key, code in COUNTRY_FLAGS.items():
        if country_key in clean_str:
            return f"https://flagcdn.com/w320/{code}.png"

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
        if ".m3u8" in url.lower():
            if url not in m3u8_history:
                m3u8_history.append(url)

    page.on("request", handle_request)

    teams_title = ""
    blv_name = card_blv
    match_time = ""
    match_date = ""

    try:
        print(f"[*] Đang cào dữ liệu chi tiết: {match_url}")
        page.goto(match_url, timeout=18000, wait_until="domcontentloaded")
        time.sleep(1.8)

        detail_data = page.evaluate('''() => {
            let t1 = '', t2 = '', blv = '', timeStr = '', dateStr = '';
            const bodyText = document.body.innerText || '';

            const teamNodes = document.querySelectorAll('.team-name, .team_name, [class*="team"] .name, .club-name, .team1, .team2');
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

            // Quét tìm BLV trên trang chi tiết
            const blvNodes = document.querySelectorAll('[class*="blv"], [class*="caster"], [class*="commentator"], .author, .speaker');
            for (let node of blvNodes) {
                if (node.innerText) {
                    blv = node.innerText.trim();
                    break;
                }
            }

            if (!blv) {
                const allEls = document.querySelectorAll('*');
                for (let el of allEls) {
                    if (el.children.length === 0 && el.innerText) {
                        const txt = el.innerText.trim();
                        if (txt.includes('🎧') || txt.toUpperCase().includes('BLV')) {
                            blv = txt.replace('🎧', '').replace(/BLV/i, '').strip();
                            break;
                        }
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

        # Lấy danh sách server nguồn phát
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
                before_len = len(m3u8_history)
                try:
                    btn.click()
                    time.sleep(1)

                    if len(m3u8_history) > before_len:
                        captured_streams.append((label, m3u8_history[-1]))
                    elif m3u8_history:
                        captured_streams.append((label, m3u8_history[-1]))
                except Exception:
                    pass
        else:
            time.sleep(1.5)
            if m3u8_history:
                captured_streams.append(("HD1", m3u8_history[-1]))

        if not captured_streams:
            iframe_src = page.evaluate('''() => {
                const iframe = document.querySelector('iframe');
                return iframe ? iframe.src : '';
            }''')
            if iframe_src and iframe_src.startswith("http"):
                captured_streams.append(("HD1", iframe_src))
            else:
                captured_streams.append(("HD1", match_url))

        page.close()
    except Exception as e:
        print(f"[!] Lỗi cào chi tiết {match_url}: {e}")
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
                    page.goto(base_url, timeout=25000, wait_until="domcontentloaded")
                    time.sleep(2)

                    tab_selectors = [
                        "//*[contains(text(), 'Tất cả')]",
                        "//*[contains(text(), 'Hôm nay')]",
                        "//*[contains(text(), 'Ngày mai')]",
                        "//*[contains(text(), 'Bóng đá')]"
                    ]

                    for tab_xpath in tab_selectors:
                        try:
                            tab_btn = page.query_selector(f"xpath={tab_xpath}")
                            if tab_btn and tab_btn.is_visible():
                                tab_btn.click()
                                time.sleep(0.8)
                        except:
                            pass

                        for _ in range(8):
                            page.evaluate("window.scrollBy(0, 1500)")
                            time.sleep(0.3)

                        extracted = page.evaluate('''() => {
                            const results = [];
                            const links = document.querySelectorAll('a[href]');

                            links.forEach(a => {
                                const href = a.getAttribute('href');
                                if (!href || href === '#' || href.startsWith('javascript:')) return;
                                const fullUrl = href.startsWith('http') ? href : window.location.origin + href;

                                if (/(truc-tiep|match|live|phong|xem|tran|watch|room|bong-da)/i.test(fullUrl) || fullUrl.split('/').pop().length > 10) {
                                    let container = a.closest('div, li, article') || a.parentElement;
                                    const text = container ? container.innerText : a.innerText;
                                    if (!text || text.length < 5) return;

                                    let logoUrl = '';
                                    const img = container ? container.querySelector('img') : null;
                                    if (img) logoUrl = img.getAttribute('src') || img.getAttribute('data-src') || '';

                                    let status = 'upcoming';
                                    const htmlAll = container ? container.innerHTML.toLowerCase() : '';
                                    if (htmlAll.includes('live') || text.includes('Đang diễn ra') || text.includes('Hiệp 1') || text.includes('Hiệp 2')) {
                                        status = 'live';
                                    }

                                    results.push({
                                        url: fullUrl,
                                        rawText: text,
                                        logo: logoUrl,
                                        status: status
                                    });
                                }
                            });
                            return results;
                        }''')

                        for item in extracted:
                            all_extracted_matches[item['url']] = item

                    page.close()

                    if len(all_extracted_matches) > 0:
                        print(f"[+] Đã tìm thấy {len(all_extracted_matches)} trận đấu!")
                        break
                except Exception as err:
                    print(f"[!] Lỗi kết nối {base_url}: {err}")

            parsed_items = []
            raw_matches = list(all_extracted_matches.values())

            if raw_matches:
                print(f"\n[*] Đang bóc tách thông tin chi tiết...")
                for item in raw_matches:
                    match_url = item['url']
                    card_text = sanitize_text(item['rawText'])
                    
                    if is_ad_or_junk(card_text):
                        continue

                    status = item['status']
                    card_blv = extract_blv_from_text(card_text)
                    teams_from_page, blv_from_page, time_from_page, date_from_page, streams = scrape_match_detail(context, match_url, card_blv)

                    teams_title = teams_from_page
                    if not teams_title:
                        match_vs = re.search(r'([A-Za-zÀ-ỹ0-9\s\.]{2,25})\s+vs\s+([A-Za-zÀ-ỹ0-9\s\.]{2,25})', card_text, re.I)
                        if match_vs:
                            teams_title = f"{clean_teams_title(match_vs.group(1))} vs {clean_teams_title(match_vs.group(2))}"
                        else:
                            teams_title = clean_teams_title(card_text)

                    teams_title = clean_teams_title(teams_title)
                    if is_ad_or_junk(teams_title) or len(teams_title) < 3:
                        continue

                    # FIX TRIỆT ĐỂ LỖI THIẾU BLV: Tự động gán BLV mặc định nếu web không ghi rõ
                    blv_final = blv_from_page if blv_from_page else card_blv
                    if not blv_final:
                        blv_final = DEFAULT_BLV

                    extracted_time = time_from_page
                    if not extracted_time:
                        time_m = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', card_text)
                        extracted_time = f"{time_m.group(1).zfill(2)}:{time_m.group(2)}" if time_m else "13:00"

                    match_date = date_from_page
                    if not match_date:
                        date_m = re.search(r'\b(\d{1,2})[/.-](\d{1,2})\b', card_text)
                        match_date = f"{date_m.group(1).zfill(2)}/{date_m.group(2).zfill(2)}" if date_m else today_str

                    status_dot = "🟢 " if status == 'live' else "🟡 "
                    card_logo = get_team_logo(teams_title, item['logo'])

                    try:
                        d, m = map(int, match_date.split('/'))
                        h, mins = map(int, extracted_time.split(':'))
                        curr_year = datetime.now(vn_tz).year
                        dt_obj = datetime(curr_year, m, d, h, mins, tzinfo=vn_tz)
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
                                blv_part = f" ({blv_final})"

                            full_title = sanitize_text(f"{status_dot}{extracted_time} {match_date} ⚽ {teams_title}{blv_part}{server_part}{geo_tag}")

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

    # Sắp xếp danh sách theo giờ và xuất ra playlist.m3u
    if parsed_items:
        parsed_items.sort(key=lambda x: (0 if x['status'] == 'live' else 1, x['dt']))

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

        print(f"\n[*] Hoàn tất! Đã xuất {len(parsed_items)} luồng trận đấu vào {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
