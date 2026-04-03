from __future__ import annotations

import html
import json
import re

from markdown import markdown
from playwright.sync_api import sync_playwright


_LENS_RE = re.compile(r"【([^】]*?·\s*L[1-6])】")


def _get_block_after_heading(md: str, heading: str) -> str:
    marker = f"## {heading}"
    start = md.find(marker)
    if start == -1:
        return ""
    start = start + len(marker)
    nxt = md.find("\n## ", start)
    if nxt == -1:
        return md[start:]
    return md[start:nxt]


def _extract_evidence_quotes(text: str) -> list[str]:
    if not text:
        return []
    patterns: list[str] = [
        r"（证据[^）]*?「([^」]+)」）",
        r"（证据[^）]*?『([^』]+)』）",
        r"（证据[^）]*?\s*\"([^\"]+)\"）",
        r"（证据[^）]*?\s*“([^”]+)”）",
        r"（证据[^）]*?([^）]+)）",
    ]
    out: list[str] = []
    for p in patterns:
        for m in re.finditer(p, text):
            groups = m.groups()
            q = (groups[0] if groups else "") or ""
            q = q.strip()
            if q and len(q) <= 180:
                out.append(q)
    # de-dup while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for q in out:
        if q in seen:
            continue
        seen.add(q)
        uniq.append(q)
    return uniq


def _parse_behavior_radar(md: str) -> tuple[list[str], list[int]]:
    block = _get_block_after_heading(md, "行为层量表")
    if not block:
        return (["样本不足"], [1])

    rows: list[tuple[str, int | None]] = []
    for line in block.splitlines():
        t = line.strip()
        if not t.startswith("|"):
            continue
        if "---" in t:
            continue

        parts = [x.strip() for x in t.split("|") if x.strip()]
        if len(parts) < 2:
            continue
        dimension = parts[0]
        score_raw = parts[1]
        if not dimension:
            continue
        if score_raw.strip().lower() == "nc":
            score = None
        else:
            try:
                n = float(score_raw)
                score = int(round(n)) if n == int(round(n)) else n  # type: ignore[assignment]
            except Exception:
                score = None

        if score is None:
            rows.append((dimension, None))
        else:
            rows.append((dimension, int(score)))  # type: ignore[arg-type]

    dims: list[str] = []
    values: list[int] = []
    for dimension, score in rows:
        if score is None:
            continue
        dims.append(re.sub(r"\s+", " ", dimension).strip())
        values.append(int(score))
        if len(dims) >= 6:
            break

    if not dims:
        return (["样本不足"], [1])
    # clamp 0..5 to keep radar stable
    values = [max(0, min(5, int(v))) for v in values]
    return (dims, values)


def _parse_lens_radar(md: str) -> tuple[list[str], list[int]]:
    matches = list(_LENS_RE.finditer(md))
    if not matches:
        return (["L1", "L2", "L3", "L4", "L5", "L6"], [1, 1, 1, 1, 1, 1])

    sections: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        lens_tag = (m.group(1) or "").strip()
        lens_id_match = re.search(r"L([1-6])", lens_tag)
        if not lens_id_match:
            continue
        lens_id = f"L{lens_id_match.group(1)}"

        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        slice_text = md[start:end].strip()
        content = re.sub(r"^【[^】]*?】", "", slice_text).strip()
        sections.append((lens_id, content))

    lens_order = ["L1", "L2", "L3", "L4", "L5", "L6"]
    counts: dict[str, int] = {k: 0 for k in lens_order}
    for lens_id, content in sections:
        q = len(_extract_evidence_quotes(content))
        counts[lens_id] += q

    values = [min(5, int(counts[lid])) for lid in lens_order]
    return (lens_order, values)


def report_markdown_to_pdf_bytes(*, report_markdown: str, title: str) -> bytes:
    """Markdown → 自包含 HTML → Chromium 打印 PDF（适合以文字为主的报告）。"""
    raw = report_markdown or ""

    behavior_indicators, behavior_values = _parse_behavior_radar(raw)
    lens_order, lens_values = _parse_lens_radar(raw)

    body_html = markdown(
        raw,
        extensions=["tables", "fenced_code"],
        output_format="html5",
    )
    safe_title = html.escape(title or "恋爱报告")

    charts_payload = {
        "behavior": {"indicators": behavior_indicators, "values": behavior_values},
        "lens": {"order": lens_order, "values": lens_values},
    }

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{safe_title}</title>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
  <style>
    @page {{ margin: 12mm 10mm; }}
    body {{
      font-family: "Nunito Sans", "Segoe UI", system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
      font-size: 11pt;
      line-height: 1.65;
      color: #1f1a22;
      margin: 0;
      padding: 10px 0 18px;
      background: #fff;
    }}

    .page {{
      padding: 0 10mm;
    }}

    h1 {{
      font-size: 20pt;
      color: #ad1457;
      margin: 0 0 14px;
      page-break-after: avoid;
    }}

    h2 {{
      font-size: 13.5pt;
      color: #6a1b9a;
      margin: 18px 0 8px;
      page-break-after: avoid;
      border-bottom: 1px solid #f8bbd0;
      padding-bottom: 6px;
    }}

    h3 {{
      font-size: 12pt;
      margin: 12px 0 6px;
      page-break-after: avoid;
    }}

    p {{ margin: 8px 0; orphans: 3; widows: 3; }}
    ul, ol {{ margin: 8px 0; padding-left: 1.3em; }}
    li {{ margin: 4px 0; }}

    .pdf-card {{
      border: 1px solid rgba(240, 98, 146, 0.18);
      border-radius: 14px;
      padding: 12px 12px 10px;
      background: #fff;
      box-shadow: 0 18px 40px rgba(240, 98, 146, 0.06);
      page-break-inside: auto;
    }}

    .pdf-charts {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin: 10px 0 14px;
    }}

    .pdf-chart-card {{
      border-radius: 14px;
      padding: 10px 10px 8px;
      border: 1px solid rgba(31, 26, 34, 0.10);
      background: #fff;
      page-break-inside: avoid;
    }}

    .pdf-chart-title {{
      font-size: 12pt;
      font-weight: 900;
      color: rgba(31, 26, 34, 0.88);
      margin: 0 0 8px;
    }}

    .pdf-chart {{
      width: 100%;
      height: 280px;
    }}

    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 10px 0;
      font-size: 10.3pt;
      page-break-inside: avoid;
    }}
    th, td {{
      border: 1px solid #e1bee7;
      padding: 6px 8px;
      vertical-align: top;
    }}
    th {{ background: #fce4ec; }}
    code, pre {{ font-family: ui-monospace, Consolas, monospace; font-size: 9.5pt; background: #faf5f7; }}
    pre {{
      padding: 10px;
      overflow-x: auto;
      white-space: pre-wrap;
      word-break: break-word;
      border-radius: 6px;
    }}
    blockquote {{
      margin: 10px 0;
      padding: 6px 12px;
      border-left: 3px solid #f06292;
      background: #fff5f8;
      color: #4a3f4a;
      border-radius: 10px;
    }}
    hr {{ border: none; border-top: 1px solid #f3e5f5; margin: 16px 0; }}
  </style>
</head>
<body>
  <div class="page">
    <h1>{safe_title}</h1>

    <div class="pdf-charts">
      <div class="pdf-chart-card">
        <div class="pdf-chart-title">行为维度雷达</div>
        <div id="behaviorRadar" class="pdf-chart"></div>
      </div>
      <div class="pdf-chart-card">
        <div class="pdf-chart-title">透镜证据密度雷达</div>
        <div id="lensRadar" class="pdf-chart"></div>
      </div>
    </div>

    <div class="pdf-card">
      {body_html}
    </div>
  </div>

  <script>
    const payload = {json.dumps(charts_payload, ensure_ascii=False)};
    const wrapAxisLabel = (s, chunk) => {{
      const t = String(s || '').replace(/\\s+/g, ' ').trim();
      if (t.length <= chunk) return t;
      const lines = [];
      for (let i = 0; i < t.length; i += chunk) {{
        lines.push(t.slice(i, i + chunk));
      }}
      return lines.join('\\n');
    }};

    const behavior = payload.behavior;
    const lens = payload.lens;

    function renderRadar(el, option) {{
      const chart = echarts.init(el, null, {{ renderer: 'canvas' }});
      chart.setOption(option, true);
      chart.resize();
      return chart;
    }}

    const behaviorChart = renderRadar(
      document.getElementById('behaviorRadar'),
      {{
        backgroundColor: 'transparent',
        tooltip: {{
          trigger: 'item',
          confine: true,
        }},
        radar: {{
          center: ['50%', '53%'],
          indicator: behavior.indicators.map(n => ({{ name: n, max: 5 }})),
          radius: '34%',
          splitNumber: 5,
          axisName: {{
            color: 'rgba(36,24,42,0.82)',
            fontFamily: 'Nunito Sans, system-ui',
            fontWeight: 800,
            fontSize: 10,
            lineHeight: 14,
            margin: 12,
            formatter: (v) => wrapAxisLabel(v, 7),
          }},
          splitLine: {{ lineStyle: {{ color: 'rgba(36, 24, 42, 0.10)' }} }},
          splitArea: {{
            areaStyle: {{
              color: ['rgba(240,98,146,0.05)', 'rgba(225,190,231,0.06)']
            }}
          }},
        }},
        series: [
          {{
            name: '评分',
            type: 'radar',
            data: [{{ value: behavior.values, name: '评分' }}],
            areaStyle: {{ opacity: 0.35 }},
            lineStyle: {{
              color: '#f06292',
              width: 2,
              shadowColor: 'rgba(240,98,146,0.25)',
              shadowBlur: 10
            }},
            itemStyle: {{ color: '#f06292' }},
            emphasis: {{
              lineStyle: {{ width: 3 }},
              itemStyle: {{ color: '#f06292' }},
            }},
          }}
        ],
      }}
    );

    const lensChart = renderRadar(
      document.getElementById('lensRadar'),
      {{
        backgroundColor: 'transparent',
        tooltip: {{
          trigger: 'item',
          confine: true,
        }},
        radar: {{
          center: ['50%', '53%'],
          indicator: lens.order.map(id => ({{ name: id, max: 5 }})),
          radius: '36%',
          splitNumber: 5,
          axisName: {{
            color: 'rgba(36,24,42,0.82)',
            fontFamily: 'Nunito Sans, system-ui',
            fontWeight: 800,
            fontSize: 10,
            lineHeight: 15,
            margin: 10,
          }},
          splitLine: {{ lineStyle: {{ color: 'rgba(36, 24, 42, 0.10)' }} }},
          splitArea: {{
            areaStyle: {{
              color: ['rgba(169,139,255,0.06)', 'rgba(240,98,146,0.04)']
            }}
          }},
        }},
        series: [
          {{
            name: '密度',
            type: 'radar',
            data: [{{ value: lens.values, name: '密度' }}],
            areaStyle: {{ opacity: 0.32 }},
            lineStyle: {{
              color: '#a98bff',
              width: 2,
              shadowColor: 'rgba(169,139,255,0.25)',
              shadowBlur: 10
            }},
            itemStyle: {{ color: '#a98bff' }},
          }}
        ],
      }}
    );

    window.__charts_ready = true;
  </script>
</body>
</html>"""

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(doc, wait_until="load", timeout=60_000)
            # Ensure ECharts finished rendering before PDF capture
            try:
                page.wait_for_function("window.__charts_ready === true", timeout=30_000)
            except Exception:
                # If CDN/network is unavailable, still output a PDF with text.
                pass
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
            )
        finally:
            browser.close()
    return pdf_bytes
