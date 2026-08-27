from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


PROJECT = Path(r"D:\TextToVideo")
HTML_PATH = PROJECT / "input" / "lesson.html"
OUTPUT_DIR = PROJECT / "output"
REPORT_PATH = PROJECT / "temp" / "lesson-layout-report.json"

VIEWPORT_WIDTH = 1080
VIEWPORT_HEIGHT = 1920


def main() -> int:
    if not HTML_PATH.is_file():
        print(f"خطا: فایل HTML پیدا نشد: {HTML_PATH}")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    browser_messages: list[dict[str, str]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--hide-scrollbars",
            ],
        )

        context = browser.new_context(
            viewport={
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT,
            },
            device_scale_factor=1,
            locale="fa-IR",
        )

        page = context.new_page()

        page.on(
            "console",
            lambda message: browser_messages.append(
                {
                    "type": message.type,
                    "text": message.text,
                }
            ),
        )

        page.on(
            "pageerror",
            lambda error: browser_messages.append(
                {
                    "type": "pageerror",
                    "text": str(error),
                }
            ),
        )

        print(f"در حال باز کردن: {HTML_PATH}")

        page.goto(
            HTML_PATH.resolve().as_uri(),
            wait_until="load",
            timeout=60_000,
        )

        page.wait_for_timeout(2000)

        layout = page.evaluate(
            """
            () => {
                const scrollingElement =
                    document.scrollingElement ||
                    document.documentElement;

                const headingElements = Array.from(
                    document.querySelectorAll(
                        'h1, h2, h3, h4, [role="heading"]'
                    )
                );

                const structuralElements = Array.from(
                    document.querySelectorAll(
                        'main, article, section'
                    )
                );

                const normalize = (value) =>
                    (value || '').replace(/\\s+/g, ' ').trim();

                return {
                    title: document.title,
                    url: location.href,
                    viewportWidth: window.innerWidth,
                    viewportHeight: window.innerHeight,
                    documentWidth: Math.max(
                        document.body.scrollWidth,
                        document.documentElement.scrollWidth
                    ),
                    documentHeight: Math.max(
                        document.body.scrollHeight,
                        document.documentElement.scrollHeight
                    ),
                    maxScroll: Math.max(
                        0,
                        scrollingElement.scrollHeight -
                        window.innerHeight
                    ),
                    direction: getComputedStyle(
                        document.documentElement
                    ).direction,
                    headingCount: headingElements.length,
                    headings: headingElements.map(
                        (element, index) => {
                            const rect =
                                element.getBoundingClientRect();

                            return {
                                index: index + 1,
                                tag: element.tagName.toLowerCase(),
                                id: element.id || null,
                                text: normalize(
                                    element.innerText ||
                                    element.textContent
                                ),
                                top: Math.round(
                                    rect.top + window.scrollY
                                ),
                                height: Math.round(rect.height),
                            };
                        }
                    ),
                    structuralCount: structuralElements.length,
                    structures: structuralElements.map(
                        (element, index) => {
                            const rect =
                                element.getBoundingClientRect();

                            return {
                                index: index + 1,
                                tag: element.tagName.toLowerCase(),
                                id: element.id || null,
                                className:
                                    typeof element.className ===
                                    'string'
                                        ? element.className
                                        : '',
                                top: Math.round(
                                    rect.top + window.scrollY
                                ),
                                height: Math.round(rect.height),
                            };
                        }
                    ),
                };
            }
            """
        )

        max_scroll = int(layout["maxScroll"])

        screenshots = [
            ("lesson-top.png", 0),
            ("lesson-middle.png", round(max_scroll * 0.5)),
            ("lesson-bottom.png", max_scroll),
        ]

        for filename, scroll_position in screenshots:
            page.evaluate(
                "(position) => window.scrollTo(0, position)",
                scroll_position,
            )
            page.wait_for_timeout(500)

            screenshot_path = OUTPUT_DIR / filename

            page.screenshot(
                path=str(screenshot_path),
                full_page=False,
            )

            print(f"تصویر ایجاد شد: {screenshot_path}")

        layout["browserMessages"] = browser_messages

        REPORT_PATH.write_text(
            json.dumps(
                layout,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8-sig",
        )

        context.close()
        browser.close()

    print()
    print("=" * 65)
    print("گزارش ساختار HTML")
    print("=" * 65)
    print(f"عنوان صفحه: {layout['title']}")
    print(
        "اندازه نمای ویدئو: "
        f"{layout['viewportWidth']}x"
        f"{layout['viewportHeight']}"
    )
    print(
        "اندازه سند: "
        f"{layout['documentWidth']}x"
        f"{layout['documentHeight']}"
    )
    print(f"حداکثر حرکت عمودی: {layout['maxScroll']}")
    print(f"جهت صفحه: {layout['direction']}")
    print(f"تعداد عنوان‌ها: {layout['headingCount']}")
    print(
        "تعداد عناصر main/article/section: "
        f"{layout['structuralCount']}"
    )
    print()

    for heading in layout["headings"]:
        text = heading["text"]

        if len(text) > 100:
            text = text[:97] + "..."

        print(
            f"{heading['index']:02}. "
            f"{heading['tag']} | "
            f"top={heading['top']} | "
            f"{text}"
        )

    print()
    print(f"گزارش JSON: {REPORT_PATH}")
    print("=" * 65)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())