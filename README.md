# TikTok Analyzer 🎵

Công cụ phân tích video TikTok bằng Gemini AI và crawl toàn bộ comment, lưu kết quả ra file JSON.

---

## Cài đặt

### 1. Yêu cầu
- Python 3.9 trở lên
- Pip

### 2. Cài thư viện
```bash
pip install -r requirements.txt
```

---

## Cách dùng

```bash
python tiktok_analyzer.py <URL_VIDEO_TIKTOK>
```

**Ví dụ:**
```bash
python tiktok_analyzer.py https://www.tiktok.com/@user/video/7123456789012345678
```
---

## Tùy chọn

| Tham số | Mô tả | Ví dụ |
|---|---|---|
| `--max-comments <số>` | Giới hạn số comment crawl (mặc định: 500) | `--max-comments 2000` |
| `--skip-video` | Bỏ qua phân tích video, chỉ crawl comment | `--skip-video` |
| `--model <tên>` | Chọn model Gemini cụ thể | `--model gemini-1.5-flash` |
| `--cookies-from-browser <trình_duyệt>` | Lấy cookie từ trình duyệt để bypass kiểm tra | `--cookies-from-browser chrome` |
| `--cookies <file>` | Dùng file cookies.txt | `--cookies cookies.txt` |
| `--proxy <địa_chỉ>` | Dùng proxy / VPN local | `--proxy http://127.0.0.1:7890` |

---

## Ví dụ nâng cao

```bash
# Dùng cookie Chrome để tải video không bị chặn
python tiktok_analyzer.py <URL> --cookies-from-browser chrome

# Crawl tối đa 2000 comment
python tiktok_analyzer.py <URL> --max-comments 2000

# Dùng proxy Clash/V2Ray
python tiktok_analyzer.py <URL> --proxy http://127.0.0.1:7890

# Chỉ crawl comment, không phân tích video
python tiktok_analyzer.py <URL> --skip-video

# Dùng model cụ thể
python tiktok_analyzer.py <URL> --model gemini-1.5-flash

# Kết hợp nhiều tùy chọn
python tiktok_analyzer.py <URL> --cookies-from-browser chrome --max-comments 1000 --proxy http://127.0.0.1:7890
```

---

## Kết quả

Kết quả được lưu tự động vào thư mục `output/<video_id>.json` với cấu trúc:

```json
{
  "url": "https://www.tiktok.com/...",
  "video_id": "7123456789012345678",
  "crawled_at": "2025-04-15T10:00:00+00:00",
  "metadata": {
    "title": "...",
    "uploader": "...",
    "view_count": 100000,
    "like_count": 5000,
    "comment_count": 300
  },
  "analysis": "1. Nội dung chính: ...\n2. Nhân vật: ...\n3. Bối cảnh: ...\n4. Thông điệp: ...",
  "comments": [
    {
      "comment_id": "...",
      "text": "Nội dung comment",
      "author": "Tên người dùng",
      "like_count": 10,
      "reply_count": 2,
      "create_time_str": "2025-04-15 08:00:00 UTC"
    }
  ],
  "comments_count": 300
}
```

> **Lưu ý:** Chạy lại cùng URL sẽ bỏ qua bước đã có sẵn (không tốn thêm quota).
---

## Xử lý lỗi thường gặp

### ❌ WinError 10060 — Không kết nối được Google API
TikTok/Google bị chặn bởi firewall hoặc mạng nội địa.

**Cách sửa:**
- Bật VPN rồi chạy lại
- Hoặc dùng proxy local:
  ```bash
  --proxy http://127.0.0.1:7890   # Clash
  --proxy http://127.0.0.1:10809  # V2Ray
  --proxy http://127.0.0.1:1080   # Shadowsocks
  ```

### ❌ 429 RESOURCE_EXHAUSTED — Hết quota Gemini
API key free tier đã hết lượt. Script tự động thử model khác.

**Cách sửa:**
- Chờ vài phút rồi chạy lại
- Dùng API key khác: https://aistudio.google.com/apikey
- Chỉ định model còn quota: `--model gemini-1.5-flash-8b`

### ❌ IP bị TikTok chặn (khi tải video)
**Cách sửa:**
```bash
# Dùng cookie từ trình duyệt đang đăng nhập TikTok
python tiktok_analyzer.py <URL> --cookies-from-browser chrome
# hoặc firefox, edge, brave...
```

Hoặc cài extension **"Get cookies.txt LOCALLY"** trên Chrome, xuất file `cookies.txt` rồi:
```bash
python tiktok_analyzer.py <URL> --cookies cookies.txt
```

---

## Các model Gemini hỗ trợ

| Model | Tốc độ | Chất lượng |
|---|---|---|
| `gemini-2.0-flash` | Nhanh | Tốt (mặc định) |
| `gemini-2.0-flash-lite` | Rất nhanh | Khá |
| `gemini-1.5-flash` | Nhanh | Tốt |
| `gemini-1.5-flash-8b` | Rất nhanh | Khá |
| `gemini-1.5-pro` | Chậm | Rất tốt |
