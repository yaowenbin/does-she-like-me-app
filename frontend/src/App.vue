<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import type { FormInst, FormRules } from 'naive-ui'
import {
  NButton,
  NConfigProvider,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSwitch,
  NTabs,
  NTabPane,
  NSelect,
} from 'naive-ui'
import {
  analyzeArchive,
  createArchive,
  downloadReportPdf,
  getAnalyzePlan,
  getAnalyzeFeatures,
  getArchiveDetail,
  getEntitlementsMe,
  getWechatScene,
  importWxTxt,
  importPaste,
  importOcr,
  listArchives,
  redeemGiftCode,
  type AnalyzePlan,
  type AnalyzeFeatures,
  type ArchiveSummary,
  type AnalyzeResultDto,
  type EntitlementsMe,
} from './api'
import AdminPanel from './components/AdminPanel.vue'
import ReportView from './components/ReportView.vue'
import SakuraScene from './components/SakuraScene.vue'
import { toast } from './http'

const loading = ref(false)
/** 仅「生成报告」阶段的整页温馨 loading */
const reportGenerating = ref(false)
const error = ref<string | null>(null)
/** 报告全屏层：生成后自动打开，也可手动打开 */
const reportFullscreen = ref(false)

/** 设备维度次数 / 卡密 / 公众号引流 */
const entitlements = ref<EntitlementsMe | null>(null)
/** 分析流水线配置（深度扣次、reasoner 模型名） */
const analyzeFeatures = ref<AnalyzeFeatures | null>(null)
/** 深度推理失败但已保存基础稿时的提示 */
const analysisWarn = ref<string | null>(null)
const analysisTrace = ref<Array<{ step: string; status: string; model?: string | null; error?: string | null }>>([])
const analyzePlan = ref<AnalyzePlan | null>(null)
const scoringResult = ref<Record<string, any> | null>(null)
const friendlySummary = ref<Record<string, any> | null>(null)
const redeemForm = reactive({ code: '' })
const redeemFormRef = ref<FormInst | null>(null)
const wechatShortCode = ref('')
const pdfExporting = ref(false)

const wechatMpProfileUrl = (
  import.meta.env.VITE_WECHAT_MP_URL?.toString().replace(/\/$/, '') || ''
).trim()

const warmMessages = [
  '正在慢慢读你的聊天记录，不着急…',
  '把感受整理成语言，需要一点点时间。',
  '会先帮你写「一眼看懂」和心动指数，再写专业分析。',
  '如果等久了，就当给自己泡杯热饮的间隙。',
]

const warmMessageIdx = ref(0)
let warmTimer: ReturnType<typeof setInterval> | null = null

function startWarmMessages() {
  warmMessageIdx.value = 0
  stopWarmMessages()
  warmTimer = setInterval(() => {
    warmMessageIdx.value = (warmMessageIdx.value + 1) % warmMessages.length
  }, 2800)
}

function stopWarmMessages() {
  if (warmTimer) {
    clearInterval(warmTimer)
    warmTimer = null
  }
}

const uiBusy = computed(() => loading.value || reportGenerating.value)

/** 运营后台：URL hash 为 #/admin */
const adminRoute = ref(false)
function syncAdminHash() {
  const raw = window.location.hash.replace(/^#\/?/, '').split(/[?#]/)[0]
  adminRoute.value = raw === 'admin'
}

const archives = ref<ArchiveSummary[]>([])
const activeId = ref<string>('')
const detail = ref<Awaited<ReturnType<typeof getArchiveDetail>> | null>(null)

const form = reactive({
  name: '',
  stage: '',
  scenario: '',
  zodiac: '',
  mbti: '',
  temperature: 0.7,
  /** 第二段：deepseek-reasoner 整稿审稿（可能多扣次） */
  deepReasoning: false,
})

const stageOptions = [
  { label: '初识', value: '初识' },
  { label: '暧昧', value: '暧昧' },
  { label: '已表白', value: '已表白' },
  { label: '冷淡期', value: '冷淡期' },
  { label: '其他', value: '其他' },
]

const scenarioOptions = [
  { label: '私聊', value: '私聊' },
  { label: '群聊', value: '群聊' },
  { label: '工作软件', value: '工作软件' },
  { label: '其他', value: '其他' },
]

const zodiacOptions = [
  { label: '不填', value: '' },
  { label: '白羊座', value: '白羊座' },
  { label: '金牛座', value: '金牛座' },
  { label: '双子座', value: '双子座' },
  { label: '巨蟹座', value: '巨蟹座' },
  { label: '狮子座', value: '狮子座' },
  { label: '处女座', value: '处女座' },
  { label: '天秤座', value: '天秤座' },
  { label: '天蝎座', value: '天蝎座' },
  { label: '射手座', value: '射手座' },
  { label: '摩羯座', value: '摩羯座' },
  { label: '水瓶座', value: '水瓶座' },
  { label: '双鱼座', value: '双鱼座' },
]

const mbtiOptions = [
  { label: '不填', value: '' },
  { label: 'INTJ', value: 'INTJ' },
  { label: 'INTP', value: 'INTP' },
  { label: 'ENTJ', value: 'ENTJ' },
  { label: 'ENTP', value: 'ENTP' },
  { label: 'INFJ', value: 'INFJ' },
  { label: 'INFP', value: 'INFP' },
  { label: 'ENFJ', value: 'ENFJ' },
  { label: 'ENFP', value: 'ENFP' },
  { label: 'ISTJ', value: 'ISTJ' },
  { label: 'ISFJ', value: 'ISFJ' },
  { label: 'ESTJ', value: 'ESTJ' },
  { label: 'ESFJ', value: 'ESFJ' },
  { label: 'ISTP', value: 'ISTP' },
  { label: 'ISFP', value: 'ISFP' },
  { label: 'ESTP', value: 'ESTP' },
  { label: 'ESFP', value: 'ESFP' },
]

function createTagOption(label: string) {
  return { label, value: label }
}

const txtState = reactive({
  files: [] as File[],
  imported: false,
  importedSize: 0,
})

const pasteState = reactive({
  text: '',
  importedSize: 0,
})

const ocrState = reactive({
  files: [] as File[],
  importedSize: 0,
  preview: '',
})

// 仅用于展示预览缩略图：需要在移除/切换档案时 revoke，避免内存泄漏
const ocrPreviewUrls = ref<string[]>([])

const wxTxtFileInputRef = ref<HTMLInputElement | null>(null)
const ocrFileInputRef = ref<HTMLInputElement | null>(null)

const archiveFormRef = ref<FormInst | null>(null)
const pasteFormRef = ref<FormInst | null>(null)

const archiveFormRules: FormRules = {
  name: [
    {
      validator: (_r, v: string) => {
        if (!v || !String(v).trim()) return new Error('请填写档案名称')
        if (String(v).trim().length > 80) return new Error('名称请控制在 80 字以内')
        return true
      },
      trigger: ['input', 'blur'],
    },
  ],
  stage: [{ required: true, type: 'string', message: '请选择关系阶段', trigger: ['change', 'blur'] }],
  scenario: [{ required: true, type: 'string', message: '请选择聊天场景', trigger: ['change', 'blur'] }],
}

const redeemFormRules: FormRules = {
  code: [
    { required: true, message: '请输入卡密', trigger: ['input', 'blur'] },
    { min: 4, message: '卡密至少 4 位', trigger: ['input', 'blur'] },
  ],
}

const pasteRules: FormRules = {
  text: [
    {
      validator: (_r, v: string) => {
        if (!v || !String(v).trim()) return new Error('请粘贴聊天内容')
        return true
      },
      trigger: ['input', 'blur'],
    },
  ],
}

const active = computed(() => archives.value.find((a) => a.id === activeId.value))

const themeOverrides = {
  common: {
    primaryColor: '#F06292',
    primaryColorHover: '#E84F7E',
    primaryColorPressed: '#D81B60',
  },
} as const

const archiveSearch = ref('')
const archiveStatus = ref<'all' | 'pending' | 'uploaded' | 'analyzed'>('all')
const archiveStatusOptions = [
  { label: '全部', value: 'all' },
  { label: '待导入', value: 'pending' },
  { label: '已导入', value: 'uploaded' },
  { label: '已分析', value: 'analyzed' },
]

const filteredArchives = computed(() => {
  const q = archiveSearch.value.trim()
  const status = archiveStatus.value
  const list = archives.value.filter((a) => {
    if (status === 'pending') return !a.has_upload && !a.has_report
    if (status === 'uploaded') return a.has_upload && !a.has_report
    if (status === 'analyzed') return a.has_report
    return true
  })

  const searched = q
    ? list.filter((a) => {
        const name = (a.name || '').toLowerCase()
        const stage = (a.stage || '').toLowerCase()
        const scenario = (a.scenario || '').toLowerCase()
        return name.includes(q.toLowerCase()) || stage.includes(q.toLowerCase()) || scenario.includes(q.toLowerCase())
      })
    : list

  // analyzed > uploaded > pending
  const rank = (a: ArchiveSummary) => (a.has_report ? 3 : a.has_upload ? 1 : 0)
  return searched.slice().sort((a, b) => {
    const dr = rank(b) - rank(a)
    if (dr !== 0) return dr
    return (b.name || '').localeCompare(a.name || '')
  })
})

function badgeFor(a: ArchiveSummary | undefined) {
  if (!a) return { text: '未选择', cls: '' }
  if (a.has_report) return { text: '已分析', cls: 'badgeOk' }
  if (a.has_upload) return { text: '已导入', cls: 'badgeWarn' }
  return { text: '待导入', cls: '' }
}

async function refreshArchives() {
  try {
    archives.value = await listArchives()
    localStorage.setItem('dslm_archives_cache_v1', JSON.stringify(archives.value))
    if (activeId.value && !archives.value.some((a) => a.id === activeId.value)) activeId.value = ''
    if (!activeId.value && archives.value.length) activeId.value = archives.value[0].id
  } catch (e) {
    if (!axios.isAxiosError(e)) throw e
    archives.value = []
    activeId.value = ''
  }
}

async function refreshDetail() {
  if (!activeId.value) {
    detail.value = null
    analysisTrace.value = []
    scoringResult.value = null
    friendlySummary.value = null
    return
  }
  try {
    detail.value = await getArchiveDetail(activeId.value)
  } catch (e) {
    if (axios.isAxiosError(e)) {
      detail.value = null
      return
    }
    throw e
  }
  if (!detail.value) return
  txtState.imported = Boolean(detail.value.archive.has_upload)
  txtState.importedSize = 0
  // 切换档案时清掉“上一档案”的输入/预览统计，避免误导
  txtState.files = []
  pasteState.importedSize = 0

  // revoke 上一次 OCR 预览 URL
  for (const u of ocrPreviewUrls.value) URL.revokeObjectURL(u)
  ocrPreviewUrls.value = []

  ocrState.files = []
  ocrState.importedSize = 0
  ocrState.preview = ''
  analysisTrace.value = []
  scoringResult.value = (detail.value.report as any)?.scoring?.scoring_result || null
  friendlySummary.value = (detail.value.report as any)?.scoring?.friendly_summary || null
  await refreshAnalyzePlan()
}

function onWxTxtPicked(e: Event) {
  const files = (e.target as HTMLInputElement).files
  txtState.files = files ? [files[0]].filter(Boolean) : []
  txtState.imported = false
  txtState.importedSize = 0
}

function onOcrPicked(e: Event) {
  const files = (e.target as HTMLInputElement).files
  for (const u of ocrPreviewUrls.value) URL.revokeObjectURL(u)
  ocrPreviewUrls.value = []

  const selected = Array.from(files || [])
  ocrState.files = selected
  ocrPreviewUrls.value = selected.map((f) => URL.createObjectURL(f))

  ocrState.importedSize = 0
  ocrState.preview = ''
}

function removeTxtAt(idx: number) {
  txtState.files.splice(idx, 1)
  txtState.imported = false
  txtState.importedSize = 0
}

function removeOcrAt(idx: number) {
  const u = ocrPreviewUrls.value[idx]
  if (u) URL.revokeObjectURL(u)
  ocrPreviewUrls.value.splice(idx, 1)
  ocrState.files.splice(idx, 1)

  ocrState.importedSize = 0
  ocrState.preview = ''
}

async function onCreateArchive() {
  try {
    await archiveFormRef.value?.validate()
  } catch {
    return
  }
  if (!canMutateWithCredits.value) return
  error.value = null
  loading.value = true
  try {
    const tags: Record<string, any> = {}
    if (form.zodiac.trim()) tags.zodiac = form.zodiac.trim()
    if (form.mbti.trim()) tags.mbti = form.mbti.trim()

    const res = await createArchive({
      name: form.name.trim(),
      stage: form.stage.trim(),
      scenario: form.scenario.trim(),
      tags,
    })
    await refreshArchives()
    activeId.value = res.id
    await refreshDetail()
    toast.success('档案已创建')
  } catch (e: any) {
    if (!axios.isAxiosError(e)) error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

async function onImportWxTxt() {
  if (!activeId.value) return
  if (!canMutateWithCredits.value) return
  if (!txtState.files.length) {
    error.value = '请先选择 txt 文件'
    return
  }
  error.value = null
  loading.value = true
  try {
    const res = await importWxTxt(activeId.value, txtState.files[0])
    txtState.imported = true
    txtState.importedSize = Number(res.normalized_size || 0)
    importMode.value = 'txt'
    await refreshDetail()
    toast.success('TXT 已导入')
  } catch (e: any) {
    if (!axios.isAxiosError(e)) error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

async function onImportPaste() {
  if (!activeId.value) return
  if (!canMutateWithCredits.value) return
  try {
    await pasteFormRef.value?.validate()
  } catch {
    return
  }
  error.value = null
  loading.value = true
  try {
    const res = await importPaste(activeId.value, {
      text: pasteState.text,
      filename: 'paste.txt',
    })
    txtState.imported = true
    txtState.importedSize = Number(res.normalized_size || 0)
    pasteState.importedSize = txtState.importedSize
    importMode.value = 'paste'
    await refreshDetail()
    toast.success('粘贴内容已导入')
  } catch (e: any) {
    if (!axios.isAxiosError(e)) error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

async function onImportOcr() {
  if (!activeId.value) return
  if (!canMutateWithCredits.value) return
  if (!ocrState.files || ocrState.files.length === 0) {
    error.value = '请先选择聊天截图图片'
    return
  }
  error.value = null
  loading.value = true
  try {
    const res = await importOcr(activeId.value, ocrState.files, { lang: 'chi_sim' })
    ocrState.importedSize = Number(res.normalized_size || 0)
    ocrState.preview = String(res.ocr_preview || '')
    await refreshDetail()
    importMode.value = 'ocr'
    toast.success('截图 OCR 已完成')
  } catch (e: any) {
    if (!axios.isAxiosError(e)) error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

async function onAnalyze() {
  if (!activeId.value) return
  error.value = null
  analysisWarn.value = null
  loading.value = true
  reportGenerating.value = true
  startWarmMessages()
  try {
    const res: AnalyzeResultDto = await analyzeArchive(activeId.value, {
      temperature: Number(form.temperature),
      deep_reasoning: form.deepReasoning,
    })
    if (res.reasoner_failed) {
      analysisWarn.value =
        (res.reasoner_error && `深度推理未生效（已保存基础稿）：${res.reasoner_error}`) ||
        '深度推理未生效，已保存基础稿；附加次数已退回（若开启扣次）。'
    }
    await refreshDetail()
    analysisTrace.value = Array.isArray(res.execution_trace) ? res.execution_trace : []
    scoringResult.value = res.scoring_result || null
    friendlySummary.value = res.friendly_summary || null
    // detail 会刷新到最新 report
    detail.value = {
      ...(detail.value as any),
      report: {
        model: res.model,
        report_markdown: res.report_markdown,
        scoring: {
          input_signal: res.input_signal || {},
          scoring_result: res.scoring_result || {},
          friendly_summary: res.friendly_summary || {},
        },
        created_at: new Date().toISOString(),
      },
    }
    reportFullscreen.value = true
    await refreshEntitlements()
    await refreshAnalyzePlan()
    toast.success('报告已生成')
  } catch (e: any) {
    if (!axios.isAxiosError(e)) error.value = e?.message || String(e)
  } finally {
    stopWarmMessages()
    loading.value = false
    reportGenerating.value = false
  }
}

function openReportFullscreen() {
  if (detail.value?.report?.report_markdown) reportFullscreen.value = true
}

function exitReportFullscreen() {
  reportFullscreen.value = false
}

async function exportReportPdf() {
  if (!activeId.value) return
  error.value = null
  pdfExporting.value = true
  try {
    const blob = await downloadReportPdf(activeId.value)
    const u = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = u
    a.download = `report-${activeId.value.slice(0, 8)}.pdf`
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(u)
    toast.success('PDF 已开始下载')
  } catch (e: any) {
    if (!axios.isAxiosError(e)) error.value = e?.message || String(e)
  } finally {
    pdfExporting.value = false
  }
}

async function refreshAnalyzeFeatures() {
  try {
    analyzeFeatures.value = await getAnalyzeFeatures()
  } catch {
    analyzeFeatures.value = null
  }
}

async function refreshAnalyzePlan() {
  if (!activeId.value) {
    analyzePlan.value = null
    return
  }
  try {
    analyzePlan.value = await getAnalyzePlan(activeId.value, form.deepReasoning)
  } catch {
    analyzePlan.value = null
  }
}

async function refreshEntitlements() {
  try {
    entitlements.value = await getEntitlementsMe()
    if (entitlements.value?.entitlements_enforced) {
      const s = await getWechatScene()
      wechatShortCode.value = s.short_code
    } else {
      wechatShortCode.value = ''
    }
    await refreshAnalyzeFeatures()
    await refreshAnalyzePlan()
  } catch {
    entitlements.value = null
  }
}

async function onRedeemCode() {
  try {
    await redeemFormRef.value?.validate()
  } catch {
    return
  }
  error.value = null
  try {
    await redeemGiftCode(redeemForm.code.trim())
    redeemForm.code = ''
    toast.success('兑换成功')
    await refreshEntitlements()
  } catch (e: any) {
    if (!axios.isAxiosError(e)) error.value = e?.message || String(e)
  }
}

onUnmounted(() => {
  window.removeEventListener('hashchange', syncAdminHash)
  stopWarmMessages()
})

onMounted(async () => {
  syncAdminHash()
  window.addEventListener('hashchange', syncAdminHash)
  try {
    const cached = localStorage.getItem('dslm_archives_cache_v1')
    if (cached) {
      try {
        archives.value = JSON.parse(cached) as ArchiveSummary[]
      } catch {
        // ignore cache parse errors
      }
    }
    const savedId = localStorage.getItem('dslm_active_id_v1')
    if (savedId) activeId.value = savedId

    await refreshArchives()
    await refreshDetail()
    await refreshEntitlements()
  } catch (e: any) {
    if (!axios.isAxiosError(e)) error.value = e?.message || String(e)
  }
  await refreshAnalyzeFeatures()
})

const badge = computed(() => badgeFor(active.value))

const flowStep = computed(() => {
  const a = active.value
  if (!a) return 1
  if (!a.has_upload) return 1
  if (a.has_upload && !a.has_report) return 2
  return 3
})

type ImportMode = 'txt' | 'ocr' | 'paste'
const importMode = ref<ImportMode>('txt')

const deepExtraCredits = computed(() => analyzeFeatures.value?.deep_reason_extra_credits ?? 1)

const creditsNeededForAnalyze = computed(() => {
  if (!entitlements.value?.entitlements_enforced) return 1
  return form.deepReasoning ? 1 + deepExtraCredits.value : 1
})

const canAnalyze = computed(() => {
  if (!detail.value?.archive?.has_upload) return false
  if (analyzePlan.value && !analyzePlan.value.can_analyze) return false
  if (entitlements.value?.entitlements_enforced) {
    if (entitlements.value.credits < creditsNeededForAnalyze.value) return false
  }
  return true
})

const pipelineStepLabels: Record<string, string> = {
  build: '构建提示词',
  base: '主模型生成',
  reasoner: '深度推理复核',
  finalize: '基础稿收束',
  persist: '报告入库',
}

const traceStatusLabels: Record<string, string> = {
  ok: '完成',
  failed: '失败',
}

/** 与后端一致：开启扣次时，新建档案与导入材料需至少 1 次额度 */
const canMutateWithCredits = computed(() => {
  const e = entitlements.value
  if (!e?.entitlements_enforced) return true
  return e.credits >= 1
})

watch(
  () => activeId.value,
  (id) => {
    if (id) localStorage.setItem('dslm_active_id_v1', id)
  }
)

watch(
  () => form.deepReasoning,
  async () => {
    await refreshAnalyzePlan()
  }
)

watch(reportFullscreen, (v) => {
  document.body.style.overflow = v ? 'hidden' : ''
})
</script>

<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <AdminPanel v-if="adminRoute" @exit="syncAdminHash" />

    <template v-if="!adminRoute">
    <SakuraScene v-show="!reportFullscreen" />

    <Teleport to="body">
      <div v-if="reportGenerating" class="pageLoadingOverlay" aria-live="polite" aria-busy="true">
        <div class="pageLoadingInner">
          <div class="pageLoadingSpinner" />
          <div class="pageLoadingTitle">正在生成治愈报告</div>
          <div class="pageLoadingSub">{{ warmMessages[warmMessageIdx] }}</div>
          <div class="pageLoadingHint">关闭本页不会中断服务端任务；但若刷新浏览器，请稍后在同档案重试。</div>
        </div>
      </div>
    </Teleport>

    <div v-show="!reportFullscreen" class="container">
      <div class="heroBanner">
        <div class="heroTitle">她爱你嘛 · 治愈报告</div>
        <div class="heroSubtitle">
          作用：导入 wx 聊天 txt / 截图 OCR → 生成证据卡片与多透镜解读 → 调用 DeepSeek 返回治愈报告（Markdown）。
        </div>
        <div class="heroSteps">
          <div class="heroStep" :class="{ heroStepActive: flowStep === 1 }">
            <div class="heroStepNum">1</div>
            选择材料
          </div>
          <div class="heroStep" :class="{ heroStepActive: flowStep === 2 }">
            <div class="heroStepNum">2</div>
            归一化导入
          </div>
          <div class="heroStep" :class="{ heroStepActive: flowStep === 3 }">
            <div class="heroStepNum">3</div>
            生成治愈报告
          </div>
        </div>
        <div class="muted" style="margin-top: 10px">
          提醒：请仅上传你有权使用的材料；不要用于骚扰或操控。
        </div>
        <div class="muted tiny" style="margin-top: 8px">
          <a href="#/admin" class="footerAdminLink">卡密运营后台（需管理密钥）</a>
        </div>
      </div>

      <div class="grid">
        <div class="card leftCol">
          <h2>档案列表</h2>
          <div class="muted" style="margin-bottom: 10px">
            点击切换档案。未分析则先导入再分析。
          </div>

          <n-input v-model:value="archiveSearch" placeholder="搜索档案（名称/阶段/场景）" style="width: 100%; margin-bottom: 10px" />
          <n-select
            v-model:value="archiveStatus"
            :options="archiveStatusOptions"
            placeholder="状态筛选"
            style="width: 100%; margin-bottom: 10px"
          />

          <div class="archiveListScroll">
            <div
            v-for="a in filteredArchives"
            :key="a.id"
            class="archiveItem"
            :class="{ archiveItemActive: a.id === activeId }"
            @click="activeId = a.id; refreshDetail()"
            role="button"
            tabindex="0"
          >
            <div>
              <div style="font-weight: 700; font-size: 13px">
                {{ a.name || '未命名' }}
              </div>
              <div class="muted" style="font-size: 11px">
                {{ a.stage || 'na' }} · {{ a.scenario || 'na' }}
              </div>
            </div>
            <div class="badge" :class="badgeFor(a).cls">
              {{ badgeFor(a).text }}
            </div>
            </div>
          </div>

          <div style="height: 10px"></div>
          <h2>新建档案</h2>
          <div class="muted tiny" style="margin-bottom: 8px">名称、关系阶段、聊天场景为必填；标签可空。</div>

          <n-form
            ref="archiveFormRef"
            :model="form"
            :rules="archiveFormRules"
            label-placement="left"
            label-width="96"
            require-mark-placement="right-hanging"
            size="small"
          >
            <n-form-item path="name" label="档案名称">
              <n-input v-model:value="form.name" placeholder="例如：2024 暧昧期" />
            </n-form-item>
            <n-form-item path="stage" label="关系阶段">
              <n-select v-model:value="form.stage" :options="stageOptions" placeholder="请选择" />
            </n-form-item>
            <n-form-item path="scenario" label="聊天场景">
              <n-select v-model:value="form.scenario" :options="scenarioOptions" placeholder="请选择" />
            </n-form-item>
            <n-form-item label="星座（可选）">
              <n-select
                v-model:value="form.zodiac"
                :options="zodiacOptions"
                placeholder="例如：双子座"
                clearable
                filterable
                tag
                :onCreate="createTagOption"
              />
            </n-form-item>
            <n-form-item label="MBTI（可选）">
              <n-select
                v-model:value="form.mbti"
                :options="mbtiOptions"
                placeholder="例如：ENFP"
                clearable
                filterable
                tag
                :onCreate="createTagOption"
              />
            </n-form-item>
          </n-form>

          <div style="height: 10px"></div>
          <n-button
            :disabled="uiBusy || !canMutateWithCredits"
            type="primary"
            :loading="loading && !reportGenerating"
            style="width: 100%"
            @click="onCreateArchive"
          >
            新建档案
          </n-button>
        </div>

        <div class="card rightCol">
          <h2>导入与分析</h2>

          <div v-if="entitlements" class="entitlementsBar">
            <div class="entitlementsRow">
              <span
                >剩余分析次数：<b class="creditNum">{{ entitlements.credits }}</b></span
              >
              <span v-if="entitlements.entitlements_enforced" class="muted tiny"
                >每次生成报告扣 1 次</span
              >
              <span v-else class="muted tiny">当前为开放联调（未强制扣次）</span>
            </div>
            <n-form ref="redeemFormRef" :model="redeemForm" :rules="redeemFormRules" class="entitlementsRedeemForm">
              <div class="entitlementsRow entitlementsActions">
                <n-form-item path="code" :show-label="false" style="flex: 1; min-width: 120px; max-width: 220px; margin-bottom: 0">
                  <n-input
                    v-model:value="redeemForm.code"
                    size="small"
                    placeholder="输入卡密，兑换次数"
                    @keydown.enter.prevent="onRedeemCode"
                  />
                </n-form-item>
                <n-button size="small" type="primary" :disabled="uiBusy" style="margin-bottom: 0" @click="onRedeemCode">
                  兑换
                </n-button>
              <a
                v-if="wechatMpProfileUrl"
                class="oaLink"
                :href="wechatMpProfileUrl"
                target="_blank"
                rel="noopener noreferrer"
              >
                关注公众号
              </a>
              </div>
            </n-form>
            <div v-if="entitlements.entitlements_enforced && !canMutateWithCredits" class="creditBlockHint">
              次数不足：无法新建档案或导入聊天材料；请先兑换卡密或关注公众号领取（与生成报告共用额度）。
            </div>
            <div v-if="entitlements.entitlements_enforced && wechatShortCode" class="muted tiny sceneHint">
              公众平台创建<strong>带参二维码</strong>时，scene 填写：
              <code class="sceneCode">{{ wechatShortCode }}</code>
              · 用户扫码关注后，本设备自动获赠一次（每个设备仅一次）。
            </div>
          </div>

          <div class="muted" style="margin-bottom: 10px">
            当前档案：<b>{{ active?.name || '未命名' }}</b>（{{ badge.text }}）
          </div>

          <div v-if="activeId">
            <div class="importTabsWrap">
              <div class="muted" style="margin-bottom: 6px">导入方式</div>
              <n-tabs v-model:value="importMode" type="segment" animated>
                <n-tab-pane name="txt" tab="TXT">
                  <div class="importPanel">
                    <label>导入 wx 聊天 txt</label>
                    <input ref="wxTxtFileInputRef" type="file" accept=".txt,text/plain" hidden @change="onWxTxtPicked" />

                    <div class="row" style="margin-top: 10px">
                      <n-button type="default" :disabled="uiBusy" @click="wxTxtFileInputRef?.click()">选择 txt</n-button>
                      <n-button
                        type="primary"
                        :disabled="uiBusy || !txtState.files.length || !canMutateWithCredits"
                        :loading="loading && !reportGenerating"
                        @click="onImportWxTxt"
                      >
                        上传并归一化
                      </n-button>
                    </div>

                    <div class="uploadFileList" v-if="txtState.files.length">
                      <div v-for="(f, idx) in txtState.files" :key="f.name + ':' + idx" class="uploadFileRow">
                        <div class="uploadFileName">{{ f.name }}</div>
                        <n-button type="error" size="tiny" :disabled="uiBusy" @click="removeTxtAt(idx)">移除</n-button>
                      </div>
                    </div>

                    <div class="muted" v-else style="font-size: 12px; margin-top: 10px">
                      还没选择文件，先上传 `txt`。
                    </div>

                    <div class="muted" v-if="txtState.imported" style="font-size: 12px; margin-top: 10px">
                      已导入（归一化字符数：{{ txtState.importedSize || 'ok' }}）
                    </div>
                  </div>
                </n-tab-pane>

                <n-tab-pane name="ocr" tab="OCR">
                  <div class="importPanel">
                    <label>如果无法导出：上传聊天截图（OCR，支持多张）</label>
                    <input ref="ocrFileInputRef" type="file" accept="image/*" multiple hidden @change="onOcrPicked" />

                    <div class="row" style="margin-top: 10px">
                      <n-button type="default" :disabled="uiBusy" @click="ocrFileInputRef?.click()">选择截图</n-button>
                      <n-button
                        type="primary"
                        :disabled="uiBusy || ocrState.files.length === 0 || !canMutateWithCredits"
                        :loading="loading && !reportGenerating"
                        @click="onImportOcr"
                      >
                        OCR 并归一化
                      </n-button>
                    </div>

                    <div class="muted" v-if="ocrState.files.length" style="font-size: 12px; margin-top: 10px">
                      已选择：{{ ocrState.files.length }} 张截图
                    </div>
                    <div class="muted" v-else style="font-size: 12px; margin-top: 10px">
                      还没选择截图，先点「选择截图」。
                    </div>

                    <div class="uploadThumbGrid" v-if="ocrPreviewUrls.length">
                      <div v-for="(url, idx) in ocrPreviewUrls" :key="url" class="uploadThumbItem">
                        <img :src="url" class="uploadThumbImg" alt="ocr-preview" />
                        <div class="uploadThumbFooter">
                          <div class="uploadThumbName" :title="ocrState.files[idx]?.name || ''">
                            {{ ocrState.files[idx]?.name || '截图' }}
                          </div>
                          <n-button type="error" size="tiny" :disabled="uiBusy" @click="removeOcrAt(idx)">移除</n-button>
                        </div>
                      </div>
                    </div>

                    <div class="muted" v-if="ocrState.importedSize" style="font-size: 12px; margin-top: 10px">
                      已导入（归一化字符数：{{ ocrState.importedSize || 'ok' }}）
                    </div>

                    <textarea
                      v-if="ocrState.preview"
                      v-model="ocrState.preview"
                      readonly
                      class="importTextarea"
                    />
                  </div>
                </n-tab-pane>

                <n-tab-pane name="paste" tab="粘贴">
                  <div class="importPanel">
                    <n-form ref="pasteFormRef" :model="pasteState" :rules="pasteRules">
                      <n-form-item path="text" label="聊天文本">
                        <textarea
                          v-model="pasteState.text"
                          class="importTextarea"
                          placeholder="把聊天内容粘贴进来即可。若你拿到的是截图转文字（OCR），也可以直接贴。"
                        />
                      </n-form-item>
                    </n-form>

                    <div class="row" style="margin-top: 10px">
                      <n-button
                        type="primary"
                        :disabled="uiBusy || !pasteState.text.trim() || !canMutateWithCredits"
                        :loading="loading && !reportGenerating"
                        @click="onImportPaste"
                      >
                        粘贴并归一化
                      </n-button>
                      <div class="muted" v-if="pasteState.importedSize" style="font-size: 12px">
                        已导入（归一化字符数：{{ pasteState.importedSize || 'ok' }}）
                      </div>
                    </div>
                  </div>
                </n-tab-pane>
              </n-tabs>
            </div>

            <label style="margin-top: 14px">生成温度（可选）</label>
            <n-input-number v-model:value="form.temperature" :min="0" :max="1.5" :step="0.1" style="width: 100%" />

            <label style="margin-top: 14px">深度推理（可选）</label>
            <div class="row" style="margin-top: 6px; align-items: center; gap: 12px">
              <n-switch v-model:value="form.deepReasoning" :disabled="uiBusy" />
              <span class="muted" style="font-size: 12px; line-height: 1.5">
                第二段调用 {{ analyzeFeatures?.reasoner_model || 'deepseek-reasoner' }} 对整稿再审，强化冲突调解与不确定性。
                <template v-if="entitlements?.entitlements_enforced">
                  <template v-if="form.deepReasoning">
                    本次将扣 <b>{{ creditsNeededForAnalyze }}</b> 次（含深度附加 {{ deepExtraCredits }}）。
                  </template>
                  <template v-else>本次将扣 <b>1</b> 次。</template>
                </template>
              </span>
            </div>

            <div v-if="analyzePlan" class="planCard">
              <div class="planTitle">调度预检</div>
              <div class="planSteps">
                <span v-for="s in analyzePlan.pipeline_steps" :key="s" class="planStepChip">
                  {{ pipelineStepLabels[s] || s }}
                </span>
              </div>
              <div class="muted tiny" style="margin-top: 6px">
                本次预计消耗：<b>{{ analyzePlan.required_credits }}</b> 次
                <template v-if="analyzePlan.deep_reasoning_enabled">
                  （含深度附加 {{ analyzePlan.deep_reason_extra_credits }}）
                </template>
              </div>
              <div v-if="analyzePlan.blockers.length" class="planBlockers">
                <div v-for="b in analyzePlan.blockers" :key="b" class="planBlockerItem">- {{ b }}</div>
              </div>
            </div>

            <div style="height: 10px"></div>
            <n-button
              :disabled="uiBusy || !canAnalyze"
              type="primary"
              :loading="reportGenerating"
              style="width: 100%"
              @click="onAnalyze"
            >
              {{ reportGenerating ? '正在生成…' : '调用 DeepSeek 生成报告' }}
            </n-button>
          </div>

          <div v-else class="muted">
            请选择或新建一个档案。
          </div>

          <div v-if="error" style="color: #b00020; font-weight: 700; margin-top: 12px">
            {{ error }}
          </div>

          <div
            v-if="analysisWarn"
            style="color: #856404; background: rgba(255, 193, 7, 0.12); padding: 10px 12px; border-radius: 10px; margin-top: 12px; font-size: 13px; line-height: 1.5"
          >
            {{ analysisWarn }}
          </div>

          <div v-if="friendlySummary" class="friendlyCard">
            <div class="friendlyHead">
              <div class="friendlyTitle">给你的直观结论</div>
              <div class="friendlyScore">{{ friendlySummary.score ?? '--' }}</div>
            </div>
            <div class="friendlyBand">{{ friendlySummary.headline || '样本不足' }}</div>
            <div class="muted" style="margin-top: 6px">{{ friendlySummary.easy_summary || '' }}</div>
            <div v-if="Array.isArray(friendlySummary.top_reasons) && friendlySummary.top_reasons.length" class="friendlyReasons">
              <div class="small">主要依据</div>
              <div v-for="r in friendlySummary.top_reasons" :key="`${r.skill_id}-${r.skill_name}`" class="friendlyReasonItem">
                - {{ r.skill_name }}（{{ r.score }}）
              </div>
            </div>
            <div v-if="Array.isArray(friendlySummary.risk_flags) && friendlySummary.risk_flags.length" class="friendlyRisk">
              风险提示：{{ friendlySummary.risk_flags.join('、') }}
            </div>
            <div class="friendlyAction">
              <div><b>下一步：</b>{{ friendlySummary.next_step || '先低压力沟通，再观察是否有稳定回应。' }}</div>
              <div style="margin-top: 4px"><b>何时停：</b>{{ friendlySummary.stop_rule || '连续被回避时先暂停投入，优先照顾自己。' }}</div>
            </div>
          </div>

          <div v-if="scoringResult" class="scoreBrief">
            <span>置信度：{{ scoringResult.confidence || 'low' }}</span>
            <span> · </span>
            <span>等级：{{ scoringResult.level || '样本不足' }}</span>
          </div>

          <div v-if="analysisTrace.length" class="traceCard">
            <div class="traceTitle">本次调度轨迹</div>
            <div v-for="(t, idx) in analysisTrace" :key="`${t.step}-${idx}`" class="traceItem">
              <div>
                <b>{{ pipelineStepLabels[t.step] || t.step }}</b>
                <span class="muted tiny" style="margin-left: 8px">{{ traceStatusLabels[t.status] || t.status }}</span>
                <span v-if="t.model" class="muted tiny" style="margin-left: 8px">{{ t.model }}</span>
              </div>
              <div v-if="t.error" class="traceError">{{ t.error }}</div>
            </div>
          </div>

          <div style="height: 14px"></div>

          <div class="reportInlineHead">
            <label>治愈报告（人话摘要 + 心动指数 + 专业分析）</label>
            <n-button
              v-if="detail?.report?.report_markdown"
              text
              type="primary"
              size="small"
              @click="openReportFullscreen"
            >
              全屏查看
            </n-button>
          </div>
          <div v-if="detail?.report?.report_markdown" style="margin-top: 10px">
            <ReportView :markdown="detail.report.report_markdown" layout="default" />
          </div>
          <div v-else class="muted" style="margin-top: 10px">
            生成后会先给你「一眼看懂」和心动指数，再附专业分析。你可以先把自己从“非要有答案”的压力里放出来。
          </div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="reportFullscreen && detail?.report?.report_markdown"
        class="reportFullscreenLayer dslm-print-root"
      >
        <header class="reportFsToolbar">
          <div class="reportFsTitle">治愈报告 · {{ active?.name || '未命名' }}</div>
          <div class="reportFsActions">
            <div class="pdfExportBtnWrap">
              <n-button quaternary :disabled="pdfExporting" class="pdfExportBtn" @click="exportReportPdf">
                导出 PDF
              </n-button>
              <div v-if="pdfExporting" class="pdfExportBtnSpinner" aria-hidden="true"></div>
            </div>
            <n-button type="primary" @click="exitReportFullscreen">返回 · 重测或换档案</n-button>
          </div>
        </header>
        <div class="reportFsScroll">
          <ReportView :markdown="detail.report.report_markdown" layout="fullscreen" />
        </div>
      </div>
    </Teleport>
    </template>
  </n-config-provider>
</template>

<style scoped>
.footerAdminLink {
  color: #c2185b;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.creditBlockHint {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: #8b2942;
  background: rgba(240, 98, 146, 0.12);
}
.entitlementsRedeemForm :deep(.n-form-item-feedback-wrapper) {
  min-height: 0;
}
.planCard {
  margin-top: 10px;
  border: 1px solid rgba(240, 98, 146, 0.24);
  border-radius: 10px;
  padding: 10px;
  background: rgba(240, 98, 146, 0.08);
}
.planTitle {
  font-weight: 700;
  font-size: 13px;
}
.planSteps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.planStepChip {
  font-size: 11px;
  border-radius: 999px;
  padding: 3px 8px;
  background: rgba(255, 255, 255, 0.7);
}
.planBlockers {
  margin-top: 8px;
  font-size: 12px;
  color: #8b2942;
}
.planBlockerItem + .planBlockerItem {
  margin-top: 4px;
}
.traceCard {
  margin-top: 12px;
  border-radius: 10px;
  padding: 10px 12px;
  background: rgba(33, 150, 243, 0.08);
}
.traceTitle {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 8px;
}
.traceItem + .traceItem {
  margin-top: 8px;
}
.traceError {
  margin-top: 4px;
  font-size: 12px;
  color: #9a2b2b;
  word-break: break-word;
}
.friendlyCard {
  margin-top: 12px;
  border: 1px solid rgba(255, 126, 95, 0.32);
  background: rgba(255, 126, 95, 0.1);
  border-radius: 12px;
  padding: 12px;
}
.friendlyHead {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.friendlyTitle {
  font-size: 14px;
  font-weight: 700;
}
.friendlyScore {
  min-width: 48px;
  text-align: center;
  border-radius: 999px;
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.85);
  font-weight: 700;
}
.friendlyBand {
  margin-top: 6px;
  font-weight: 600;
  color: #7d2d1b;
}
.friendlyReasons {
  margin-top: 8px;
}
.friendlyReasonItem {
  font-size: 12px;
  line-height: 1.6;
}
.friendlyRisk {
  margin-top: 8px;
  font-size: 12px;
  color: #9a2b2b;
}
.friendlyAction {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
}
.scoreBrief {
  margin-top: 8px;
  font-size: 12px;
  color: #6c6c6c;
}
</style>
