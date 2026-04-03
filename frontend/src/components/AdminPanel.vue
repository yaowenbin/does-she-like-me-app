<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import type { DataTableColumns } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'
import {
  NButton,
  NCard,
  NCollapse,
  NCollapseItem,
  NConfigProvider,
  NDataTable,
  NInput,
  NInputNumber,
  NModal,
  NPopconfirm,
  NSelect,
  NSpace,
  NSpin,
  NStatistic,
  NTag,
  darkTheme,
} from 'naive-ui'
import {
  adminCreateGiftCodes,
  adminListGiftCodes,
  adminRevokeGiftCodes,
  type AdminGiftCodeRow,
  type GiftCodeStatus,
} from '../api'
import { toast } from '../http'

const emit = defineEmits<{ exit: [] }>()

/** ui-ux-pro-max: OLED 暗色 + 品牌粉 accent，数据台可读性优先 */
const adminThemeOverrides: GlobalThemeOverrides = {
  common: {
    fontFamily: '"DM Sans", system-ui, -apple-system, Segoe UI, sans-serif',
    fontFamilyMono: '"JetBrains Mono", ui-monospace, monospace',
    primaryColor: '#f472b6',
    primaryColorHover: '#f9a8d4',
    primaryColorPressed: '#ec4899',
    primaryColorSuppl: '#fbcfe8',
    borderRadius: '12px',
    borderRadiusSmall: '8px',
    bodyColor: '#06070b',
    cardColor: '#0c0e14',
    modalColor: '#101218',
    popoverColor: '#101218',
    tableColor: '#0a0c12',
    inputColor: '#101218',
    hoverColor: 'rgba(244, 114, 182, 0.085)',
  },
  Card: {
    color: 'rgba(12, 14, 20, 0.82)',
    borderColor: 'rgba(148, 163, 184, 0.11)',
    titleFontSize: '16px',
    titleFontWeight: '600',
  },
  DataTable: {
    thColor: 'rgba(8, 10, 16, 0.98)',
    tdColor: 'transparent',
    thTextColor: 'rgba(226, 232, 240, 0.95)',
    tdTextColor: 'rgba(226, 232, 240, 0.9)',
    borderColor: 'rgba(51, 65, 85, 0.4)',
    tdColorHover: 'rgba(244, 114, 182, 0.04)',
  },
  Input: {
    borderHover: '1px solid rgba(244, 114, 182, 0.35)',
    borderFocus: '1px solid rgba(244, 114, 182, 0.5)',
    boxShadowFocus: '0 0 0 2px rgba(244, 114, 182, 0.2)',
  },
  Collapse: {
    dividerColor: 'rgba(148, 163, 184, 0.12)',
  },
}

const tokenDraft = ref('')
/** 首屏：已有 session 时静默拉列表，勿与登录按钮共用 loading */
const sessionChecking = ref(false)
/** 仅「验证并进入」按钮 */
const loginSubmitting = ref(false)
/** 已登录后的列表刷新 / 生成 / 导入 / 废除 */
const pageLoading = ref(false)

const rows = ref<AdminGiftCodeRow[]>([])
const authed = ref(false)

const checkedRowKeys = ref<string[]>([])
const statusFilter = ref<'all' | GiftCodeStatus>('all')
const searchQuery = ref('')

const genCount = ref(50)
const genCredits = ref(5)
const genExpireDays = ref(7)
const genPrefix = ref('DSL')

const manualText = ref('')
const manualExpireDays = ref(7)

const showGenModal = ref(false)
const lastGenPlain = ref('')

const filteredRows = computed(() => {
  let list = rows.value
  if (statusFilter.value !== 'all') {
    list = list.filter((r) => r.status === statusFilter.value)
  }
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter(
      (r) =>
        r.code.toLowerCase().includes(q) ||
        (r.used_by_device && r.used_by_device.toLowerCase().includes(q))
    )
  }
  return list
})

const stats = computed(() => {
  const s = { unused: 0, used: 0, expired: 0, revoked: 0 }
  for (const r of rows.value) {
    if (r.status in s) s[r.status as keyof typeof s]++
  }
  return s
})

const totalCodes = computed(() => rows.value.length)

const creditsInUnused = computed(() =>
  rows.value.filter((r) => r.status === 'unused').reduce((sum, r) => sum + r.credits, 0)
)

/** 微型说明：基于当前全库实时聚合（无历史接口时用作「贵」一点的仪表文案） */
const statMicro = computed(() => {
  const t = totalCodes.value
  const pct = (n: number) => (t > 0 ? Math.round((n / t) * 100) : 0)
  const u = stats.value.unused
  const d = stats.value.used
  const e = stats.value.expired
  const r = stats.value.revoked
  if (!t) {
    return {
      unused: '全库暂无数据 · 生成首批卡密',
      used: '—',
      expired: '—',
      revoked: '—',
    }
  }
  return {
    unused: `占全库 ${pct(u)}% · 未核销额度约 ${creditsInUnused.value} 次`,
    used: `累计 ${d} 条 · 占全库 ${pct(d)}%`,
    expired: `占全库 ${pct(e)}% · 建议定期导出或废除`,
    revoked: `占全库 ${pct(r)}% · 泄漏止损记录`,
  }
})

watch([statusFilter, searchQuery], () => {
  checkedRowKeys.value = checkedRowKeys.value.filter((k) => filteredRows.value.some((r) => r.code === k))
})

function statusLabel(s: GiftCodeStatus): string {
  const m: Record<GiftCodeStatus, string> = {
    unused: '未使用',
    used: '已兑换',
    expired: '已过期',
    revoked: '已废除',
  }
  return m[s] || s
}

function statusTagType(s: GiftCodeStatus): 'success' | 'warning' | 'error' | 'default' {
  if (s === 'unused') return 'success'
  if (s === 'expired') return 'warning'
  if (s === 'revoked') return 'error'
  return 'default'
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { hour12: false })
}

function focusExpiredOnly() {
  statusFilter.value = 'expired'
  toast.info('已筛选「已过期」状态')
}

const statusFilterOptions = [
  { label: '全部状态', value: 'all' },
  { label: '未使用', value: 'unused' },
  { label: '已兑换', value: 'used' },
  { label: '已过期', value: 'expired' },
  { label: '已废除', value: 'revoked' },
]

const columns: DataTableColumns<AdminGiftCodeRow> = [
  { type: 'selection', fixed: 'left', width: 48 },
  {
    title: '卡密',
    key: 'code',
    width: 208,
    fixed: 'left',
    ellipsis: { tooltip: true },
    render(row) {
      return h('code', { class: 'monoCode' }, row.code)
    },
  },
  {
    title: '次数',
    key: 'credits',
    width: 72,
  },
  {
    title: '状态',
    key: 'status',
    width: 96,
    render(row) {
      return h(
        NTag,
        { type: statusTagType(row.status), size: 'small', bordered: false, round: true },
        { default: () => statusLabel(row.status) }
      )
    },
  },
  {
    title: '创建',
    key: 'created_at',
    width: 158,
    render(row) {
      return fmtTime(row.created_at)
    },
  },
  {
    title: '过期',
    key: 'expires_at',
    width: 158,
    render(row) {
      return row.expires_at ? fmtTime(row.expires_at) : '—'
    },
  },
  {
    title: '兑换时间',
    key: 'used_at',
    width: 158,
    render(row) {
      return fmtTime(row.used_at)
    },
  },
  {
    title: '兑换设备',
    key: 'used_by_device',
    ellipsis: { tooltip: true },
  },
]

async function pullGiftCodeRows(): Promise<boolean> {
  try {
    rows.value = await adminListGiftCodes()
    authed.value = true
    checkedRowKeys.value = []
    return true
  } catch {
    sessionStorage.removeItem('dslm_admin_token')
    authed.value = false
    rows.value = []
    return false
  }
}

async function loadList() {
  pageLoading.value = true
  try {
    await pullGiftCodeRows()
  } finally {
    pageLoading.value = false
  }
}

async function login() {
  const t = tokenDraft.value.trim()
  if (t.length < 8) {
    toast.warning('请输入管理密钥（至少 8 位，不含首尾空格）')
    return
  }
  if (loginSubmitting.value || sessionChecking.value) return
  loginSubmitting.value = true
  sessionStorage.setItem('dslm_admin_token', t)
  try {
    const ok = await pullGiftCodeRows()
    if (ok) tokenDraft.value = ''
  } finally {
    loginSubmitting.value = false
  }
}

function logout() {
  sessionStorage.removeItem('dslm_admin_token')
  authed.value = false
  rows.value = []
  tokenDraft.value = ''
  checkedRowKeys.value = []
}

function backToApp() {
  logout()
  window.location.hash = ''
  emit('exit')
}

function escapeCsvCell(v: string): string {
  if (/[",\n\r]/.test(v)) return `"${v.replace(/"/g, '""')}"`
  return v
}

function rowsToCsv(list: AdminGiftCodeRow[]): string {
  const header = 'code,credits,status,created_at,expires_at,used_at,revoked_at,used_by_device'
  const lines = list.map((r) =>
    [
      r.code,
      String(r.credits),
      statusLabel(r.status),
      r.created_at ?? '',
      r.expires_at ?? '',
      r.used_at ?? '',
      r.revoked_at ?? '',
      r.used_by_device ?? '',
    ]
      .map((x) => escapeCsvCell(x))
      .join(',')
  )
  return [header, ...lines].join('\r\n')
}

function downloadText(filename: string, text: string, mime: string) {
  const blob = new Blob([text], { type: mime })
  const u = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = u
  a.download = filename
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(u)
}

function exportCsv(list: AdminGiftCodeRow[], name: string) {
  if (!list.length) {
    toast.warning('没有可导出的行')
    return
  }
  const raw = rowsToCsv(list)
  const withBom = `\uFEFF${raw}`
  downloadText(name, withBom, 'text/csv;charset=utf-8')
  toast.success(`已导出 ${list.length} 条`)
}

function exportSelected() {
  const set = new Set(checkedRowKeys.value)
  const list = filteredRows.value.filter((r) => set.has(r.code))
  exportCsv(list, `gift-codes-selected-${Date.now()}.csv`)
}

function exportFiltered() {
  exportCsv(filteredRows.value, `gift-codes-filtered-${Date.now()}.csv`)
}

async function onGenerate() {
  const count = Math.min(5000, Math.max(1, Math.floor(Number(genCount.value) || 0)))
  pageLoading.value = true
  try {
    const r = await adminCreateGiftCodes({
      generate: {
        count,
        credits: Math.max(1, Math.floor(Number(genCredits.value) || 1)),
        expires_in_days: Math.max(1, Math.floor(Number(genExpireDays.value) || 7)),
        prefix: genPrefix.value.trim(),
      },
    })
    if (r.generated_plaintext) {
      lastGenPlain.value = r.generated_plaintext
      showGenModal.value = true
    }
    const skip = r.skipped_invalid ? `，跳过 ${r.skipped_invalid}` : ''
    toast.success(`已随机入库 ${r.created} 条${skip}`)
    await pullGiftCodeRows()
  } finally {
    pageLoading.value = false
  }
}

function parseManual(s: string): { code: string; credits: number }[] {
  const items: { code: string; credits: number }[] = []
  for (const line of s.split(/\r?\n/)) {
    const t = line.trim()
    if (!t || t.startsWith('#')) continue
    const parts = t.split(/[,，\t]/)
    const code = (parts[0] || '').trim()
    const credits = Number((parts[1] || '1').trim()) || 1
    if (code.length >= 4) items.push({ code, credits })
  }
  return items
}

async function onManualImport() {
  const items = parseManual(manualText.value)
  if (!items.length) {
    toast.warning('没有有效行。每行：卡密,次数（次数可省略，默认 1）')
    return
  }
  pageLoading.value = true
  try {
    const r = await adminCreateGiftCodes({
      items,
      manual_expires_in_days: Math.max(1, Math.floor(Number(manualExpireDays.value) || 7)),
    })
    toast.success(`手工入库成功 ${r.created} 条，跳过/重复 ${r.skipped_invalid} 条`)
    manualText.value = ''
    await pullGiftCodeRows()
  } finally {
    pageLoading.value = false
  }
}

async function onRevokeSelected() {
  const codes = [...checkedRowKeys.value]
  if (!codes.length) {
    toast.warning('请先勾选要废除的卡密')
    return
  }
  pageLoading.value = true
  try {
    const r = await adminRevokeGiftCodes(codes)
    toast.success(`已废除 ${r.revoked} 条（仅未兑换且未作废的会生效）`)
    checkedRowKeys.value = []
    await pullGiftCodeRows()
  } finally {
    pageLoading.value = false
  }
}

function copyLastGen() {
  if (!lastGenPlain.value) return
  navigator.clipboard.writeText(lastGenPlain.value).then(
    () => toast.success('已复制到剪贴板'),
    () => toast.warning('复制失败，请手动全选复制')
  )
}

onMounted(async () => {
  const tok = sessionStorage.getItem('dslm_admin_token')?.trim()
  if (!tok) return
  if (tok.length < 8) {
    sessionStorage.removeItem('dslm_admin_token')
    return
  }
  sessionChecking.value = true
  try {
    await pullGiftCodeRows()
  } finally {
    sessionChecking.value = false
  }
})
</script>

<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="adminThemeOverrides">
    <div class="adminShell">
      <div class="adminMesh" aria-hidden="true" />
      <div class="adminNoise" aria-hidden="true" />

      <div class="adminLayout">
        <!-- 顶栏：悬浮留白 + 毛玻璃（ui-ux-pro-max：不要紧贴视口边缘） -->
        <header class="adminNav">
          <div class="adminNavInner">
            <div class="adminBrand">
              <p class="adminEyebrow">Gift codes · Admin</p>
              <h1 class="adminTitle">卡密运营中心</h1>
              <p class="adminSubtitle">
                批量随机入库、状态与过期可视、泄漏一键废除、CSV
                导出；电商自动发卡可在后续对接同一数据源。
              </p>
            </div>
            <n-space align="center" :size="10" class="adminNavActions">
              <template v-if="authed">
                <n-button tertiary class="navBtn" :loading="pageLoading" @click="loadList">
                  <template #icon>
                    <svg class="ico" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path
                        d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                        stroke="currentColor"
                        stroke-width="1.75"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </template>
                  刷新列表
                </n-button>
                <n-button tertiary class="navBtn" @click="focusExpiredOnly">
                  <template #icon>
                    <svg class="ico" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path
                        d="M12 6v6l3 2m6-2a9 9 0 11-18 0 9 9 0 0118 0z"
                        stroke="currentColor"
                        stroke-width="1.75"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </template>
                  过期一览
                </n-button>
                <n-button quaternary round class="navBtnGhost" @click="logout">
                  <template #icon>
                    <svg class="ico" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <path
                        d="M12 3l7 4v5c0 5-3 9-7 10-4-1-7-5-7-10V7l7-4z"
                        stroke="currentColor"
                        stroke-width="1.5"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </template>
                  清除密钥
                </n-button>
              </template>
              <n-button type="primary" round strong class="navBtnPrimary" @click="backToApp">返回主站</n-button>
            </n-space>
          </div>
        </header>

        <p v-if="!authed && !sessionChecking" class="adminHint">
          管理密钥仅存于本标签页的 <code>sessionStorage</code>。请在 HTTPS
          下操作；勿在不可信环境截屏或停留会话。
        </p>

        <div v-if="sessionChecking" class="sessionBoot" role="status" aria-live="polite" aria-busy="true">
          <n-spin size="large" class="sessionBootSpin" />
          <p class="sessionBootText">正在验证已保存的会话…</p>
        </div>

        <n-card v-else-if="!authed" class="loginCard">
          <div class="loginCardInner">
            <div class="loginBadge" aria-hidden="true">
              <svg viewBox="0 0 24 24" class="loginBadgeSvg" fill="none">
                <path
                  d="M12 3l7 4v5c0 5-3 9-7 10-4-1-7-5-7-10V7l7-4z"
                  stroke="currentColor"
                  stroke-width="1.5"
                  stroke-linejoin="round"
                />
                <path
                  d="M9 12l2 2 4-4"
                  stroke="currentColor"
                  stroke-width="1.75"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </div>
            <h2 class="loginTitle">安全登录</h2>
            <p class="loginDesc">与服务端 <code>ADMIN_API_TOKEN</code> 一致的 Bearer 密钥</p>
            <n-space vertical size="large" style="width: 100%; margin-top: 8px">
              <n-input
                v-model:value="tokenDraft"
                type="password"
                show-password-on="click"
                size="large"
                placeholder="输入管理密钥"
                @keydown.enter.prevent="login"
              />
              <n-button
                type="primary"
                size="large"
                block
                strong
                :loading="loginSubmitting"
                :disabled="loginSubmitting || sessionChecking"
                @click="login"
              >
                验证并进入
              </n-button>
            </n-space>
          </div>
        </n-card>

        <template v-else>
          <!-- 指标 Bento -->
          <div class="statsBento">
            <div class="statTile statTile--ok">
              <div class="statTileTop">
                <span class="statTileLabel">未使用</span>
                <svg class="statMiniIco" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path
                    d="M20 7l-8 4-8-4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m-4 5v10l8 4"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </div>
              <n-statistic tabular-nums :value="stats.unused" class="statTileNum" />
              <p class="statTileTrend">{{ statMicro.unused }}</p>
            </div>
            <div class="statTile">
              <div class="statTileTop">
                <span class="statTileLabel">已兑换</span>
                <svg class="statMiniIco" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path
                    d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </div>
              <n-statistic tabular-nums :value="stats.used" class="statTileNum" />
              <p class="statTileTrend">{{ statMicro.used }}</p>
            </div>
            <div class="statTile statTile--warn">
              <div class="statTileTop">
                <span class="statTileLabel">已过期</span>
                <svg class="statMiniIco" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path
                    d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </div>
              <n-statistic tabular-nums :value="stats.expired" class="statTileNum" />
              <p class="statTileTrend">{{ statMicro.expired }}</p>
            </div>
            <div class="statTile statTile--danger">
              <div class="statTileTop">
                <span class="statTileLabel">已废除</span>
                <svg class="statMiniIco" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path
                    d="M18.364 18.364L5.636 5.636m12.728 0L5.636 18.364"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linecap="round"
                  />
                </svg>
              </div>
              <n-statistic tabular-nums :value="stats.revoked" class="statTileNum" />
              <p class="statTileTrend">{{ statMicro.revoked }}</p>
            </div>
          </div>

          <n-card class="sectionCard sectionCard--accent">
            <template #header>
              <div class="sectionHead">
                <span class="adminEyebrow adminEyebrow--onCard">Generate</span>
                <span class="sectionHeadTitle">
                  <svg class="icoTitle" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path
                      d="M12 2v3m0 14v3M4.5 4.5l2.1 2.1m10.8 10.8l2.1 2.1M2 12h3m14 0h3M4.5 19.5l2.1-2.1m10.8-10.8l2.1-2.1"
                      stroke="currentColor"
                      stroke-width="1.75"
                      stroke-linecap="round"
                    />
                  </svg>
                  随机批量生成
                </span>
              </div>
            </template>
            <div class="genGrid">
              <div class="genField">
                <label class="genLabel">生成数量</label>
                <n-input-number v-model:value="genCount" :min="1" :max="5000" :step="10" class="genInput" />
              </div>
              <div class="genField">
                <label class="genLabel">每张次数</label>
                <n-input-number v-model:value="genCredits" :min="1" :max="9999" class="genInput" />
              </div>
              <div class="genField">
                <label class="genLabel">有效天数</label>
                <n-input-number v-model:value="genExpireDays" :min="1" :max="365" class="genInput" />
              </div>
              <div class="genField genFieldWide">
                <label class="genLabel">前缀</label>
                <n-input v-model:value="genPrefix" placeholder="如 DSL，留空则纯随机" clearable />
              </div>
            </div>
            <p class="fieldHint">
              高熵随机码；过期后不可兑换。生成完成会弹出明文窗口，请立即转存或导出 CSV。
            </p>
            <div class="sectionFooter">
              <n-button
                type="primary"
                strong
                round
                :loading="pageLoading"
                :disabled="pageLoading"
                @click="onGenerate"
              >
                <template #icon>
                  <svg class="ico" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path
                      d="M12 2v3m0 14v3M4.5 4.5l2.1 2.1m10.8 10.8l2.1 2.1M2 12h3m14 0h3M4.5 19.5l2.1-2.1m10.8-10.8l2.1-2.1"
                      stroke="currentColor"
                      stroke-width="1.75"
                      stroke-linecap="round"
                    />
                  </svg>
                </template>
                随机生成并入库
              </n-button>
            </div>
          </n-card>

          <n-collapse class="manualCollapse" arrow-placement="right" display-directive="show">
            <n-collapse-item name="manual" title="手工录入（备选）">
              <div class="manualExpire">
                <label class="genLabel">手工行统一有效期</label>
                <n-input-number v-model:value="manualExpireDays" :min="1" :max="365" />
                <span class="unitHint">天</span>
              </div>
              <textarea v-model="manualText" class="manualArea" placeholder="每行：卡密,次数&#10;# 以 # 开头的行为注释" />
              <n-button secondary strong round :loading="pageLoading" @click="onManualImport">
                导入手工列表
              </n-button>
            </n-collapse-item>
          </n-collapse>

          <n-card class="sectionCard tableSection">
            <template #header>
              <div class="sectionHead">
                <span class="adminEyebrow adminEyebrow--onCard">Inventory</span>
                <span class="sectionHeadTitle">卡密明细</span>
              </div>
            </template>

            <div class="tableToolbar">
              <n-select
                v-model:value="statusFilter"
                :options="statusFilterOptions"
                placeholder="状态"
                filterable
                size="medium"
                class="toolbarSelect"
              />
              <n-input
                v-model:value="searchQuery"
                size="medium"
                placeholder="搜索卡密或设备片段…"
                clearable
                class="toolbarSearch"
              />
              <div class="toolbarSpacer" />
              <n-button quaternary size="medium" :disabled="!checkedRowKeys.length" @click="exportSelected">
                导出所选 CSV
              </n-button>
              <n-button quaternary size="medium" @click="exportFiltered">导出当前筛选</n-button>
              <n-popconfirm @positive-click="onRevokeSelected">
                <template #trigger>
                  <n-button
                    type="error"
                    secondary
                    strong
                    round
                    size="medium"
                    :disabled="!checkedRowKeys.length || pageLoading"
                  >
                    废除勾选
                  </n-button>
                </template>
                将勾选中「未兑换」的卡密标记为废除（已兑换不受影响）。用于泄漏止损。
              </n-popconfirm>
            </div>

            <div class="tableViewport">
              <n-data-table
                v-model:checked-row-keys="checkedRowKeys"
                :columns="columns"
                :data="filteredRows"
                :loading="pageLoading"
                :row-key="(r: AdminGiftCodeRow) => r.code"
                :scroll-x="1280"
                size="small"
                class="giftTable"
                :single-line="false"
                striped
                :pagination="{ pageSize: 15, showSizePicker: true, pageSizes: [15, 30, 50] }"
              />
            </div>
          </n-card>
        </template>
      </div>

      <n-modal
        v-model:show="showGenModal"
        preset="card"
        :segmented="{ content: true, footer: 'soft' }"
        title="刚生成的卡密"
        class="genModalWrap"
        style="width: min(720px, 94vw)"
      >
        <p class="modalHint">
          以下明文建议立即复制或导出；关闭弹窗后可在表格中按条件筛选并导出 CSV。
        </p>
        <textarea :value="lastGenPlain" readonly class="genModalArea" />
        <template #footer>
          <n-space justify="end" :size="12">
            <n-button quaternary @click="showGenModal = false">关闭</n-button>
            <n-button type="primary" strong round @click="copyLastGen">复制全部</n-button>
          </n-space>
        </template>
      </n-modal>
    </div>
  </n-config-provider>
</template>

<style scoped>
.ico {
  width: 1.1em;
  height: 1.1em;
  flex-shrink: 0;
}

.adminShell {
  position: relative;
  min-height: 100vh;
  color: #e2e8f0;
  padding: 1.25rem 1rem 4rem;
}

@media (min-width: 768px) {
  .adminShell {
    padding: 1.5rem 1.75rem 4.5rem;
  }
}

.adminMesh {
  pointer-events: none;
  position: fixed;
  inset: 0;
  z-index: 0;
  background:
    radial-gradient(1200px 600px at 80% -10%, rgba(244, 114, 182, 0.14), transparent 55%),
    radial-gradient(900px 500px at 10% 20%, rgba(99, 102, 241, 0.12), transparent 50%),
    linear-gradient(180deg, #05060a 0%, #080a11 45%, #05060a 100%);
}

.adminNoise {
  pointer-events: none;
  position: fixed;
  inset: 0;
  z-index: 0;
  opacity: 0.035;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}

.adminLayout {
  position: relative;
  z-index: 1;
  max-width: 1280px;
  margin: 0 auto;
  width: 100%;
}

.adminNav {
  position: sticky;
  top: 1rem;
  z-index: 20;
  margin-bottom: 1.75rem;
}

.adminNavInner {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.25rem;
  padding: 1.1rem 1.25rem;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(10, 12, 18, 0.72);
  backdrop-filter: blur(18px) saturate(1.2);
  -webkit-backdrop-filter: blur(18px) saturate(1.2);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.04) inset,
    0 24px 48px rgba(0, 0, 0, 0.35);
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

@media (prefers-reduced-motion: reduce) {
  .adminNavInner,
  .statTile,
  .sectionCard {
    transition: none;
  }
}

.adminNavInner:hover {
  border-color: rgba(244, 114, 182, 0.2);
}

.adminEyebrow {
  margin: 0 0 0.35rem;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgba(244, 114, 182, 0.85);
}

.adminEyebrow--onCard {
  color: rgba(244, 114, 182, 0.75);
}

.adminTitle {
  margin: 0;
  font-size: clamp(1.45rem, 3vw, 1.85rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
  color: #f8fafc;
}

.adminSubtitle {
  margin: 0.5rem 0 0;
  max-width: 36rem;
  font-size: 13px;
  line-height: 1.55;
  color: rgba(148, 163, 184, 0.92);
}

.adminNavActions :deep(.n-button) {
  cursor: pointer;
}

.navBtnPrimary {
  box-shadow: 0 4px 20px rgba(244, 114, 182, 0.25);
}

.adminHint {
  margin: 0 0 1.25rem;
  font-size: 13px;
  line-height: 1.55;
  color: rgba(148, 163, 184, 0.95);
}

.adminHint code {
  padding: 0.1rem 0.35rem;
  border-radius: 6px;
  background: rgba(244, 114, 182, 0.1);
  font-family: var(--n-font-family-mono);
  font-size: 12px;
  color: #fbcfe8;
}

.sessionBoot {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  min-height: 42vh;
  padding: 2.5rem 1rem;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.1);
  background: rgba(8, 10, 14, 0.5);
}

.sessionBootText {
  margin: 0;
  font-size: 14px;
  color: rgba(148, 163, 184, 0.95);
}

.sessionBootSpin :deep(.n-spin-body) {
  color: #f472b6;
}

.loginCard {
  max-width: 460px;
  margin: 0 auto;
  border-radius: 16px !important;
}

.loginCard :deep(.n-card__content) {
  padding: 0 !important;
}

.loginCardInner {
  padding: 1.75rem 1.5rem 2rem;
}

.loginBadge {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 1rem;
  background: linear-gradient(145deg, rgba(244, 114, 182, 0.2), rgba(99, 102, 241, 0.12));
  border: 1px solid rgba(244, 114, 182, 0.25);
  color: #f9a8d4;
}

.loginBadgeSvg {
  width: 26px;
  height: 26px;
}

.loginTitle {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 650;
  color: #f8fafc;
}

.loginDesc {
  margin: 0.35rem 0 0;
  font-size: 13px;
  color: rgba(148, 163, 184, 0.95);
}

.loginDesc code {
  font-family: var(--n-font-family-mono);
  font-size: 12px;
  color: #fbcfe8;
}

.statsBento {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 1.25rem;
}

@media (max-width: 960px) {
  .statsBento {
    grid-template-columns: repeat(2, 1fr);
  }
}

.statTile {
  cursor: default;
  padding: 1rem 1.1rem;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(12, 14, 22, 0.65);
  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    transform 0.2s ease;
}

.statTile:hover {
  border-color: rgba(244, 114, 182, 0.22);
  background: rgba(14, 16, 24, 0.78);
}

.statTile--ok {
  box-shadow: 0 0 0 1px rgba(52, 211, 153, 0.12);
}
.statTile--warn {
  box-shadow: 0 0 0 1px rgba(251, 191, 36, 0.12);
}
.statTile--danger {
  box-shadow: 0 0 0 1px rgba(248, 113, 113, 0.12);
}

.statTileTop {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.35rem;
}

.statTileLabel {
  font-size: 12px;
  font-weight: 600;
  color: rgba(148, 163, 184, 0.95);
}

.statMiniIco {
  width: 18px;
  height: 18px;
  color: rgba(148, 163, 184, 0.55);
}

.statTileNum :deep(.n-statistic-value) {
  font-size: 1.65rem !important;
  font-weight: 700 !important;
  color: #f8fafc !important;
  letter-spacing: -0.02em;
}

.statTileNum :deep(.n-statistic-label) {
  display: none;
}

.statTileTrend {
  margin: 0.45rem 0 0;
  font-size: 11px;
  line-height: 1.45;
  letter-spacing: 0.02em;
  color: rgba(148, 163, 184, 0.88);
}

.sectionCard {
  margin-bottom: 1.1rem;
  border-radius: 16px !important;
  overflow: hidden;
}

.sectionCard--accent {
  border: 1px solid rgba(244, 114, 182, 0.18) !important;
  background: linear-gradient(
    165deg,
    rgba(16, 18, 28, 0.88) 0%,
    rgba(12, 14, 22, 0.92) 100%
  ) !important;
}

.sectionHead {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.sectionHeadTitle {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 1.05rem;
  font-weight: 650;
  color: #f8fafc;
}

.icoTitle {
  width: 1.2em;
  height: 1.2em;
  flex-shrink: 0;
  color: #f472b6;
  opacity: 0.95;
}

.genGrid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem 1.25rem;
}

@media (max-width: 720px) {
  .genGrid {
    grid-template-columns: 1fr;
  }
}

.genFieldWide {
  grid-column: 1 / -1;
}

.genLabel {
  display: block;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 0.4rem;
  color: rgba(148, 163, 184, 0.98);
}

.genInput {
  width: 100%;
}

.fieldHint {
  margin: 0.75rem 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(100, 116, 139, 0.95);
}

.sectionFooter {
  margin-top: 1.25rem;
}

.manualCollapse {
  margin-bottom: 1.1rem;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.11);
  background: rgba(10, 12, 18, 0.55);
  overflow: hidden;
}

.manualCollapse :deep(.n-collapse-item__header) {
  padding: 14px 18px !important;
  font-weight: 600 !important;
}

.manualCollapse :deep(.n-collapse-item__content-inner) {
  padding: 0 18px 18px !important;
}

.manualExpire {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.unitHint {
  font-size: 13px;
  color: rgba(148, 163, 184, 0.85);
}

.manualArea {
  width: 100%;
  min-height: 130px;
  box-sizing: border-box;
  margin-bottom: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(51, 65, 85, 0.45);
  background: rgba(6, 8, 12, 0.65);
  color: #e2e8f0;
  font-family: var(--n-font-family-mono);
  font-size: 13px;
  line-height: 1.45;
  resize: vertical;
  transition: border-color 0.2s ease;
}

.manualArea:focus {
  outline: none;
  border-color: rgba(244, 114, 182, 0.45);
}

.tableSection {
  border-radius: 16px !important;
}

.tableToolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}

.toolbarSelect {
  width: 168px;
}

.toolbarSearch {
  width: min(260px, 100%);
}

.toolbarSpacer {
  flex: 1;
  min-width: 8px;
}

.tableViewport {
  width: 100%;
  border-radius: 12px;
  border: 1px solid rgba(51, 65, 85, 0.38);
  overflow: hidden;
  background: rgba(6, 8, 12, 0.35);
}

.giftTable {
  width: 100%;
}

.giftTable :deep(.monoCode) {
  font-family: var(--n-font-family-mono);
  font-size: 12px;
  font-weight: 500;
  color: #fbcfe8;
  letter-spacing: 0.02em;
}

.genModalWrap :deep(.n-card) {
  border-radius: 16px !important;
}

.genModalWrap :deep(.n-card-header) {
  font-weight: 650 !important;
}

.genModalArea {
  width: 100%;
  min-height: 220px;
  box-sizing: border-box;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid rgba(51, 65, 85, 0.45);
  background: #06070b;
  color: #e2e8f0;
  font-family: var(--n-font-family-mono);
  font-size: 12px;
  line-height: 1.55;
  resize: vertical;
}

.modalHint {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.55;
  color: rgba(148, 163, 184, 0.95);
}
</style>
