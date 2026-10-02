import re
import json
import requests

def extract_stream_ids(html_or_json_text):
    """
    Hàm giúp tách đúng 2 Hash ID khác nhau từ dữ liệu thô
    """
    digitalcdn_match = re.search(r'pull(?:\d)?\.digitalcdn\.net/live/([a-f0-9]{32})/', html_or_json_text)
    digitalcdn_id = digitalcdn_match.group(1) if digitalcdn_match else None

    nhadai_match = re.search(r'lilive1\.eu\.cc/live/([a-f0-9]{32})/', html_or_json_text)
    nhadai_id = nhadai_match.group(1) if nhadai_match else None

    return digitalcdn_id, nhadai_id


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

        digitalcdn_id = item.get("digitalcdn_id")
        nhadai_id = item.get("nhadai_id")

        # 1. Luồng BLV - Server chính (pull.digitalcdn.net)
        if digitalcdn_id:
            extinf = f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group}" , {is_live}{time_str} {sport} {title} {blv_label} [geo]'
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


def main():
    # Danh sách chứa các trận đấu bóc tách được
    matches_data = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://phalang.live/"
    }

    try:
        # TODO: Thêm logic request / cào dữ liệu trận đấu của bạn tại đây
        # response = requests.get("https://phalang.live/api/matches", headers=headers, timeout=15)
        # matches_data = response.json()
        pass
    except Exception as e:
        print(f"Lỗi trong quá trình lấy dữ liệu: {e}")

    # Tạo nội dung chuỗi M3U
    m3u_content = build_m3u_playlist(matches_data)

    # GHI THỰC TẾ RA FILE phalang.m3u
    with open("phalang.m3u", "w", encoding="utf-8") as f:
        f.write(m3u_content)

    print("Đã tạo thành công file phalang.m3u!")


if __name__ == "__main__":
    main()
    
