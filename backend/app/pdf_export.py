from __future__ import annotations

import html

from markdown import markdown
from playwright.sync_api import sync_playwright


def report_markdown_to_pdf_bytes(*, report_markdown: str, title: str) -> bytes:
    """Markdown → 自包含 HTML → Chromium 打印 PDF（适合以文字为主的报告）。"""
    raw = report_markdown or ""
    body_html = markdown(
        raw,
        extensions=["tables", "fenced_code"],
        output_format="html5",
    )
    safe_title = html.escape(title or "治愈报告")
    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <style>
    @page {{ margin: 14mm 12mm; }}
    body {{
      font-family: "Segoe UI", system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
      font-size: 11.5pt;
      line-height: 1.6;
      color: #1f1a22;
      margin: 0;
      padding: 8px 12px 24px;
    }}
    h1 {{ font-size: 18pt; color: #ad1457; margin: 0 0 12px; page-break-after: avoid; }}
    h2 {{ font-size: 13pt; color: #6a1b9a; margin: 18px 0 8px; page-break-after: avoid; border-bottom: 1px solid #f8bbd0; padding-bottom: 4px; }}
    h3 {{ font-size: 11.5pt; margin: 12px 0 6px; page-break-after: avoid; }}
    p {{ margin: 8px 0; orphans: 3; widows: 3; }}
    ul, ol {{ margin: 8px 0; padding-left: 1.3em; }}
    li {{ margin: 4px 0; }}
    table {{ border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 10pt; page-break-inside: avoid; }}
    th, td {{ border: 1px solid #e1bee7; padding: 6px 8px; vertical-align: top; }}
    th {{ background: #fce4ec; }}
    code, pre {{ font-family: ui-monospace, Consolas, monospace; font-size: 9.5pt; background: #faf5f7; }}
    pre {{ padding: 10px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; border-radius: 6px; }}
    blockquote {{ margin: 10px 0; padding: 6px 12px; border-left: 3px solid #f06292; background: #fff5f8; color: #4a3f4a; }}
    hr {{ border: none; border-top: 1px solid #f3e5f5; margin: 16px 0; }}
  </style>
</head>
<body>
  <h1>{safe_title}</h1>
  {body_html}
</body>
</html>"""

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(doc, wait_until="load", timeout=60_000)
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"},
            )
        finally:
            browser.close()
    return pdf_bytes
