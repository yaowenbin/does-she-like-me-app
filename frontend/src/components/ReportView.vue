<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import * as echarts from 'echarts'

type LensSection = { lensTag: string; lensId: 'L1' | 'L2' | 'L3' | 'L4' | 'L5' | 'L6'; content: string }

const props = withDefaults(
  defineProps<{
    markdown: string
    layout?: 'default' | 'fullscreen'
  }>(),
  { layout: 'default' }
)

const isFs = computed(() => props.layout === 'fullscreen')

const behaviorRadarRef = ref<HTMLDivElement | null>(null)
const lensRadarRef = ref<HTMLDivElement | null>(null)
let behaviorChart: any | null = null
let lensChart: any | null = null

function sanitizeHtml(html: string) {
  return DOMPurify.sanitize(html)
}

function renderMarkdown(md: string) {
  // `marked` 的类型在不同版本下会对返回值进行联合（string | Promise<string>）。
  // 这里我们只走同步渲染：若类型不确定，直接做兜底转 string。
  const html = marked.parse(md || '') as unknown
  return sanitizeHtml(typeof html === 'string' ? html : String(html))
}

function extractEvidenceQuotes(text: string): string[] {
  if (!text) return []
  const patterns: RegExp[] = [
    /（证据[^）]*?「([^」]+)」）/g,
    /（证据[^）]*?『([^』]+)』）/g,
    /（证据[^）]*?\s*\"([^\"]+)\"）/g,
    /（证据[^）]*?\s*“([^”]+)”）/g,
    /（证据[^）]*?([^）]+)）/g,
  ]

  const out: string[] = []
  for (const p of patterns) {
    for (const m of text.matchAll(p)) {
      const q = m[1]?.trim()
      if (q && q.length <= 180) out.push(q)
    }
  }
  // 去重
  return Array.from(new Set(out))
}

function parseLensSections(md: string): LensSection[] {
  const out: LensSection[] = []
  if (!md) return out

  const re = /【([^】]*?·\s*L[1-6])】/g
  const matches = Array.from(md.matchAll(re))
  for (let i = 0; i < matches.length; i++) {
    const m = matches[i]
    const lensTag = m[1] // includes Lx
    const lensIdMatch = lensTag.match(/L([1-6])/)
    const lensId = lensIdMatch?.[1] ? (`L${lensIdMatch[1]}` as any) : null
    if (!lensId) continue

    const start = m.index ?? 0
    const end = i + 1 < matches.length ? (matches[i + 1].index ?? md.length) : md.length
    const slice = md.slice(start, end).trim()
    // Remove leading `【...】`
    const content = slice.replace(/^【[^】]*?】/, '').trim()
    out.push({ lensTag: lensTag.trim(), lensId: lensId as any, content })
  }
  return out
}

function getBlockAfterHeading(md: string, heading: string) {
  const idx = md.indexOf(`## ${heading}`)
  if (idx < 0) return ''
  const rest = md.slice(idx + `## ${heading}`.length)
  // Stop at next `## ` heading
  const next = rest.indexOf('\n## ')
  return (next >= 0 ? rest.slice(0, next) : rest).trim()
}

type BehaviorRow = { dimension: string; score: number | null; raw: string }

function parseBehaviorTable(md: string): BehaviorRow[] {
  const block = getBlockAfterHeading(md, '行为层量表')
  if (!block) return []
  const lines = block.split('\n')
  const rows: BehaviorRow[] = []
  for (const line of lines) {
    const t = line.trim()
    if (!t.startsWith('|')) continue
    if (t.includes('---')) continue
    // Try: | dim | score | evidence | alt |
    const parts = t.split('|').map((x) => x.trim()).filter(Boolean)
    if (parts.length < 3) continue
    const dimension = parts[0]
    const scoreRaw = parts[1]
    if (!dimension) continue

    let score: number | null = null
    if (scoreRaw === 'nc') score = null
    else {
      const n = Number(scoreRaw)
      score = Number.isFinite(n) ? n : null
    }
    rows.push({ dimension, score, raw: line })
  }
  return rows
}

const extracted = computed(() => {
  const md = props.markdown || ''
  const evidence = extractEvidenceQuotes(md)
  const lensSections = parseLensSections(md)
  const behaviorRows = parseBehaviorTable(md)

  const synthesisBlock = md.includes('## 合成') ? getBlockAfterHeading(md, '合成（Synthesis）') : ''
  const interval = synthesisBlock.match(/综合区间[:：]?\s*([^\n]+)/)?.[1]?.trim() || ''
  const nextLine = synthesisBlock.match(/下一步[^\\n]*[:：]?\s*([\\s\\S]*?)(?:\n\n|$)/)?.[1]?.trim() || ''
  const whenStop = synthesisBlock.match(/何时停[^\\n]*[:：]?\s*([\\s\\S]*?)(?:\n\n|$)/)?.[1]?.trim() || ''

  return { evidence, lensSections, behaviorRows, synthesisBlock, interval, nextLine, whenStop }
})

const humanBlock = computed(() => getBlockAfterHeading(props.markdown || '', '一眼看懂（人话版）'))
const heartbeatBlock = computed(() => getBlockAfterHeading(props.markdown || '', '心动指数'))

function parseHeartbeatBlock(block: string) {
  if (!block) {
    return { tier: '', low: null as number | null, high: null as number | null, oneLine: '' }
  }
  const tier =
    block.match(/\*\*档位\*\*\s*[:：]\s*([^\n]+)/)?.[1]?.trim() ||
    block.match(/[-*]\s*\*\*档位\*\*\s*[:：]\s*([^\n]+)/)?.[1]?.trim() ||
    ''
  const rm = block.match(/(\d+)\s*[–-]\s*(\d+)/)
  const oneLine = block.match(/\*\*一句话\*\*\s*[:：]\s*([^\n]+)/)?.[1]?.trim() || ''
  return {
    tier,
    low: rm ? Number(rm[1]) : null,
    high: rm ? Number(rm[2]) : null,
    oneLine,
  }
}

const heartbeatMeta = computed(() => parseHeartbeatBlock(heartbeatBlock.value))

const humanHtml = computed(() => renderMarkdown(humanBlock.value))

const heartbeatBarPct = computed(() => {
  const { low, high } = heartbeatMeta.value
  if (low == null || high == null) return null
  return Math.min(100, Math.max(0, Math.round((low + high) / 2)))
})

const showHero = computed(() => Boolean(humanBlock.value.trim() || heartbeatBlock.value.trim()))

const behaviorRadar = computed(() => {
  const rows = extracted.value.behaviorRows
  // 取前 6 个可读维度
  const dims = rows
    .filter((r) => r.score !== null)
    .slice(0, 6)

  const indicators = dims.map((d) => d.dimension.replace(/\s+/g, ' '))
  const values = dims.map((d) => (d.score ?? 0))
  // 兜底：如果全 nc，就给一个示意
  if (indicators.length === 0) return { indicators: ['样本不足'], values: [1] }
  return { indicators, values }
})

const lensRadar = computed(() => {
  const sections = extracted.value.lensSections
  const lensOrder: LensSection['lensId'][] = ['L1', 'L2', 'L3', 'L4', 'L5', 'L6']
  const counts: Record<string, number> = { L1: 0, L2: 0, L3: 0, L4: 0, L5: 0, L6: 0 }
  for (const s of sections) {
    const q = extractEvidenceQuotes(s.content).length
    counts[s.lensId] += q
  }
  // 0..5 归一（基于证据密度的启发式，而非科学量化）
  const values = lensOrder.map((id) => Math.min(5, counts[id]))
  return { lensOrder, values, counts }
})

/** 雷达轴文字换行，避免长维度名被裁切 */
function wrapAxisLabel(s: string, chunk: number): string {
  const t = (s || '').replace(/\s+/g, ' ').trim()
  if (t.length <= chunk) return t
  const lines: string[] = []
  for (let i = 0; i < t.length; i += chunk) {
    lines.push(t.slice(i, i + chunk))
  }
  return lines.join('\n')
}

function initCharts() {
  const bEl = behaviorRadarRef.value
  const lEl = lensRadarRef.value
  if (!bEl || !lEl) return

  behaviorChart = echarts.init(bEl)
  lensChart = echarts.init(lEl)

  const bIndicators = behaviorRadar.value.indicators
  const bValues = behaviorRadar.value.values

  const behaviorOption: any = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: 'rgba(240,98,146,0.35)',
      borderWidth: 1,
      padding: [10, 12],
      textStyle: {
        color: 'rgba(31,26,34,0.94)',
        fontFamily: 'Nunito Sans, ui-sans-serif, system-ui',
        fontWeight: 800,
        fontSize: 12,
      },
      extraCssText: 'box-shadow:0 18px 50px rgba(240,98,146,0.18);backdrop-filter: blur(10px);',
    },
    radar: {
      center: ['50%', '53%'],
      indicator: bIndicators.map((n) => ({ name: n, max: 5 })),
      radius: '34%',
      splitNumber: 5,
      axisName: {
        color: 'rgba(36, 24, 42, 0.82)',
        fontFamily: 'Nunito Sans, ui-sans-serif, system-ui',
        fontWeight: 800,
        fontSize: 10,
        lineHeight: 14,
        margin: 12,
        formatter: (v: string) => wrapAxisLabel(v, 7),
      },
      splitLine: { lineStyle: { color: 'rgba(36, 24, 42, 0.10)' } },
      splitArea: {
        areaStyle: { color: ['rgba(240,98,146,0.05)', 'rgba(225,190,231,0.06)'] },
      },
    },
    series: [
      {
        name: '行为维度',
        type: 'radar',
        data: [{ value: bValues, name: '评分' }],
        areaStyle: { opacity: 0.35 },
        lineStyle: { color: '#f06292', width: 2, shadowColor: 'rgba(240,98,146,0.25)', shadowBlur: 10 },
        itemStyle: { color: '#f06292' },
        emphasis: {
          lineStyle: { width: 3 },
          itemStyle: { color: '#f06292' },
        },
      },
    ],
  }
  behaviorChart.setOption(behaviorOption)

  const lensOrder = lensRadar.value.lensOrder
  const lensValues = lensRadar.value.values
  const lensOption: any = {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: 'rgba(169,139,255,0.35)',
      borderWidth: 1,
      padding: [10, 12],
      textStyle: {
        color: 'rgba(31,26,34,0.94)',
        fontFamily: 'Nunito Sans, ui-sans-serif, system-ui',
        fontWeight: 800,
        fontSize: 12,
      },
      extraCssText: 'box-shadow:0 18px 50px rgba(169,139,255,0.18);backdrop-filter: blur(10px);',
    },
    radar: {
      center: ['50%', '53%'],
      indicator: lensOrder.map((id) => ({ name: id, max: 5 })),
      radius: '36%',
      splitNumber: 5,
      axisName: {
        color: 'rgba(36, 24, 42, 0.82)',
        fontFamily: 'Nunito Sans, ui-sans-serif, system-ui',
        fontWeight: 800,
        fontSize: 10,
        lineHeight: 15,
        margin: 10,
      },
      splitLine: { lineStyle: { color: 'rgba(36, 24, 42, 0.10)' } },
      splitArea: {
        areaStyle: { color: ['rgba(169,139,255,0.06)', 'rgba(240,98,146,0.04)'] },
      },
    },
    series: [
      {
        name: '透镜证据密度（启发式）',
        type: 'radar',
        data: [{ value: lensValues, name: '密度' }],
        areaStyle: { opacity: 0.32 },
        lineStyle: { color: '#a98bff', width: 2, shadowColor: 'rgba(169,139,255,0.25)', shadowBlur: 10 },
        itemStyle: { color: '#a98bff' },
        emphasis: {
          lineStyle: { width: 3 },
          itemStyle: { color: '#a98bff' },
        },
      },
    ],
  }
  lensChart.setOption(lensOption)
  requestAnimationFrame(() => {
    behaviorChart?.resize()
    lensChart?.resize()
  })
}

function disposeCharts() {
  try {
    behaviorChart?.dispose()
    lensChart?.dispose()
  } catch {
    // ignore
  }
  behaviorChart = null
  lensChart = null
}

watch(
  () => props.markdown,
  async () => {
    await nextTick()
    disposeCharts()
    initCharts()
  }
)

function onWinResize() {
  behaviorChart?.resize()
  lensChart?.resize()
}

onMounted(async () => {
  await nextTick()
  initCharts()
  window.addEventListener('resize', onWinResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onWinResize)
  disposeCharts()
})
</script>

<template>
  <div :class="['reportViewRoot', { 'reportViewRoot--fs': isFs }]">
    <div v-if="showHero" class="reportHeroGrid">
      <div v-if="humanBlock.trim()" class="reportHeroCard reportHeroCard--human">
        <div class="reportHeroKicker">给忙碌的你 · 先看这段就够</div>
        <div class="reportHeroTitle">一眼看懂</div>
        <div class="reportHeroMd" v-html="humanHtml"></div>
      </div>
      <div v-if="heartbeatBlock.trim()" class="reportHeroCard reportHeroCard--pulse">
        <div class="reportHeroKicker">不是算命 · 只是一个温柔的刻度</div>
        <div class="reportHeroTitle">心动指数</div>
        <div v-if="heartbeatMeta.tier" class="heartbeatTierPill">{{ heartbeatMeta.tier }}</div>
        <div v-if="heartbeatBarPct != null" class="heartbeatGauge" aria-hidden="true">
          <div class="heartbeatGaugeFill" :style="{ width: heartbeatBarPct + '%' }"></div>
        </div>
        <div v-if="heartbeatMeta.low != null && heartbeatMeta.high != null" class="heartbeatRangeText">
          区间约 {{ heartbeatMeta.low }}–{{ heartbeatMeta.high }}（越高越偏「心动信号」一侧，仍非精确预测）
        </div>
        <div v-if="heartbeatMeta.oneLine" class="heartbeatOneLine">{{ heartbeatMeta.oneLine }}</div>
        <div
          v-else
          class="reportHeroMd heartbeatFallbackMd"
          v-html="renderMarkdown(heartbeatBlock)"
        ></div>
      </div>
    </div>

    <div class="healNotice">
      <div class="bubbleHeader">
        <div class="bubbleTag">自我关爱提醒</div>
        <div class="badge">治愈模式 · 档案级分析</div>
      </div>
      <div class="muted">
        目的不是让你痛苦，也不是替你做判决。
        <b>我们在做的是：把“样本”整理清楚，让你把时间用在更值得的自己身上。</b>
      </div>
    </div>

    <details class="proFold" open>
      <summary class="proFoldSummary">专业分析（证据、图表与量表）</summary>
      <p class="proFoldHint muted">下面偏长，适合想慢慢核对细节的你；普通读者看完上面两段也可以停在这里。</p>

      <div class="reportProGrid">
        <div class="reportProCol reportProCol--narrative">
          <div class="reportColTitle">第 1 列 · 合成与透镜</div>
          <div class="bubbleWrap" v-if="extracted.interval">
            <div class="sectionTitle">番剧字幕（合成结论）</div>
            <div class="bubbleText">
              <div style="font-weight: 900; margin-bottom: 6px">综合区间：{{ extracted.interval }}</div>
              <div v-if="extracted.nextLine">
                <b>下一步：</b> {{ extracted.nextLine }}
              </div>
              <div v-if="extracted.whenStop" style="margin-top: 6px">
                <b>何时停：</b> {{ extracted.whenStop }}
              </div>
            </div>
          </div>

          <div class="reportLensStack">
            <div class="bubbleWrap" v-for="s in extracted.lensSections" :key="s.lensTag">
              <div class="sectionTitle">章节（{{ s.lensId }}）</div>
              <div class="bubbleText">
                <div
                  style="
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    gap: 10px;
                    margin-bottom: 8px;
                    flex-wrap: wrap;
                  "
                >
                  <div class="bubbleTag">{{ s.lensTag }}</div>
                  <div class="muted" style="white-space: nowrap">证据密度：{{ extractEvidenceQuotes(s.content).length }}</div>
                </div>
                <div v-html="renderMarkdown(s.content)"></div>
              </div>
            </div>
          </div>
        </div>

        <div class="reportProCol reportProCol--charts">
          <div class="reportColTitle">第 2 列 · 雷达图</div>
          <div class="sectionTitle">行为维度雷达</div>
          <div class="chartBox chartBox--radar" ref="behaviorRadarRef"></div>
          <div class="muted chartHint">
            基于「行为层量表」可解析数值；半径留白便于完整显示轴标签。
          </div>

          <div class="sectionTitle" style="margin-top: 8px">透镜证据密度</div>
          <div class="chartBox chartBox--radar" ref="lensRadarRef"></div>
          <div class="muted chartHint">L1–L6 启发式密度，非科学量化。</div>
        </div>

        <div class="reportProCol reportProCol--evidence">
          <div class="reportColTitle">第 3 列 · 摘录与量表</div>
          <div class="sectionTitle">证据卡片</div>
          <div class="evidenceList evidenceList--scroll">
            <div v-if="extracted.evidence.length === 0" class="muted">未在报告中找到可展示的证据引文。</div>
            <div v-for="q in extracted.evidence.slice(0, 12)" :key="q" class="evidenceItem">
              <div class="small">摘录（用于复核，不做判决）</div>
              <div>{{ q }}</div>
            </div>
          </div>

          <div class="sectionTitle" style="margin-top: 14px">行为层量表（可复核）</div>
          <div class="evidenceList evidenceList--scroll">
            <div v-if="extracted.behaviorRows.length === 0" class="muted">报告中未解析到行为层量表。</div>
            <div v-for="r in extracted.behaviorRows.slice(0, 12)" :key="r.dimension" class="evidenceItem">
              <div class="small">{{ r.dimension }}</div>
              <div style="font-weight: 900">
                {{ r.score === null ? 'nc' : r.score }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </details>
  </div>
</template>

