<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import {
  NButton,
  NConfigProvider,
  NInput,
  NInputNumber,
  NTabs,
  NTabPane,
  NSelect,
} from 'naive-ui'
import {
  analyzeArchive,
  createArchive,
  downloadReportPdf,
  getArchiveDetail,
  getEntitlementsMe,
  getWechatScene,
  importWxTxt,
  importPaste,
  importOcr,
  listArchives,
  redeemGiftCode,
  type ArchiveSummary,
  type EntitlementsMe,
} from './api'
import ReportView from './components/ReportView.vue'
import SakuraScene from './components/SakuraScene.vue'

const loading = ref(false)
/** 仅「生成报告」阶段的整页温馨 loading */
const reportGenerating = ref(false)
const error = ref<string | null>(null)
/** 报告全屏层：生成后自动打开，也可手动打开 */
const reportFullscreen = ref(false)

/** 设备维度次数 / 卡密 / 公众号引流 */
const entitlements = ref<EntitlementsMe | null>(null)
const redeemCodeInput = ref('')
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
})

const stageOptions = [
  { label: '不填', value: '' },
  { label: '初识', value: '初识' },
  { label: '暧昧', value: '暧昧' },
  { label: '已表白', value: '已表白' },
  { label: '冷淡期', value: '冷淡期' },
  { label: '其他', value: '其他' },
]

const scenarioOptions = [
  { label: '不填', value: '' },
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
  archives.value = await listArchives()
  localStorage.setItem('dslm_archives_cache_v1', JSON.stringify(archives.value))

  // activeId 优先回显；若不在列表中则回退到第一个
  if (activeId.value && !archives.value.some((a) => a.id === activeId.value)) activeId.value = ''
  if (!activeId.value && archives.value.length) activeId.value = archives.value[0].id
}

async function refreshDetail() {
  if (!activeId.value) {
    detail.value = null
    return
  }
  detail.value = await getArchiveDetail(activeId.value)
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
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

async function onImportWxTxt() {
  if (!activeId.value) return
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
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

async function onImportPaste() {
  if (!activeId.value) return
  if (!pasteState.text.trim()) {
    error.value = '请先粘贴聊天内容（可以是 OCR 后的文字）'
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
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

async function onImportOcr() {
  if (!activeId.value) return
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
    // OCR 导入成功后，后端会写入 uploaded 内容，因此分析按钮应可用
    await refreshDetail()
    importMode.value = 'ocr'
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

async function onAnalyze() {
  if (!activeId.value) return
  error.value = null
  loading.value = true
  reportGenerating.value = true
  startWarmMessages()
  try {
    const res = await analyzeArchive(activeId.value, { temperature: Number(form.temperature) })
    await refreshDetail()
    // detail 会刷新到最新 report
    detail.value = {
      ...(detail.value as any),
      report: {
        model: res.model,
        report_markdown: res.report_markdown,
        created_at: new Date().toISOString(),
      },
    }
    reportFullscreen.value = true
    await refreshEntitlements()
  } catch (e: any) {
    error.value = e?.message || String(e)
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
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    pdfExporting.value = false
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
  } catch {
    entitlements.value = null
  }
}

async function onRedeemCode() {
  error.value = null
  if (!redeemCodeInput.value.trim()) {
    error.value = '请输入卡密'
    return
  }
  try {
    await redeemGiftCode(redeemCodeInput.value.trim())
    redeemCodeInput.value = ''
    await refreshEntitlements()
  } catch (e: any) {
    error.value = e?.message || String(e)
  }
}

onUnmounted(() => stopWarmMessages())

onMounted(async () => {
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
    error.value = e?.message || String(e)
  }
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

const canAnalyze = computed(() => Boolean(detail.value?.archive?.has_upload))

watch(
  () => activeId.value,
  (id) => {
    if (id) localStorage.setItem('dslm_active_id_v1', id)
  }
)

watch(reportFullscreen, (v) => {
  document.body.style.overflow = v ? 'hidden' : ''
})
</script>

<template>
  <n-config-provider :theme-overrides="themeOverrides">
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

          <div class="formRow">
            <label>名称（可选）</label>
            <div class="formControl">
              <n-input v-model:value="form.name" placeholder="例如：2024 暧昧期" style="width: 100%" />
            </div>
          </div>

          <div class="formRow">
            <label>关系阶段（可选）</label>
            <div class="formControl">
              <n-select v-model:value="form.stage" :options="stageOptions" placeholder="请选择" style="width: 100%" />
            </div>
          </div>

          <div class="formRow">
            <label>聊天场景（可选）</label>
            <div class="formControl">
              <n-select
                v-model:value="form.scenario"
                :options="scenarioOptions"
                placeholder="请选择"
                style="width: 100%"
              />
            </div>
          </div>

          <div class="formRow">
            <label>自愿标签：星座</label>
            <div class="formControl">
              <n-select
                v-model:value="form.zodiac"
                :options="zodiacOptions"
                placeholder="例如：双子座"
                style="width: 100%"
                clearable
                filterable
                tag
                :onCreate="createTagOption"
              />
            </div>
          </div>

          <div class="formRow">
            <label>自愿标签：MBTI</label>
            <div class="formControl">
              <n-select
                v-model:value="form.mbti"
                :options="mbtiOptions"
                placeholder="例如：ENFP"
                style="width: 100%"
                clearable
                filterable
                tag
                :onCreate="createTagOption"
              />
            </div>
          </div>

          <div style="height: 10px"></div>
          <n-button :disabled="uiBusy" type="primary" :loading="loading && !reportGenerating" style="width: 100%" @click="onCreateArchive">
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
            <div class="entitlementsRow entitlementsActions">
              <n-input
                v-model:value="redeemCodeInput"
                size="small"
                placeholder="输入卡密，兑换次数"
                style="flex: 1; min-width: 120px; max-width: 220px"
                @keydown.enter.prevent="onRedeemCode"
              />
              <n-button size="small" type="primary" :disabled="uiBusy" @click="onRedeemCode">
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
                        :disabled="uiBusy || !txtState.files.length"
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
                        :disabled="uiBusy || ocrState.files.length === 0"
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
                    <label>如果无法导出：直接粘贴聊天文本（支持 Tencent 无导出情况）</label>
                    <textarea
                      v-model="pasteState.text"
                      class="importTextarea"
                      placeholder="把聊天内容粘贴进来即可。若你拿到的是截图转文字（OCR），也可以直接贴。"
                    />

                    <div class="row" style="margin-top: 10px">
                      <n-button
                        type="primary"
                        :disabled="uiBusy || !pasteState.text.trim()"
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
            <n-button quaternary :loading="pdfExporting" @click="exportReportPdf">导出 PDF</n-button>
            <n-button type="primary" @click="exitReportFullscreen">返回 · 重测或换档案</n-button>
          </div>
        </header>
        <div class="reportFsScroll">
          <ReportView :markdown="detail.report.report_markdown" layout="fullscreen" />
        </div>
      </div>
    </Teleport>
  </n-config-provider>
</template>

