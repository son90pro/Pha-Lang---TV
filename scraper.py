import time
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

REFERER_URL = "https://phalang.tv/"
OUTPUT_FILE = "playlist.m3u"
GROUP_NAME = "Phá Làng TV"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# DANH SÁCH MẪU TIỀN TỐ TÊN GIẢI ĐẤU CẦN CẮT BỎ BẰNG MỌI GIÁ
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

# Kho Logo & Cờ Quốc gia chuẩn TiviMate
LOGOS = {
    # Châu Âu
    "netherlands": "https://flagcdn.com/w320/nl.png", "hà lan": "https://flagcdn.com/w320/nl.png",
    "germany": "https://flagcdn.com/w320/de.png", "đức": "https://flagcdn.com/w320/de.png",
    "spain": "https://flagcdn.com/w320/es.png", "tây ban nha": "https://flagcdn.com/w320/es.png",
    "france": "https://flagcdn.com/w320/fr.png", "pháp": "https://flagcdn.com/w320/fr.png",
    "italy": "https://flagcdn.com/w320/it.png", "ý": "https://flagcdn.com/w320/it.png",
    "portugal": "https://flagcdn.com/w320/pt.png", "bồ đào nha": "https://flagcdn.com/w320/pt.png",
    "england": "https://flagcdn.com/w320/gb-eng.png", "anh": "https://flagcdn.com/w320/gb-eng.png",
    "slovakia": "https://flagcdn.com/w320/sk.png", "armenia": "https://flagcdn.com/w320/am.png", 
    "latvia": "https://flagcdn.com/w320/lv.png", "turkiye": "https://flagcdn.com/w320/tr.png", "turkey": "https://flagcdn.com/w320/tr.png", "thổ nhĩ kỳ": "https://flagcdn.com/w320/tr.png",
    "belgium": "https://flagcdn.com/w320/be.png", "bỉ": "https://flagcdn.com/w320/be.png",
    "poland": "https://flagcdn.com/w320/pl.png", "ba lan": "https://flagcdn.com/w320/pl.png",
    "hungary": "https://flagcdn.com/w320/hu.png", "hungari": "https://flagcdn.com/w320/hu.png", "ukraine": "https://flagcdn.com/w320/ua.png",
    "finland": "https://flagcdn.com/w320/fi.png", "phần lan": "https://flagcdn.com/w320/fi.png",
    "sweden": "https://flagcdn.com/w320/se.png", "thụy điển": "https://flagcdn.com/w320/se.png",
    "romania": "https://flagcdn.com/w320/ro.png", "croatia": "https://flagcdn.com/w320/hr.png",

    # Châu Á & Đông Nam Á
    "vietnam": "https://flagcdn.com/w320/vn.png", "việt nam": "https://flagcdn.com/w320/vn.png",
    "thailand": "https://flagcdn.com/w320/th.png", "thái lan": "https://flagcdn.com/w320/th.png",
    "indonesia": "https://flagcdn.com/w320/id.png", "malaysia": "https://flagcdn.com/w320/my.png",
    "japan": "https://flagcdn.com/w320/jp.png", "nhật bản": "https://flagcdn.com/w320/jp.png",
    "south korea": "https://flagcdn.com/w320/kr.png", "hàn quốc": "https://flagcdn.com/w320/kr.png", "korea": "https://flagcdn.com/w320/kr.png",
    "china": "https://flagcdn.com/w320/cn.png", "trung quốc": "https://flagcdn.com/w320/cn.png",
    "india": "https://flagcdn.com/w320/in.png", "ấn độ": "https://flagcdn.com/w320/in.png",
    "singapore": "https://flagcdn.com/w320/sg.png", "bangladesh": "https://flagcdn.com/w320/bd.png",
    "australia": "https://flagcdn.com/w320/au.png", "úc": "https://flagcdn.com/w320/au.png",
    "pakistan": "https://flagcdn.com/w320/pk.png",

    # Mỹ & Châu Phi & Các CLB
    "panama": "https://flagcdn.com/w320/pa.png", "jamaica": "https://flagcdn.com/w320/jm.png",
    "guatemala": "https://flagcdn.com/w320/gt.png", "morocco": "https://flagcdn.com/w320/ma.png", "ma rốc": "https://flagcdn.com/w320/ma.png",
    "gabon": "https://flagcdn.com/w320/ga.png", "colombia": "https://flagcdn.com/w320/co.png", "chico": "https://flagcdn.com/w320/co.png", "pasto": "https://flagcdn.com/w320/co.png",
    "mexico": "https://flagcdn.com/w320/mx.png", "atlante": "https://flagcdn.com/w320/mx.png", "tijuana": "https://flagcdn.com/w320/mx.png", "monterrey": "https://flagcdn.com/w320/mx.png", "atlas": "https://flagcdn.com/w320/mx.png",
    "brazil": "https://flagcdn.com/w320/br.png", "argentina": "https://flagcdn.com/w320/ar.png",
    "uruguay": "https://flagcdn.com/w320/uy.png", "ecuador": "https://flagcdn.com/w320/ec.png",
    "jaca": "https://flagcdn.com/w320/jp.png", "j3": "https://flagcdn.com/w320/jp.png"
}

def to_slug(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.lower().replace('đ', 'd')
    return re.sub(r'[^a-z0-9]', '', text)

def clean_word(w: str) -> str:
    w_low = w.lower()
    if w_low in ['nu', 'nữ', 'women']: return 'W'
    if w_low in ['nam', 'men']: return 'Men'
    if w_low in ['u23', 'u21', 'u20', 'u19', 'u18', 'u17', 'u16']: return w.upper()
    if w_low in ['fc', 'ac', 'sc', 'as', 'cd', 'pr', 'dpr']: return w.upper()
    return w.capitalize()

def parse_teams_from_slug(url: str) -> str:
    """Bóc tách tên 2 đội chính xác từ URL slug, lọc bỏ hoàn toàn Tên Giải Đấu & Tên BLV"""
    try:
        match_slug = re.search(r'/(?:truc-tiep|match|live|room|xem|phong|link|stream)/([^/?#]+)', url)
        if not match_slug:
            return ""
        slug = match_slug.group(1).lower()
        if '-vs-' in slug:
            parts = slug.split('-vs-')
            left, right = parts[0], parts[1]

            # 1. Loại bỏ các tiền tố xưng hô BLV / nhà cái
            left = re.sub(r'^(?:blv|caster|ga|ly)[-_]*', '', left, flags=re.I)
            
            # 2. Loại bỏ các tên BLV dính ở đầu slug
            caster_words = [
                "troc", "tru", "chuoi", "nho", "kem", "say", "sais", "chao", 
                "la", "ngao", "to", "tay", "lap", "ky", "beo", "sieu", "ga", "ly"
            ]
            pattern_caster = r'^(?:' + '|'.join(caster_words) + r')[-_]*'
            while re.match(pattern_caster, left, flags=re.I):
                left = re.sub(pattern_caster, '', left, flags=re.I)

            # 3. LOẠI BỎ TRIỆT ĐỂ TÊN GIẢI ĐẤU DÍNH Ở ĐẦU TÊN ĐỘI 1
            for l_pat in LEAGUE_SLUG_PATTERNS:
                left = re.sub(l_pat, '', left, flags=re.I)

            left = re.sub(r'^(?:truc-tiep|xem-truc-tiep|match|live)[-_]*', '', left, flags=re.I)

            # 4. Làm sạch vế phải (Đội 2) khỏi thông số thời gian
            right = re.sub(r'-(?:luc|ngay|time|fhd|hls|\d{2}h\d{2}|\d{3,4}|\d{1,2}-\d{1,2}|\d{4}).*$', '', right, flags=re.I)
            right = re.sub(r'-\d+$', '', right)

            t1_words = [clean_word(w) for w in left.split('-') if w and not w.isdigit()]
            t2_words = [clean_word(w) for w in right.split('-') if w and not w.isdigit()]

            t1 = " ".join(t1_words).strip()
            t2 = " ".join(t2_words).strip()

            if t1 and t2 and len(t1) > 1 and len(t2) > 1:
                return f"{t1} vs {t2}"
    except Exception:
        pass
    return ""

def extract_teams_from_lines(card_text: str) -> str:
    """Bóc tách tên 2 đội từ văn bản thô khi URL không chứa từ khóa -vs-"""
    lines = [line.strip() for line in card_text.split('\n') if line.strip()]
    candidates = []
    
    junk_patterns = [
        r'\b\d{1,2}[:h/]\d{2}\b', r'\b\d{1,2}/\d{1,2}\b',
        r'\b(?:fhd|hls|live|trực tiếp|đang diễn ra|sắp diễn ra|hiệp 1|hiệp 2|hoàn tất|kết thúc)\b',
        r'\b(?:chuối|trốc|blv|caster)\s+[a-zA-Z0-9_À-ỹ]+\b',
        r'^\s*(?:chuối|trốc|blv|caster)\s*$',
        r'\b(?:vđqg|asian games|fifa asean cup|liga mx|j3 league|v-league|giao hữu quốc tế|uefa nations league)\b'
    ]

    for line in lines:
        l_clean = line
        for pat in junk_patterns:
            l_clean = re.sub(pat, '', l_clean, flags=re.I).strip()
            
        if not l_clean or len(l_clean) < 2:
            continue

        candidates.append(l_clean)

    if len(candidates) >= 2:
        return f"{candidates[0]} vs {candidates[1]}"
    elif len(candidates) == 1:
        return candidates[0]
    return ""

def is_league_or_generic_logo(url: str) -> bool:
    """Kiểm tra nếu logo thu thập được chỉ là logo giải đấu chung"""
    if not url:
        return True
    u_low = url.lower()
    junk_terms = ['liga', 'league', 'j3', 'j1', 'banner', 'default', 'icon', 'un.png', 'avatar', 'logo_league', 'comp']
    for jt in junk_terms:
        if jt in u_low:
            return True
    return False

def get_team_logo(teams_str: str, raw_card_logo: str = "") -> str:
    """Ưu tiên tìm Cờ/Logo CLB tương ứng với tên 2 đội bóng"""
    t_lower = teams_str.lower()
    for key, url in LOGOS.items():
        if key in t_lower:
            return url

    if raw_card_logo and raw_card_logo.startswith("http") and not is_league_or_generic_logo(raw_card_logo):
        return raw_card_logo

    return DEFAULT_LOGO

def build_emergency_channels():
    vn_tz = timezone(timedelta(hours=7))
    now_str = datetime.now(vn_tz).strftime("%H:%M %d/%m")
    items = []
    for blv in KNOWN_BLVS:
        slug = to_slug(blv)
        stream_url = CASTER_STREAM_MAP.get(slug, f"https://stm9ee346727718.stream.hdplaylink.com/cctvlive/{slug}hd/playlist.m3u8")
        title = f"🟢 {now_str} ⚽ Trực Tiếp ({blv}) [FHD] [hls]"
        items.append({
            "title": title,
            "logo": DEFAULT_LOGO,
            "stream_url": stream_url,
            "status": "live",
            "dt": datetime.now(vn_tz),
            "match_url": f"emergency-{slug}"
        })
    return items

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
                print(f"[*] Thử kết nối tới: {base_url}")
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
                        print(f"[+] Lấy thành công {len(raw_matches)} trận từ {base_url}")
                        break
                except Exception as err:
                    print(f"[!] Tên miền {base_url} lỗi: {err}")

            browser.close()

    except Exception as e:
        print(f"[!] Lỗi hệ thống Playwright: {e}")

    parsed_items = []

    if raw_matches:
        for item in raw_matches:
            match_url = item['url']
            card_text = item['rawText']
            status = item['status']

            # 1. Bóc tách tên BLV
            blv_name = "Chuối Chiên"
            for b in KNOWN_BLVS:
                if b.lower() in card_text.lower() or to_slug(b) in match_url.lower():
                    blv_name = b
                    break

            # 2. Bóc tách tên 2 Đội bóng (Giải mã Slug chuẩn)
            teams_title = parse_teams_from_slug(match_url)

            if not teams_title:
                match_vs = re.search(r'([A-Za-zÀ-ỹ0-9\s\.]{2,25})\s+vs\s+([A-Za-zÀ-ỹ0-9\s\.]{2,25})', card_text, re.I)
                if match_vs:
                    t1 = match_vs.group(1).strip()
                    t2 = match_vs.group(2).strip()
                    teams_title = f"{t1} vs {t2}"

            if not teams_title:
                teams_title = extract_teams_from_lines(card_text)

            if not teams_title:
                teams_title = "Trận đấu Trực Tiếp"

            # 3. Tự động chọn Logo / Cờ Quốc gia
            card_logo = get_team_logo(teams_title, item['logo'])

            # 4. Icon môn thể thao
            sport_icon = "⚽"
            text_lower = card_text.lower()
            if any(k in text_lower for k in ["bóng chuyền", "volleyball"]):
                sport_icon = "🏐"
            elif any(k in text_lower for k in ["bóng rổ", "basketball"]):
                sport_icon = "🏀"
            elif any(k in text_lower for k in ["tennis", "quần vợt"]):
                sport_icon = "🎾"

            # 5. Bóc tách Thời gian
            time_m = re.search(r'\b(2[0-3]|[0-1]?\d)[:h](\d{2})\b', card_text)
            extracted_time = f"{time_m.group(1).zfill(2)}:{time_m.group(2)}" if time_m else "20:00"

            date_m = re.search(r'\b(\d{1,2})[/.-](\d{1,2})\b', card_text)
            match_date = f"{date_m.group(1).zfill(2)}/{date_m.group(2).zfill(2)}" if date_m else today_str

            # Dấu chấm trạng thái TiviMate chuẩn
            status_dot = ""
            if status == 'live':
                status_dot = "🟢 "
            elif status == 'soon':
                status_dot = "🟡 "

            # Tiêu đề kênh chuẩn 100% hình mẫu: 🟢 08:00 26/09 ⚽ Atlante FC vs Monterrey (Chuối Chao) [FHD] [hls]
            full_title = f"{status_dot}{extracted_time} {match_date} {sport_icon} {teams_title} ({blv_name}) [FHD] [hls]"

            blv_slug = to_slug(blv_name)
            stream_url = CASTER_STREAM_MAP.get(
                blv_slug, 
                f"https://stm9ee346727718.stream.hdplaylink.com/cctvlive/{blv_slug}hd/playlist.m3u8"
            )

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

        parsed_items.sort(key=lambda x: (x['status'] != 'live', x['status'] != 'soon', x['dt']))

    if not parsed_items:
        print("[!] Kích hoạt danh sách kênh dự phòng khẩn cấp!")
        parsed_items = build_emergency_channels()

    # GHI FILE PLAYLIST M3U DÀNH CHO TIVIMATE
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write('#EXTM3U\n\n')
        seen_urls = set()
        for item in parsed_items:
            if item['match_url'] in seen_urls:
                continue
            seen_urls.add(item['match_url'])

            f.write(f'#EXTINF:-1 tvg-logo="{item["logo"]}" group-title="{GROUP_NAME}" , {item["title"]} \n')
            f.write(f'#EXTVLCOPT:http-referrer={REFERER_URL}\n')
            f.write(f'#EXTVLCOPT:http-user-agent={USER_AGENT}\n')
            f.write(f'{item["stream_url"]}\n\n')

    print(f"[*] Xuất thành công {len(parsed_items)} trận vào file {OUTPUT_FILE}")

if __name__ == "__main__":
    run_scraper()
            
