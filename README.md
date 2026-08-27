# TextToVideo

برنامه گرافیکی تبدیل متن فارسی و HTML به صوت، زیرنویس و ویدئو.

## امکانات

- رابط گرافیکی با PySide6
- تولید صوت فارسی
- تولید و ویرایش زیرنویس SRT
- پیش‌نمایش و رندر نهایی با FFmpeg
- پشتیبانی از تصویر و قالب HTML
- اولویت خودکار فایل زیرنویس ویرایش‌شده
- ویرایشگر زیرنویس فارسی

## اجرای برنامه

```powershell
python -m app.main
```

## پیش‌نیازها

- Python 3.11 یا جدیدتر
- FFmpeg و ffprobe
- PySide6
- edge-tts
- Pillow
- BeautifulSoup4
- lxml
- pysubs2
- Playwright
