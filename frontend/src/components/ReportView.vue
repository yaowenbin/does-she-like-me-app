<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import * as echarts from 'echarts'

type LensSection = {
  lensTag: string
  lensId: 'L1' | 'L2' | 'L3' | 'L4' | 'L5' | 'L6'
  content: string
  l6Panels?: { A: string; B: string; C: string; D: string }
}

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
  // UI 层不展示内部编码 “· Lx”，避免用户看到 L1~L6 觉得是内部术语。
  const cleaned = (md || '').replace(/【([^】]*?)\s*·\s*L[1-6]\s*】/g, '【$1】')
  const html = marked.parse(cleaned) as unknown
  return sanitizeHtml(typeof html === 'string' ? html : String(html))
}

type EvidenceQuote = { quote: string; desc: string }
function extractEvidenceQuotes(text: string): EvidenceQuote[] {
  if (!text) return []

  // 优先抓“有一句话说明”的证据： （证据：<desc>：「quote」）
  const patternsWithDesc: RegExp[] = [
    /（证据[^）]*?：\s*([^「]+?)「([^」]+)」）/g,
    /（证据[^）]*?：\s*([^『]+?)『([^』]+)』）/g,
  ]

  // 退化抓“只有引文”的证据： （证据：「quote」）
  const patterns: RegExp[] = [
    /（证据[^）]*?「([^」]+)」）/g,
    /（证据[^）]*?『([^』]+)』）/g,
    /（证据[^）]*?\s*\"([^\"]+)\"）/g,
    /（证据[^）]*?\s*“([^”]+)”）/g,
    /（证据[^）]*?([^）]+)）/g,
  ]

  const out: EvidenceQuote[] = []
  const seenQuote = new Set<string>()

  for (const p of patternsWithDesc) {
    for (const m of text.matchAll(p)) {
      const desc = (m[1] || '').trim()
      const quote = (m[2] || '').trim()
      if (!quote || quote.length > 180) continue
      if (seenQuote.has(quote)) continue
      seenQuote.add(quote)
      out.push({ quote, desc })
    }
  }

  for (const p of patterns) {
    for (const m of text.matchAll(p)) {
      const quote = (m[1] || '').trim()
      if (!quote || quote.length > 180) continue
      if (seenQuote.has(quote)) continue
      seenQuote.add(quote)
      out.push({ quote, desc: '' })
    }
  }

  return out
}

function parseLensSections(md: string): LensSection[] {
  const byId = new Map<LensSection['lensId'], LensSection>()
  const order: LensSection['lensId'][] = []
  if (!md) return []
  // 防止同一透镜的多个小节标题（例如 L6 专业整合/人话要点）被当成多个“章节卡片”

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
    if (!byId.has(lensId as any)) {
      byId.set(lensId as any, { lensTag: lensTag.trim(), lensId: lensId as any, content })
      order.push(lensId as any)
    } else {
      // 同一透镜的多个分段合并显示
      const prev = byId.get(lensId as any)
      if (prev) prev.content = `${prev.content}\n\n${content}`.trim()
    }
  }
  return order.map((id) => byId.get(id)!).filter(Boolean)
}

function getBlockAfterHeading(md: string, heading: string) {
  const idx = md.indexOf(`## ${heading}`)
  if (idx < 0) return ''
  const rest = md.slice(idx + `## ${heading}`.length)
  // Stop at next `## ` heading
  const next = rest.indexOf('\n## ')
  return (next >= 0 ? rest.slice(0, next) : rest).trim()
}

function getBlockAfterSubHeading(md: string, subHeading: string) {
  const idx = md.indexOf(`### ${subHeading}`)
  if (idx < 0) return ''
  const rest = md.slice(idx + `### ${subHeading}`.length)
  const next = rest.search(/\r?\n### /)
  return (next >= 0 ? rest.slice(0, next) : rest).trim()
}

type BehaviorRow = { dimension: string; score: number | null; evidence: string; alt: string; raw: string }

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
    const partsAll = t.split('|').map((x) => x.trim())
    if (partsAll[0] === '') partsAll.shift()
    if (partsAll.length && partsAll[partsAll.length - 1] === '') partsAll.pop()
    if (partsAll.length < 2) continue

    const dimension = partsAll[0]
    const scoreRaw = partsAll[1]
    const evidence = partsAll[2] || ''
    const alt = partsAll.slice(3).join(' | ')
    if (!dimension) continue

    let score: number | null = null
    if (scoreRaw === 'nc') score = null
    else {
      const n = Number(scoreRaw)
      if (!Number.isFinite(n)) continue
      score = n
    }
    rows.push({ dimension, score, evidence, alt, raw: line })
  }
  return rows
}

type LensStrengthRow = { level: string; tag: string; meaning: string }
function parseLensStrengthTable(md: string): LensStrengthRow[] {
  const block = getBlockAfterHeading(md, '透镜强度说明')
  if (!block) return []
  const lines = block.split('\n')
  const rows: LensStrengthRow[] = []
  for (const line of lines) {
    const t = line.trim()
    if (!t.startsWith('|')) continue
    if (t.includes('---')) continue
    const partsAll = t.split('|').map((x) => x.trim())
    if (partsAll[0] === '') partsAll.shift()
    if (partsAll.length && partsAll[partsAll.length - 1] === '') partsAll.pop()
    // Expect: | 层级 | 标签 | 含义 |
    if (partsAll.length < 3) continue
    const level = partsAll[0]
    const tag = partsAll[1]
    const meaning = partsAll.slice(2).join(' | ')
    if (!level) continue
    rows.push({ level, tag, meaning })
  }
  return rows
}

function parseL6ABCDSections(content: string): { A: string; B: string; C: string; D: string } {
  const md = content || ''
  const get = (key: 'A' | 'B' | 'C' | 'D', lookAheadKeys: Array<'A' | 'B' | 'C' | 'D'>) => {
    const nextHeadingPart = lookAheadKeys.length ? `(?:${lookAheadKeys.join('|')})` : ''
    const endLookahead =
      lookAheadKeys.length ? `(?=^###\\s*(?:${nextHeadingPart})\\b|$)` : `(?=^##\\s|^---\\s*$|$)`
    const re = new RegExp(`^###\\s*${key}\\b[^\\n]*\\n([\\s\\S]*?)${endLookahead}`, 'm')
    const m = md.match(re)
    return (m?.[1] || '').trim()
  }

  return {
    A: get('A', ['B', 'C', 'D']),
    B: get('B', ['C', 'D']),
    C: get('C', ['D']),
    D: get('D', []),
  }
}

const extracted = computed(() => {
  const md = props.markdown || ''
  const evidence = extractEvidenceQuotes(md)
  const lensSections = parseLensSections(md)
  const behaviorRows = parseBehaviorTable(md)
  const lensStrengthRows = parseLensStrengthTable(md)

  // If the report includes L6 "four-layer attainability", parse its A/B/C/D subsections
  // so UI can render them as four small panels.
  for (const s of lensSections) {
    if (s.lensId === 'L6') s.l6Panels = parseL6ABCDSections(s.content)
  }

  const synthesisBlock = md.includes('## 合成') ? getBlockAfterHeading(md, '合成（Synthesis）') : ''
  const interval = synthesisBlock.match(/综合区间[:：]?\s*([^\n]+)/)?.[1]?.trim() || ''
  const nextLine = synthesisBlock.match(/下一步[^\\n]*[:：]?\s*([\\s\\S]*?)(?:\n\n|$)/)?.[1]?.trim() || ''
  const whenStop = synthesisBlock.match(/何时停[^\\n]*[:：]?\s*([\\s\\S]*?)(?:\n\n|$)/)?.[1]?.trim() || ''

  const conflictBlock = getBlockAfterSubHeading(synthesisBlock, '冲突调解')
  const narrativesBlock = getBlockAfterSubHeading(synthesisBlock, '三种叙事')

  return {
    evidence,
    lensSections,
    behaviorRows,
    lensStrengthRows,
    synthesisBlock,
    conflictBlock,
    narrativesBlock,
    interval,
    nextLine,
    whenStop,
  }
})

const humanBlock = computed(() => {
  const md = props.markdown || ''
  return getBlockAfterHeading(md, '一眼看懂（人话版）') || getBlockAfterHeading(md, '结论')
})
const heartbeatBlock = computed(() => {
  const md = props.markdown || ''
  return getBlockAfterHeading(md, '心动指数') || getBlockAfterHeading(md, '结论')
})

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

const heartbeatHearts = computed(() => {
  const { low, high } = heartbeatMeta.value
  if (low == null || high == null) return null
  const mid = (low + high) / 2
  const clamped = Math.min(100, Math.max(0, mid))
  const filled = Math.min(5, Math.max(0, Math.round((clamped / 100) * 5)))
  return { filled, total: 5 }
})

const showHero = computed(() => Boolean(humanBlock.value.trim() || heartbeatBlock.value.trim()))

const evidenceExpanded = ref(false)
const behaviorExpanded = ref(false)
const LENS_PREVIEW_CHARS = 220

const shownEvidence = computed(() => {
  const list = extracted.value.evidence
  return evidenceExpanded.value ? list : list.slice(0, 6)
})

const shownBehaviorRows = computed(() => {
  const list = extracted.value.behaviorRows
  return behaviorExpanded.value ? list : list.slice(0, 6)
})

const lensIdToFriendlyName: Record<LensSection['lensId'], string> = {
  L1: '心理沟通线索（依恋/情绪）',
  L2: '成本与互惠（投入/回避）',
  L3: '真诚度线索（模板/细节）',
  L4: '欲望的叙事翻译（关心/试探）',
  L5: '文化对照视角（可选标签）',
  L6: '四层可得性（A/B/C/D）',
}

function cleanLensTag(tag: string): string {
  // 删除尾部 “· Lx”，避免用户看到 L1-L6 这样的内部编码
  return (tag || '').replace(/\s*·\s*L[1-6]\s*$/g, '').trim()
}

function scoreToHuman(score: number | null): string {
  if (score === null) return 'nc（证据不足）'
  const n = score
  if (n <= 1) return '很弱'
  if (n === 2) return '偏弱'
  if (n === 3) return '中等'
  if (n === 4) return '偏强'
  return '很强'
}

function strengthLevelToFriendly(level: string): string {
  switch (level) {
    case 'L1':
      return '更接近证据（仍可能误判）'
    case 'L2':
      return '偏类比推演（非个体预测）'
    case 'L3':
      return '偏修辞/模因叙事（非检测）'
    case 'L4':
      return '偏文学阐释（多种译本并存）'
    case 'L5':
      return '偏文化标签（可选、非科学）'
    case 'L6':
      return '四层可得性整合（解释框架）'
    default:
      return level
  }
}

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

function shouldCollapseLens(content: string): boolean {
  return (content || '').length > LENS_PREVIEW_CHARS
}

function previewLensMarkdown(content: string): string {
  const text = (content || '').trim()
  if (text.length <= LENS_PREVIEW_CHARS) return text
  return `${text.slice(0, LENS_PREVIEW_CHARS)}...`
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
        <div v-if="heartbeatHearts != null" aria-hidden="true" style="margin-top: 8px">
          <span
            v-for="i in heartbeatHearts.total"
            :key="i"
            style="font-size: 18px; margin-right: 6px; line-height: 1"
            :style="{ color: i <= heartbeatHearts.filled ? '#f06292' : 'rgba(240,98,146,0.25)' }"
          >
            ❤
          </span>
        </div>
        <div v-if="heartbeatMeta.low != null && heartbeatMeta.high != null" class="heartbeatRangeText">
          心动区间约 {{ heartbeatMeta.low }}–{{ heartbeatMeta.high }}
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
        <div class="badge">档案分析</div>
      </div>
      <div class="muted">
        目的不是让你痛苦，也不是替你做判决。
        <b>我们在做的是：把“样本”整理清楚，让你把时间用在更值得的自己身上。</b>
      </div>
    </div>

    <details class="proFold">
      <summary class="proFoldSummary">展开深度细节（证据、图表、量表）</summary>
      <p class="proFoldHint muted">下面偏长，适合想慢慢核对细节的你；普通读者看完上面两段也可以停在这里。</p>

      <!-- 大屏优先：雷达图置顶首屏；窄屏上下堆叠 -->
      <div class="reportRadarStrip" aria-label="雷达可视化">
        <article class="reportRadarStripItem reportProCol reportProCol--charts">
          <div class="reportCardNo">R1</div>
          <div class="sectionTitle">行为维度雷达</div>
          <div class="chartBox chartBox--radar chartBox--radarHero" ref="behaviorRadarRef"></div>
          <div class="muted chartHint">基于行为层量表解析数值，非精确预测。</div>
        </article>
        <article class="reportRadarStripItem reportProCol reportProCol--charts">
          <div class="reportCardNo">R2</div>
          <div class="sectionTitle">透镜证据密度</div>
          <div class="chartBox chartBox--radar chartBox--radarHero" ref="lensRadarRef"></div>
          <div class="muted chartHint">多透镜证据密度（启发式），非科学量化。</div>
        </article>
      </div>

      <div class="reportMasonry">
        <article v-if="extracted.interval" class="reportMasonryItem reportProCol reportProCol--narrative">
          <div class="reportCardNo">01</div>
          <div class="sectionTitle">合成结论（关系复核）</div>
          <div class="bubbleText">
            <div style="font-weight: 900; margin-bottom: 6px">综合区间：{{ extracted.interval }}</div>
            <div v-if="extracted.nextLine">
              <b>关系升级下一步：</b> {{ extracted.nextLine }}
            </div>
            <div v-if="extracted.whenStop" style="margin-top: 6px">
              <b>何时停（防过度解读）：</b> {{ extracted.whenStop }}
            </div>
            <details v-if="extracted.conflictBlock" class="lensDetails" open style="margin-top: 10px">
              <summary class="lensDetailsSummary">冲突调解（温柔复核）</summary>
              <div class="lensFullMd" v-html="renderMarkdown(extracted.conflictBlock)"></div>
            </details>
            <details v-if="extracted.narrativesBlock" class="lensDetails" open style="margin-top: 10px">
              <summary class="lensDetailsSummary">三种叙事（含纯友谊）</summary>
              <div class="lensFullMd" v-html="renderMarkdown(extracted.narrativesBlock)"></div>
            </details>
          </div>
        </article>

        <article v-if="extracted.lensStrengthRows.length" class="reportMasonryItem reportProCol reportProCol--evidence">
          <div class="reportCardNo">E0</div>
          <div class="sectionTitle">这条判断有多确定（认识论强度）</div>
          <div class="evidenceList evidenceList--scroll">
            <div v-for="r in extracted.lensStrengthRows" :key="r.level + r.tag" class="evidenceItem">
              <div class="small">{{ r.level }} · {{ strengthLevelToFriendly(r.level) }}</div>
              <div style="margin-top: 6px">{{ r.meaning }}</div>
            </div>
          </div>
        </article>

        <article
          v-for="(s, idx) in extracted.lensSections"
          :key="s.lensTag"
          class="reportMasonryItem reportProCol reportProCol--narrative"
        >
          <div class="reportCardNo">{{ String(idx + 2).padStart(2, '0') }}</div>
          <div class="sectionTitle">{{ lensIdToFriendlyName[s.lensId] }}</div>
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
              <div class="bubbleTag">{{ s.lensId === 'L6' ? '四层拆解' : '透镜解读' }}</div>
              <div class="muted" style="white-space: nowrap">证据密度：{{ extractEvidenceQuotes(s.content).length }}</div>
            </div>
            <details class="lensDetails" :open="idx === 0 || !shouldCollapseLens(s.content)">
              <summary v-if="shouldCollapseLens(s.content)" class="lensDetailsSummary">
                <span>展开内容</span>
              </summary>

              <template v-if="s.lensId !== 'L6' || !s.l6Panels">
                <div
                  v-if="shouldCollapseLens(s.content)"
                  class="lensPreviewMd"
                  v-html="renderMarkdown(previewLensMarkdown(s.content))"
                ></div>
                <div class="lensFullMd" v-html="renderMarkdown(s.content)"></div>
              </template>

              <template v-else>
                <div v-if="shouldCollapseLens(s.content)" class="lensPreviewMd">
                  <div
                    style="
                      display: grid;
                      grid-template-columns: repeat(2, minmax(0, 1fr));
                      gap: 10px;
                    "
                  >
                    <div>
                      <div class="small">A 底层本能/安全感</div>
                      <div class="lensFullMd" v-html="renderMarkdown(previewLensMarkdown(s.l6Panels.A))"></div>
                    </div>
                    <div>
                      <div class="small">B 心理行为/投入节奏</div>
                      <div class="lensFullMd" v-html="renderMarkdown(previewLensMarkdown(s.l6Panels.B))"></div>
                    </div>
                    <div>
                      <div class="small">C 社会现实/成本风险</div>
                      <div class="lensFullMd" v-html="renderMarkdown(previewLensMarkdown(s.l6Panels.C))"></div>
                    </div>
                    <div>
                      <div class="small">D 表层沟通/展示信号</div>
                      <div class="lensFullMd" v-html="renderMarkdown(previewLensMarkdown(s.l6Panels.D))"></div>
                    </div>
                  </div>
                </div>

                <div class="lensFullMd">
                  <div
                    style="
                      display: grid;
                      grid-template-columns: repeat(2, minmax(0, 1fr));
                      gap: 10px;
                    "
                  >
                    <div>
                      <div class="small">A 底层本能/安全感</div>
                      <div class="lensFullMd" v-html="renderMarkdown(s.l6Panels.A || '（待验证）')"></div>
                    </div>
                    <div>
                      <div class="small">B 心理行为/投入节奏</div>
                      <div class="lensFullMd" v-html="renderMarkdown(s.l6Panels.B || '（待验证）')"></div>
                    </div>
                    <div>
                      <div class="small">C 社会现实/成本风险</div>
                      <div class="lensFullMd" v-html="renderMarkdown(s.l6Panels.C || '（待验证）')"></div>
                    </div>
                    <div>
                      <div class="small">D 表层沟通/展示信号</div>
                      <div class="lensFullMd" v-html="renderMarkdown(s.l6Panels.D || '（待验证）')"></div>
                    </div>
                  </div>
                </div>
              </template>
            </details>
          </div>
        </article>

        <article class="reportMasonryItem reportProCol reportProCol--evidence">
          <div class="reportCardNo">E1</div>
          <div class="sectionTitle">证据卡片</div>
          <div class="evidenceList evidenceList--scroll">
            <div v-if="extracted.evidence.length === 0" class="muted">未在报告中找到可展示的证据引文。</div>
            <div v-for="q in shownEvidence" :key="q.quote" class="evidenceItem">
              <div class="small">摘录</div>
              <div v-if="q.desc" class="muted" style="margin-top: 4px">{{ q.desc }}</div>
              <div style="margin-top: 6px">{{ q.quote }}</div>
            </div>
            <button
              v-if="extracted.evidence.length > 6"
              class="plainToggleBtn"
              type="button"
              @click="evidenceExpanded = !evidenceExpanded"
            >
              {{ evidenceExpanded ? '收起证据' : `展开全部证据（${extracted.evidence.length}）` }}
            </button>
          </div>
        </article>

        <article class="reportMasonryItem reportProCol reportProCol--evidence">
          <div class="reportCardNo">E2</div>
          <div class="sectionTitle">行为层量表</div>
          <div class="evidenceList evidenceList--scroll">
            <div v-if="extracted.behaviorRows.length === 0" class="muted">报告中未解析到行为层量表。</div>
            <div v-for="r in shownBehaviorRows" :key="r.dimension" class="evidenceItem">
              <div class="small">{{ r.dimension }}</div>
              <div style="font-weight: 900; margin-top: 4px">{{ scoreToHuman(r.score) }}</div>
              <div v-if="r.alt" class="muted" style="margin-top: 6px">{{ r.alt }}</div>
            </div>
            <button
              v-if="extracted.behaviorRows.length > 6"
              class="plainToggleBtn"
              type="button"
              @click="behaviorExpanded = !behaviorExpanded"
            >
              {{ behaviorExpanded ? '收起量表' : `展开全部量表（${extracted.behaviorRows.length}）` }}
            </button>
          </div>
        </article>
      </div>
    </details>
  </div>
</template>
