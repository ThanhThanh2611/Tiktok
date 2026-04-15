#!/usr/bin/env python3
"""
TikTok Video Analyzer
- Phân tích nội dung video TikTok bằng Gemini API
- Crawl toàn bộ comment của video
- Lưu kết quả vào file JSON

Cách chạy:
  python3 tiktok_analyzer.py <URL>
  python3 tiktok_analyzer.py <URL> --max-comments 1000
  python3 tiktok_analyzer.py <URL> --cookies-from-browser chrome
  python3 tiktok_analyzer.py <URL> --cookies cookies.txt
  python3 tiktok_analyzer.py <URL> --skip-video
  python3 tiktok_analyzer.py <URL> --model gemini-1.5-flash
  python3 tiktok_analyzer.py <URL> --proxy http://127.0.0.1:7890
"""

import os
import sys
import re
import json
import time
import random
import string
import socket
import tempfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import yt_dlp
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from google import genai
from google.genai import types

# ============================================================
# CẤU HÌNH
# ============================================================
GEMINI_API_KEY = "AIzaSyCHghKTWwHxSWzUkwRQD-stIpZOPTXHXow"

# Thử lần lượt các model nếu bị rate-limit
GEMINI_MODELS_FALLBACK = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro",
]

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

ANALYSIS_PROMPT = (
    "Phân tích video này về cái gì, context, bối cảnh, nhân vật. "
    "Hãy trả lời chi tiết theo các mục sau:\n"
    "1. Nội dung chính (video nói về điều gì)\n"
    "2. Nhân vật (mô tả người xuất hiện trong video, tạo hình, hành động)\n"
    "3. Bối cảnh (không gian, phong cách nghệ thuật, âm nhạc nếu có)\n"
    "4. Thông điệp và ý nghĩa\n"
    "Trả lời bằng tiếng Việt, chi tiết và đầy đủ."
)

TIKTOK_COMMENT_API = "https://www.tiktok.com/api/comment/list/"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.tiktok.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
}

# Lỗi mạng cần retry
NETWORK_ERRORS = (
    ConnectionError,
    TimeoutError,
    socket.timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ReadTimeout,
    requests.exceptions.ConnectTimeout,
)


# ============================================================
# KIỂM TRA KẾT NỐI
# ============================================================
def check_google_connectivity(proxy: str = None) -> bool:
    """Kiểm tra xem máy có kết nối được tới Google API không."""
    proxies = {"http": proxy, "https": proxy} if proxy else None
    try:
        r = requests.get(
            "https://generativelanguage.googleapis.com/",
            timeout=10,
            proxies=proxies,
        )
        return True
    except Exception:
        return False


def print_network_error_help(proxy: str = None):
    print("""
  ┌─────────────────────────────────────────────────────────┐
  │  LỖI KẾT NỐI MẠNG (WinError 10060 / Timeout)           │
  │                                                         │
  │  Nguyên nhân phổ biến:                                  │
  │  1. Firewall / Antivirus chặn kết nối Google           │
  │  2. Cần VPN hoặc proxy để vào Google API               │
  │  3. Mạng không ổn định                                  │
  │                                                         │
  │  Cách khắc phục:                                        │
  │  A) Bật VPN rồi chạy lại                                │
  │  B) Dùng proxy:                                         │
  │     --proxy http://127.0.0.1:7890   (Clash)             │
  │     --proxy http://127.0.0.1:10809  (V2Ray)             │
  │     --proxy http://127.0.0.1:1080   (Shadowsocks)       │
  │  C) Tắt tạm firewall / antivirus rồi thử lại           │
  └─────────────────────────────────────────────────────────┘
""")


# ============================================================
# TIỆN ÍCH
# ============================================================
def extract_video_id(url: str) -> str:
    for pat in [r"/video/(\d+)", r"v=(\d+)"]:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return hashlib.md5(url.encode()).hexdigest()[:12]


def output_path(video_id: str) -> Path:
    return OUTPUT_DIR / f"{video_id}.json"


def load_existing(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_result(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  ✅ Đã lưu: {path}")


def random_ms_token(length: int = 107) -> str:
    chars = string.ascii_letters + string.digits + "-_"
    return "".join(random.choices(chars, k=length))


def parse_cookies_txt(cookies_file: str) -> dict:
    cookies = {}
    try:
        with open(cookies_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    cookies[parts[5]] = parts[6]
    except Exception as e:
        print(f"  ⚠️  Không đọc được file cookie: {e}")
    return cookies


def make_requests_session(proxy: str = None) -> requests.Session:
    """Tạo requests.Session với retry tự động và proxy (nếu có)."""
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)

    # Retry tự động cho lỗi mạng
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
        print(f"  🔀 Dùng proxy: {proxy}")

    return session


# ============================================================
# BƯỚC 1: TẢI VIDEO VÀ LẤY METADATA
# ============================================================
def download_video(url: str, tmp_dir: str,
                   cookies_browser: str = None,
                   cookies_file: str = None,
                   proxy: str = None) -> tuple:
    ydl_opts = {
        "outtmpl": os.path.join(tmp_dir, "video.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "format": "mp4/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "socket_timeout": 60,
        "retries": 5,
    }
    if cookies_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_browser,)
    if cookies_file and os.path.exists(cookies_file):
        ydl_opts["cookiefile"] = cookies_file
    if proxy:
        ydl_opts["proxy"] = proxy

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        meta = {
            "title": info.get("title", ""),
            "description": info.get("description", ""),
            "uploader": info.get("uploader", ""),
            "uploader_id": info.get("uploader_id", ""),
            "like_count": info.get("like_count"),
            "comment_count": info.get("comment_count"),
            "view_count": info.get("view_count"),
            "share_count": info.get("repost_count"),
            "upload_date": info.get("upload_date", ""),
            "duration": info.get("duration"),
            "webpage_url": info.get("webpage_url", url),
            "video_id": info.get("id", ""),
        }

    for f in Path(tmp_dir).iterdir():
        if f.suffix in (".mp4", ".webm", ".mov"):
            return str(f), meta

    raise FileNotFoundError("Không tìm thấy file video sau khi tải.")


# ============================================================
# BƯỚC 2: PHÂN TÍCH VIDEO BẰNG GEMINI
# ============================================================
def _is_network_error(err: str) -> bool:
    keywords = [
        "10060", "10061", "WinError", "timed out", "timeout",
        "connection refused", "network", "unreachable", "ConnectTimeout",
        "ConnectionError", "RemoteDisconnected",
    ]
    return any(k.lower() in err.lower() for k in keywords)


def _is_quota_error(err: str) -> bool:
    return "429" in err or "RESOURCE_EXHAUSTED" in err


def _wait_from_error(err: str, default: int) -> int:
    m = re.search(r"retry.*?(\d+)s", err, re.IGNORECASE)
    return int(m.group(1)) + 5 if m else default


def _generate_with_retry(client, model: str, contents,
                         max_retries: int = 4, proxy: str = None) -> str:
    """Gọi Gemini với retry cho cả lỗi 429 và lỗi mạng."""
    delay = 30
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
            )
            return response.text

        except Exception as e:
            err = str(e)

            if _is_quota_error(err):
                wait = _wait_from_error(err, delay)
                if attempt < max_retries - 1:
                    print(f"\n  ⏳ Rate limit ({model}) — chờ {wait}s...", flush=True)
                    time.sleep(wait)
                    delay = min(delay * 2, 120)
                else:
                    raise

            elif _is_network_error(err):
                wait = delay
                if attempt < max_retries - 1:
                    print(f"\n  ⚠️  Lỗi mạng — chờ {wait}s rồi thử lại "
                          f"({attempt + 2}/{max_retries})...", flush=True)
                    time.sleep(wait)
                    delay = min(delay * 2, 90)
                else:
                    print_network_error_help(proxy)
                    raise

            else:
                raise

    raise RuntimeError("Hết số lần retry.")


def analyze_video_with_gemini(video_path: str,
                               preferred_model: str = None,
                               proxy: str = None) -> str:
    """
    Upload video lên Gemini và phân tích.
    Tự động thử model dự phòng khi bị rate-limit.
    Hỗ trợ proxy cho môi trường bị tường lửa.
    """
    # Đặt proxy cho thư viện google-genai (dùng httpx bên dưới)
    if proxy:
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["HTTP_PROXY"] = proxy
        os.environ["http_proxy"] = proxy
        os.environ["https_proxy"] = proxy

    print("  📤 Đang upload video lên Gemini API...")
    client = genai.Client(api_key=GEMINI_API_KEY)

    # Upload với retry mạng
    upload_retries = 4
    video_file = None
    for attempt in range(upload_retries):
        try:
            video_file = client.files.upload(
                file=video_path,
                config=types.UploadFileConfig(
                    display_name="tiktok_video",
                    mime_type="video/mp4",
                ),
            )
            break
        except Exception as e:
            err = str(e)
            if _is_network_error(err) and attempt < upload_retries - 1:
                wait = 15 * (attempt + 1)
                print(f"\n  ⚠️  Lỗi upload — chờ {wait}s rồi thử lại "
                      f"({attempt + 2}/{upload_retries})...", flush=True)
                time.sleep(wait)
            else:
                if _is_network_error(err):
                    print_network_error_help(proxy)
                raise

    print("  ⏳ Đang chờ Gemini xử lý video...", end="", flush=True)
    while video_file.state.name == "PROCESSING":
        time.sleep(3)
        video_file = client.files.get(name=video_file.name)
        print(".", end="", flush=True)
    print()

    if video_file.state.name == "FAILED":
        raise RuntimeError("Gemini không thể xử lý video này.")

    contents = [
        types.Part.from_uri(file_uri=video_file.uri, mime_type="video/mp4"),
        ANALYSIS_PROMPT,
    ]

    if preferred_model:
        models_to_try = [preferred_model] + [
            m for m in GEMINI_MODELS_FALLBACK if m != preferred_model
        ]
    else:
        models_to_try = GEMINI_MODELS_FALLBACK

    last_error = None
    for model in models_to_try:
        print(f"  🤖 Model: {model} ...")
        try:
            result = _generate_with_retry(client, model, contents, proxy=proxy)
            try:
                client.files.delete(name=video_file.name)
            except Exception:
                pass
            return result

        except Exception as e:
            err = str(e)
            last_error = err
            if _is_quota_error(err):
                print(f"  ❌ {model} hết quota — thử model tiếp theo...")
                continue
            elif _is_network_error(err):
                # Lỗi mạng không ổn định, dừng thay vì thử model khác
                try:
                    client.files.delete(name=video_file.name)
                except Exception:
                    pass
                raise
            else:
                try:
                    client.files.delete(name=video_file.name)
                except Exception:
                    pass
                raise

    try:
        client.files.delete(name=video_file.name)
    except Exception:
        pass

    raise RuntimeError(
        f"Tất cả model đều bị rate-limit.\n"
        f"Lỗi cuối: {last_error}\n\n"
        f"Giải pháp:\n"
        f"  1. Chờ vài phút rồi chạy lại\n"
        f"  2. Dùng API key khác: https://aistudio.google.com/apikey\n"
        f"  3. Nâng cấp plan: https://ai.google.dev/pricing"
    )


# ============================================================
# BƯỚC 3: CRAWL COMMENT
# ============================================================
def crawl_comments_via_api(video_id: str, max_comments: int = 500,
                           extra_cookies: dict = None,
                           proxy: str = None) -> list:
    session = make_requests_session(proxy)
    base_cookies = {
        "msToken": random_ms_token(),
        "tt_chain_token": random_ms_token(24),
    }
    if extra_cookies:
        base_cookies.update(extra_cookies)
    for k, v in base_cookies.items():
        session.cookies.set(k, v, domain=".tiktok.com")

    comments = []
    cursor = 0
    count = 20
    page = 0
    consecutive_errors = 0

    print(f"  Crawl comment cho video {video_id}...")

    while len(comments) < max_comments:
        params = {
            "aid": "1988",
            "app_name": "tiktok_web",
            "aweme_id": video_id,
            "cursor": cursor,
            "count": count,
            "enter_from": "tiktok_web",
            "msToken": random_ms_token(),
        }

        try:
            resp = session.get(TIKTOK_COMMENT_API, params=params, timeout=20)
            data = resp.json()
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            print(f"\n    ⚠️  Lỗi trang {page+1}: {e}")
            if consecutive_errors >= 3:
                break
            time.sleep(3)
            continue

        status = data.get("status_code")
        if status not in (0, None):
            print(f"\n    ⚠️  API lỗi: {status} — {data.get('status_msg', '')}")
            break

        raw_comments = data.get("comments") or []
        if not raw_comments:
            break

        for c in raw_comments:
            user = c.get("user", {})
            ts = c.get("create_time", 0)
            comments.append({
                "comment_id": c.get("cid", ""),
                "text": c.get("text", ""),
                "author": user.get("nickname", ""),
                "author_id": user.get("uid", ""),
                "like_count": c.get("digg_count", 0),
                "reply_count": c.get("reply_comment_total", 0),
                "create_time": ts,
                "create_time_str": (
                    datetime.fromtimestamp(ts, tz=timezone.utc)
                    .strftime("%Y-%m-%d %H:%M:%S UTC") if ts else ""
                ),
            })

        has_more = data.get("has_more", 0)
        cursor = data.get("cursor", cursor + count)
        page += 1
        print(f"    Trang {page}: {len(comments)} comment...", end="\r")

        if not has_more:
            break
        time.sleep(random.uniform(0.8, 1.5))

    print(f"\n    Tổng: {len(comments)} comment")
    return comments


def crawl_comments_yt_dlp(url: str,
                           cookies_browser: str = None,
                           cookies_file: str = None,
                           proxy: str = None) -> list:
    print("  Thử crawl comment qua yt-dlp...")
    ydl_opts = {
        "getcomments": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 60,
        "retries": 5,
        "extractor_args": {"tiktok": {"comment_count": "999999"}},
    }
    if cookies_browser:
        ydl_opts["cookiesfrombrowser"] = (cookies_browser,)
    if cookies_file and os.path.exists(cookies_file):
        ydl_opts["cookiefile"] = cookies_file
    if proxy:
        ydl_opts["proxy"] = proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            raw = info.get("comments") or []

        comments = []
        for c in raw:
            ts = c.get("timestamp", 0)
            comments.append({
                "comment_id": str(c.get("id", "")),
                "text": c.get("text", ""),
                "author": c.get("author", ""),
                "author_id": str(c.get("author_id", "")),
                "like_count": c.get("like_count", 0),
                "reply_count": 0,
                "create_time": ts,
                "create_time_str": (
                    datetime.fromtimestamp(ts, tz=timezone.utc)
                    .strftime("%Y-%m-%d %H:%M:%S UTC") if ts else ""
                ),
            })
        print(f"    yt-dlp: {len(comments)} comment")
        return comments
    except Exception as e:
        print(f"    yt-dlp thất bại: {e}")
        return []


# ============================================================
# HÀM CHÍNH
# ============================================================
def analyze(url: str,
            max_comments: int = 500,
            skip_video_analysis: bool = False,
            cookies_browser: str = None,
            cookies_file: str = None,
            preferred_model: str = None,
            proxy: str = None):

    print(f"\n{'='*60}")
    print(f"  TikTok Analyzer — Gemini AI")
    print(f"{'='*60}")
    print(f"  URL   : {url}")

    video_id = extract_video_id(url)
    out_path = output_path(video_id)
    print(f"  ID    : {video_id}")
    print(f"  Output: {out_path}")
    if proxy:
        print(f"  Proxy : {proxy}")

    # Kiểm tra kết nối ngay từ đầu
    if not skip_video_analysis:
        print("\n  Kiểm tra kết nối tới Google API...", end="", flush=True)
        ok = check_google_connectivity(proxy)
        print(" OK ✓" if ok else " THẤT BẠI ✗")
        if not ok:
            print_network_error_help(proxy)
            if not proxy:
                print("  Tiếp tục thử (có thể thất bại)...\n")

    result = load_existing(out_path)
    if not result:
        result = {
            "url": url,
            "video_id": video_id,
            "crawled_at": datetime.now(tz=timezone.utc).isoformat(),
            "metadata": {},
            "analysis": "",
            "comments": [],
            "comments_count": 0,
        }

    # ---- Tải + phân tích video ----
    if not skip_video_analysis and not result.get("analysis"):
        print(f"\n{'─'*60}")
        print("  [1/2] Tải video + phân tích Gemini")
        print(f"{'─'*60}")
        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                print("  📥 Đang tải video...")
                video_path, meta = download_video(
                    url, tmp_dir,
                    cookies_browser=cookies_browser,
                    cookies_file=cookies_file,
                    proxy=proxy,
                )
                result["metadata"] = meta
                if meta.get("video_id"):
                    video_id = meta["video_id"]
                    result["video_id"] = video_id
                    out_path = output_path(video_id)

                print(f"  ✅ Tải xong: {Path(video_path).name}")
                print(f"  👤 Tác giả   : {meta.get('uploader', 'N/A')}")
                print(f"  📊 Lượt xem  : {meta.get('view_count', 'N/A')}")
                print(f"  ❤️  Lượt thích: {meta.get('like_count', 'N/A')}")

                print("\n  🔍 Đang phân tích bằng Gemini...")
                analysis = analyze_video_with_gemini(
                    video_path, preferred_model, proxy
                )
                result["analysis"] = analysis

                print("\n" + "─"*60)
                print("  KẾT QUẢ PHÂN TÍCH:")
                print("─"*60)
                print(analysis)
                print("─"*60)

            except Exception as e:
                err_msg = str(e)
                print(f"\n  ❌ Lỗi: {err_msg}")
                if "blocked" in err_msg.lower() or "ip" in err_msg.lower():
                    print("\n  💡 TikTok chặn IP — thêm --cookies-from-browser chrome")
                result["analysis_error"] = err_msg
    elif skip_video_analysis:
        print("\n  [1/2] ⏭️  Bỏ qua phân tích video (--skip-video)")
    else:
        print("\n  [1/2] ⏭️  Đã có phân tích, bỏ qua")

    # ---- Crawl comment ----
    if not result.get("comments"):
        print(f"\n{'─'*60}")
        print(f"  [2/2] Crawl comment (tối đa {max_comments})")
        print(f"{'─'*60}")

        extra_cookies = {}
        if cookies_file and os.path.exists(cookies_file):
            extra_cookies = parse_cookies_txt(cookies_file)

        comments = crawl_comments_via_api(
            video_id, max_comments, extra_cookies, proxy
        )
        if not comments:
            comments = crawl_comments_yt_dlp(
                url,
                cookies_browser=cookies_browser,
                cookies_file=cookies_file,
                proxy=proxy,
            )
        result["comments"] = comments
        result["comments_count"] = len(comments)
    else:
        print(f"\n  [2/2] ⏭️  Đã có {len(result['comments'])} comment, bỏ qua")

    result["crawled_at"] = datetime.now(tz=timezone.utc).isoformat()
    save_result(out_path, result)

    print(f"\n{'='*60}")
    print("  ✅  HOÀN THÀNH!")
    print(f"  Phân tích video : {'Có ✓' if result.get('analysis') else 'Không có ✗'}")
    print(f"  Số comment      : {result.get('comments_count', 0)}")
    print(f"  File kết quả    : {out_path}")
    print(f"{'='*60}\n")

    return result


# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        print("Ví dụ:")
        print("  python3 tiktok_analyzer.py https://www.tiktok.com/@user/video/123")
        print("  python3 tiktok_analyzer.py https://vm.tiktok.com/ABC/ --cookies-from-browser chrome")
        print("  python3 tiktok_analyzer.py <URL> --proxy http://127.0.0.1:7890")
        sys.exit(1)

    url_arg            = sys.argv[1]
    max_comments_arg   = 500
    skip_video_arg     = False
    cookies_browser_arg = None
    cookies_file_arg   = None
    preferred_model_arg = None
    proxy_arg          = None

    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--max-comments" and i + 1 < len(sys.argv):
            max_comments_arg = int(sys.argv[i + 1]); i += 2
        elif arg == "--skip-video":
            skip_video_arg = True; i += 1
        elif arg == "--cookies-from-browser" and i + 1 < len(sys.argv):
            cookies_browser_arg = sys.argv[i + 1]; i += 2
        elif arg == "--cookies" and i + 1 < len(sys.argv):
            cookies_file_arg = sys.argv[i + 1]; i += 2
        elif arg == "--model" and i + 1 < len(sys.argv):
            preferred_model_arg = sys.argv[i + 1]; i += 2
        elif arg == "--proxy" and i + 1 < len(sys.argv):
            proxy_arg = sys.argv[i + 1]; i += 2
        else:
            i += 1

    analyze(
        url_arg,
        max_comments=max_comments_arg,
        skip_video_analysis=skip_video_arg,
        cookies_browser=cookies_browser_arg,
        cookies_file=cookies_file_arg,
        preferred_model=preferred_model_arg,
        proxy=proxy_arg,
    )
