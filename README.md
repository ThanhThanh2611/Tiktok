# TikTok Analyzer 🎵
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
