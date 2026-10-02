import re
import json

def build_m3u_playlist(matches_data):
    """
    Tạo danh sách IPTV M3U chuẩn cho Phá Làng TV.
    :param matches_data: List chứa thông tin các trận đấu thu thập được từ API/Web
    """
    m3u_lines = ["#EXTM3U\n"]
    
    # Header cố định cho trình phát IPTV
    REFERRER_TAG = "#EXTVLCOPT:http-referrer=https://phalang.live/"

    for item in matches_data:
        logo = item.get("logo", "")
        group = item.get("group", "Phá Làng TV")
        time_str = item.get("time", "")
        sport = item.get("sport", "⚽")
        title = item.get("title", "")
        is_live = "🟢 " if item.get("is_live", False) else ""
        
        blv = item.get("blv_name", "").strip()
        blv_label = f"({blv})" if blv else ""

        # LẤY ĐÚNG HASH ID RIÊNG CHO TỪNG NGUỒN
        # Đảm bảo không lấy nhầm Hash ID của Nhà đài gán cho digitalcdn
        digitalcdn_id = item.get("digitalcdn_id")  # VD: 56ab06ef2994451995eebfbdf3ce4c8c
        nhadai_id = item.get("nhadai_id")          # VD: af1e3c5362ae48452c6e328062a5800b

        # 1. Luồng BLV - Sever chính (pull.digitalcdn.net)
        if digitalcdn_id:
            extinf = f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group}" , {is_live}{time_str} {sport} {title} {blv_label} [geo]'
            # Giữ URL sạch, KHÔNG cộng thêm '|Referer=...' ở cuối
            clean_url = f"https://pull.digitalcdn.net/live/{digitalcdn_id}/index.m3u8"
            m3u_lines.extend([extinf, REFERRER_TAG, clean_url, ""])

        # 2. Luồng BLV - Server dự phòng (pull1.digitalcdn.net)
        if digitalcdn_id:
            extinf_hd2 = f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group}" , {is_live}{time_str} {sport} {title} {blv_label} (HD2) [geo]'
            clean_url_hd2 = f"https://pull1.digitalcdn.net/live/{digitalcdn_id}/index.m3u8"
            m3u_lines.extend([extinf_hd2, REFERRER_TAG, clean_url_hd2, ""])

        # 3. Luồng Nhà đài (lilive1.eu.cc)
        if nhadai_id:
            extinf_nhadai = f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group}" , {is_live}{time_str} {sport} {title} (Nhà đài)'
            clean_url_nhadai = f"https://lilive1.eu.cc/live/{nhadai_id}/playlist.m3u8"
            m3u_lines.extend([extinf_nhadai, REFERRER_TAG, clean_url_nhadai, ""])

    return "\n".join(m3u_lines)


# --- NẾU BẠN BẮT LINK BẰNG REGEX TỪ SOURCE WEB/API ---
def extract_stream_ids(html_or_json_text):
    """
    Hàm mẫu giúp tách đúng 2 Hash ID khác nhau từ dữ liệu thô
    """
    # Regex tìm Hash ID của digitalcdn (Luồng BLV)
    digitalcdn_match = re.search(r'pull(?:\d)?\.digitalcdn\.net/live/([a-f0-9]{32})/', html_or_json_text)
    digitalcdn_id = digitalcdn_match.group(1) if digitalcdn_match else None

    # Regex tìm Hash ID của lilive1 (Luồng Nhà đài)
    nhadai_match = re.search(r'lilive1\.eu\.cc/live/([a-f0-9]{32})/', html_or_json_text)
    nhadai_id = nhadai_match.group(1) if nhadai_match else None

    return digitalcdn_id, nhadai_id
