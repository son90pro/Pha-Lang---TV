import time
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# CAU HINH CHUNG
DOMAINS = [
    "https://phalang.tv/",
    "https://phalang1.tv/",
    "https://phalang2.tv/"
]
REFERER_URL = "https://phalang.tv/"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phá Làng TV"
DEFAULT_LOGO = "https://flagcdn.com/w320/vn.png"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# DANH SACH BLV PHÁ LÀNG TV
KNOWN_BLVS = [
    "Lý Linh", "Lý Lên Lửa", "Lý La Làng", "Lý Bò", "Lý Thông", "Lý Tưởng",
    "Lý Béo", "Lý A", "Lý Đức", "Chuối Chiên", "Chuối Chao", "Trốc", "Củ Cốt",
    "Thỏ", "Gà", "Nhà đài"
]

LEAGUE_SLUG_PATTERNS = [
    r'^(?:vdqg|vdqg-[a-z0-9]+)[-_]*',
    r'^(?:asian-games|asiad|asean-games)[-_]*',
    r'^(?:fifa-asean-cup|fifa-asean|asean-cup|aff-cup|aff-shopee-cup)[-_]*',
    r'^(?:meiji-yasuda-j3-league|j3-league|j1-league|j2-league|j-league)[-_]*',
    r'^(?:liga-mx|la-liga|serie-a|bundesliga|ligue-1|premier-league|ngoai-hang-anh)[-_]*',
    r'^(?:uefa-nations-league|nations-league|uefa-champions-league|champions-league|cup-c1)[-_]*',
    r'^(?:giao-huu-quoc-te|giao-huu|international-friendlies|friendlies)[-_]*',
    r'^(?:sea-games|world-cup|euro|copa-america|afc-champions-league|afc-cup)[-_]*',
    r'^(?:v-league|vleague|giai-vong-loai|vong-loai)[-_]*'
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
    "india": "https://flagcdn.com/w320/in.png", "singapore": "https://flagcdn.com/w320/sg.png",
    "australia": "https://flagcdn.com/w320/au.png", "úc": "https://flagcdn.com/w320/au.png",
    "germany": "https://flagcdn.com/w320/de.png", "đức": "https://flagcdn.com/w320/de.png",
    "spain": "https://flagcdn.com/w320/es.png", "tây ban nha": "https://flagcdn.com/w320/es.png",
    "france": "https://flagcdn.com/w320/fr.png", "pháp": "https://flagcdn.com/w320/fr.png",
    "italy": "https://flagcdn.com/w320/it.png", "ý": "https://flagcdn.com/w320/it.png",
    "england": "https://flagcdn.com/w320/gb-eng.png", "anh": "https://flagcdn.com/w320/gb-eng.png",
    "brazil": "https://flagcdn.com/w320/br.png", "argentina": "https://flagcdn.com/w320/ar.png"
}

def to_slug(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower().replace('đ', 'd')
    return re.sub(r'[^a-z0-9]', '', text)

def is_junk_hash(word: str) -> bool:
    """Kiểm tra và loại bỏ các mã ID phòng rác như y39mp1hdvw4dmoj, 5e47f28fed4441c7be5"""
    w = word.lower()
    if len(w) >= 7 and re.search(r'\d', w) and re.search(r'[a-z]', w):
        return True
    if len(w) >= 12 and re.match(r'^[a-z0-9]+$', w):
        return True
    return False

def clean_word(w: str) -> str:
    w_low = w.lower()
    if w_low in ['nu', 'nữ', 'women']: return 'Women'
    if w_low in ['nam', 'men']: return 'Men'
    if w_low in ['u23', 'u21', 'u20', 'u19', 'u18', 'u17', 'u16']: return w.upper()
    if w_low in ['fc', 'ac', 'sc', 'as', 'cd', 'pr', 'dpr']: return w.upper()
    return w.capitalize()

def parse_teams_from_slug(url: str) -> str:
    try:
        match_slug = re.search(r'/(?:truc-tiep|match|live|room|xem|phong|link|stream)/([^/?#]+)', url)
        if not match_slug:
            return ""
        slug = match_slug.group(1).lower()
        
        # Xóa ID phòng rác ở cuối slug
        slug = re.sub(r'-[a-z0-9]{8,}(?=$|\?|#)', '', slug)
        
        if '-vs-' in slug:
            parts = slug.split('-vs-')
            left, right = parts[0], parts[1]

            left = re.sub(r'^(?:blv|caster|ga|ly)[-_]*', '', left, flags=re.I)
            caster_words = ["troc", "tru", "chuoi", "nho", "kem", "say", "sais", "chao", "la", "ngao", "to", "tay", "lap", "ky", "beo", "sieu", "ga", "ly"]
            pattern_caster = r'^(?:' + '|'.join(caster_words) + r')[-_]*'
            while re.match(pattern_caster, left, flags=re.I):
                left = re.sub(pattern_caster, '', left, flags=re.I)

            for l_pat in LEAGUE_SLUG_PATTERNS:
                left = re.sub(l_pat, '', left, flags=re.I)

            left = re.sub(r'^(?:truc-tiep|xem-truc-tiep|match|live)[-_]*', '', left, flags=re.I)

            right = re.sub(r'-(?:luc|ngay|time|fhd|hls|\d{2}h\d{2}|\d{3,4}|\d{1,2}-\d{1,2}|\d{4}).*$', '', right, flags=re.I)
            right = re.sub(r'-\d+$', '', right)

            # Lọc từ và loại bỏ mã hash rác
            t1_words = [clean_word(w) for w in left.split('-') if w and not w.isdigit() and not is_junk_hash(w)]
            t2_words = [clean_word(w) for w in right.split('-') if w and not w.isdigit() and not is_junk_hash(w)]

            t1 = " ".join(t1_words).strip()
            t2 = " ".join(t2_words).strip()

            if t1 and t2 and len(t1) > 1 and len(t2) > 1:
                return f"{t1} vs {t2}"
    except Exception:
        pass
    return ""

def get_team_logo(teams_str: str, raw_card_logo: str = "") -> str:
    t_lower = teams_str.lower()
    for key, url in LOGOS.items():
        if key in t_lower:
            return url
    if raw_card_logo and raw_card_logo.startswith("http"):
        return raw_card_logo
    return DEFAULT_LOGO

def get_live_stream_and_blv(context, match_url: str):
    """Truy cập vào trang trận đấu để bắt link .m3u8 thực tế và bóc tách tên BLV chính xác"""
    page = context.new_page()
    captured_m3u8 = ""

    def handle_request(req):
        nonlocal captured_m3u8
        url = req.url
        if ".m3u8" in url and not captured_m3u8:
            if any(k in url for k in ["index", "playlist", "live", "stream", "chunk", "hls"]):
                captured_m3u8 = url

    page.on("request", handle_request)
    blv_name = ""

    try:
        page.goto(match_url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(2.5) # Chờ player nạp stream

        if not captured_m3u8:
            captured_m3u8 = page.evaluate('''() => {
                const v = document.querySelector('video');
                if (v && v.src && v.src.includes('.m3u8')) return v.src;
                const iframes = document.querySelectorAll('iframe');
                for (let f of iframes) {
                    if (f.src && f.src.includes('.m3u8')) return f.src;
                }
                return '';
            }''')

        body_text = page.evaluate("() => document.body.innerText || ''")
        for b in KNOWN_BLVS:
            if b.lower() in body_text.lower():
                blv_name = b
                break

        if not blv_name:
            blv_m = re.search(r'(?:BLV|Caster)\s+([A-Za-zÀ-ỹ0-9\s]{2,15})', body_text, re.I)
            if blv_m:
                blv_name = blv_m.group(1).strip()

        page.close()
    except Exception as e:
        print(f"[!] Lỗi truy cập phòng {match_url}: {e}")
        try:
            page.close()
        except:
            pass

    return captured_m3u8, blv_name

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
                print(f"[*] Kết nối tới: {base_url}")
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
                        const links = document.querySelectorAll('a[href*="/truc-tiep/"], a[href*="/match/"], a[href*="/live/"], a[href*="/xem/"], a[href*="/room/"]');

                        links.forEach(a => {
                            const href = a.getAttribute('href');
                            if (!href) return;
                            const fullUrl = href.startsWith('http') ? href : window.location.origin + href;
                            if (seenUrls.has(fullUrl)) return;
                            seenUrls.add(fullUrl);

                            let container = a;
                            let parent = a.parentElement;
                            while (parent && parent.tagName !== 'BODY') {
                                if (parent.innerText && parent.innerText.length > 20 && parent.innerText.length < 500) {
                                    container = parent;
                                    break;
                                }
                                parent = parent.parentElement;
                            }

                            const text = container.innerText || a.innerText || '';
                            let logoUrl = '';
                            const imgs = container.querySelectorAll('img');
                            imgs.forEach(img => {
                                if (!logoUrl) {
                                    const src = img.getAttribute('src') || img.getAttribute('data-src') || '';
                                    if (src && !src.includes('avatar') && !src.includes('icon') && !src.includes('gif')) {
                                        logoUrl = src;
                                    }
                                }
                            });
                            if (logoUrl && logoUrl.startsWith('//')) logoUrl = 'https:' + logoUrl;
                            else if (logoUrl && !logoUrl.startsWith('http')) logoUrl = window.location.origin + logoUrl;

                            const htmlAll = container.innerHTML.toLowerCase();
                            let status = 'upcoming';
                            if (htmlAll.includes('live') || text.includes('Đang diễn ra') || text.includes('Hiệp 1') || text.includes('Hiệp 2')) {
                                status = 'live';
                            } else if (text.includes('Sắp diễn ra') || text.includes('Chuẩn bị')) {
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
                        print(f"[+] Lấy danh sách thành công: {len(raw_matches)} trận từ {base_url}")
                        break
                except Exception as err:
                    print(f"[!] Lỗi kết nối {base_url}: {err}")

            # TRUY CẬP TỪNG PHÒNG ĐỂ BẮT LINK STREAM M3U8 THỰC TẾ & TÊN BLV
            parsed_items = []
            if raw_matches:
                print("[*] Đang bóc tách link stream thực tế & BLV cho từng trận...")
                for item in raw_matches:
                    match_url = item['url']
                    card_text = item['rawText']
                    status = item['status']

                    # Lấy link stream m3u8 chuẩn và tên BLV từ phòng live
                    real_m3u8, room_blv = get_live_stream_and_blv(context, match_url)

                    # Tên BLV ưu tiên từ trang live, sau đó mới tìm ở card
                    blv_name = room_blv if room_blv else "Nhà đài"
                    if blv_name == "Nhà đài":
                        for b in KNOWN_BLVS:
                            if b.lower() in card_text.lower():
                                blv_name = b
                                break

                    # Làm sạch tên 2 đội bóng
                    teams_title = parse_teams_from_slug(match_url)
                    if not teams_title:
                        match_vs = re.search(r'([A-Za-zÀ-ỹ0-9\s\.]{2,25})\s+vs\s+([A-Za-zÀ-ỹ0-9\s\.]{2,25})', card_text, re.I)
                        if match_vs:
                            t1 = match_vs.group(1).strip()
                            t2 = match_vs.group(2).strip()
                            teams_title = f"{t1} vs {t2}"

                    if not teams_title:
                        teams_title = "Trận đấu Trực Tiếp"

                    card_logo = get_team_logo(teams_title, item['logo'])

                    sport_icon = "⚽"
                    text_lower = card_text.lower()
                    if any(k in text_lower for k in ["bóng chuyền", "volleyball"]):
                        sport_icon = "🏐"
                    elif any(k in text_lower for k in ["bóng rổ", "basketball"]):
                        sport_icon = "🏀"

                    time_m = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', card_text)
                    extracted_time = f"{time_m.group(1).zfill(2)}:{time_m.group(2)}" if time_m else "13:00"

                    date_m = re.search(r'\b(\d{1,2})[/.-](\d{1,2})\b', card_text)
                    match_date = f"{date_m.group(1).zfill(2)}/{date_m.group(2).zfill(2)}" if date_m else today_str

                    status_dot = "🟢 " if status == 'live' else ("🟡 " if status == 'soon' else "")

                    extra_tags = ""
                    if "hd2" in card_text.lower() or "hd2" in match_url.lower():
                        extra_tags += " [HD2]"
                    if "geo" in card_text.lower() or "geo" in match_url.lower():
                        extra_tags += " [geo]"

                    # Định dạng tiêu đề hiển thị chuẩn 100%
                    full_title = f"{status_dot}{extracted_time} {match_date} {sport_icon} {teams_title} ({blv_name}){extra_tags}".strip()

                    # Nếu không bắt được link m3u8 động thì dùng fallback
                    stream_url = real_m3u8 if real_m3u8 else match_url

                    try:
                        d, m = map(int, match_date.split('/'))
                        h, mins = map(int, extracted_time.split(':'))
                        dt_obj = datetime(datetime.now(vn_tz).year, m, d, h, mins, tzinfo=vn_tz)
                    except Exception:
                        dt_obj = datetime(2099, 1, 1, 0, 0, tzinfo=vn_tz)

                    parsed_items.append({
                        "title": full_title,
                        "logo": card_logo,
                        "stream_url": stream_url,
                        "dt": dt_obj,
                        "status": status,
                        "match_url": match_url
                    })

            browser.close()

    except Exception as e:
        print(f"[!] Lỗi hệ thống Playwright: {e}")

    # GHI FILE PLAYLIST M3U DÀNH CHO IPTV / TIVIMATE
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

    print(f"[*] Xuất thành công {len(parsed_items)} trận vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
    
