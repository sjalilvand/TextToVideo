from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(
        viewport={
            "width": 1080,
            "height": 1920
        }
    )
    page.set_content("""
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <style>
            body {
                background: #101828;
                color: white;
                font-family: Tahoma, sans-serif;
                padding: 100px;
                text-align: center;
            }

            h1 {
                margin-top: 500px;
                font-size: 80px;
            }

            p {
                font-size: 42px;
                line-height: 2;
            }
        </style>
    </head>
    <body>
        <h1>تبدیل HTML به ویدئو</h1>
        <p>آزمایش ساخت تصویر عمودی برای اینستاگرام</p>
    </body>
    </html>
    """)

    page.screenshot(
        path=r"D:\TextToVideo\output\playwright-test.png",
        full_page=False
    )

    browser.close()

print("SCREENSHOT_OK")
