<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  analyzeArchive,
  createArchive,
  getArchiveDetail,
  importWxTxt,
  importPaste,
  listArchives,
  type ArchiveSummary,
} from './api'
import ReportView from './components/ReportView.vue'

const loading = ref(false)
const error = ref<string | null>(null)

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

const fileState = reactive({
  file: null as File | null,
  imported: false,
  importedSize: 0,
})

const pasteState = reactive({
  text: '',
  importedSize: 0,
})

const active = computed(() => archives.value.find((a) => a.id === activeId.value))

function badgeFor(a: ArchiveSummary | undefined) {
  if (!a) return { text: '未选择', cls: '' }
  if (a.has_report) return { text: '已分析', cls: 'badgeOk' }
  if (a.has_upload) return { text: '已导入', cls: 'badgeWarn' }
  return { text: '待导入', cls: '' }
}

async function refreshArchives() {
  archives.value = await listArchives()
  if (!activeId.value && archives.value.length) activeId.value = archives.value[0].id
}

async function refreshDetail() {
  if (!activeId.value) {
    detail.value = null
    return
  }
  detail.value = await getArchiveDetail(activeId.value)
  fileState.imported = Boolean(detail.value.archive.has_upload)
  fileState.importedSize = 0
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
  if (!fileState.file) {
    error.value = '请先选择 txt 文件'
    return
  }
  error.value = null
  loading.value = true
  try {
    const res = await importWxTxt(activeId.value, fileState.file)
    fileState.imported = true
    fileState.importedSize = Number(res.normalized_size || 0)
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
    fileState.imported = true
    fileState.importedSize = Number(res.normalized_size || 0)
    pasteState.importedSize = fileState.importedSize
    await refreshDetail()
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
  } catch (e: any) {
    error.value = e?.message || String(e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    await refreshArchives()
    await refreshDetail()
  } catch (e: any) {
    error.value = e?.message || String(e)
  }
})

const badge = computed(() => badgeFor(active.value))
</script>

<template>
  <div class="container">
    <h1>她爱你嘛 · 管理页</h1>
    <div class="muted">
      作用：导入 wx 聊天 txt → 生成证据卡片与多透镜解读 → 调用 DeepSeek 返回报告（Markdown）。
      <br />
      提醒：请仅上传你有权使用的材料；不要用于骚扰或操控。
    </div>

    <div style="height: 14px"></div>

    <div class="grid">
      <div class="card">
        <h2>档案列表</h2>
        <div class="muted" style="margin-bottom: 10px">
          点击切换档案。未分析则先导入再分析。
        </div>
        <div
          v-for="a in archives"
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

        <div style="height: 10px"></div>
        <h2>新建档案</h2>
        <label>名称（可选）</label>
        <input v-model="form.name" placeholder="例如：2024 暧昧期" />

        <label>关系阶段（可选）</label>
        <input v-model="form.stage" placeholder="初识/暧昧/已表白/冷淡期/其他" />

        <label>聊天场景（可选）</label>
        <input v-model="form.scenario" placeholder="私聊/群聊/工作软件/其他" />

        <label>自愿标签：星座（可选，不必生日）</label>
        <input v-model="form.zodiac" placeholder="例如：双子座" />

        <label>自愿标签：MBTI（可选）</label>
        <input v-model="form.mbti" placeholder="例如：ENFP" />

        <div style="height: 10px"></div>
        <button :disabled="loading" @click="onCreateArchive">新建档案</button>
      </div>

      <div class="card">
        <h2>导入与分析</h2>

        <div style="margin-bottom: 10px" class="muted">
          当前档案：<b>{{ active?.name || '未命名' }}</b>（{{ badge.text }}）
        </div>

        <div v-if="activeId">
          <label>导入 wx 聊天 txt</label>
          <input
            type="file"
            accept=".txt,text/plain"
            @change="(e) => fileState.file = (e.target as HTMLInputElement).files?.[0] || null"
          />
          <div class="row" style="margin-top: 10px">
            <button :disabled="loading || !fileState.file" @click="onImportWxTxt">上传并归一化</button>
            <div class="muted" v-if="fileState.imported" style="font-size: 12px">
              已导入（归一化字符数：{{ fileState.importedSize || 'ok' }}）
            </div>
          </div>

          <div style="height: 16px"></div>

          <label>如果无法导出：直接粘贴聊天文本（支持 Tencent 无导出情况）</label>
          <textarea
            v-model="pasteState.text"
            placeholder="把聊天内容粘贴进来即可。若你拿到的是截图转文字（OCR），也可以直接贴。"
          />
          <div class="row" style="margin-top: 10px">
            <button :disabled="loading || !pasteState.text.trim()" @click="onImportPaste">粘贴并归一化</button>
            <div class="muted" v-if="pasteState.importedSize" style="font-size: 12px">
              已导入（归一化字符数：{{ pasteState.importedSize || 'ok' }}）
            </div>
          </div>

          <label style="margin-top: 14px">生成温度（可选）</label>
          <input
            type="number"
            step="0.1"
            min="0"
            max="1.5"
            v-model.number="form.temperature"
          />

          <div style="height: 10px"></div>
          <button :disabled="loading" @click="onAnalyze">调用 DeepSeek 生成报告</button>
        </div>

        <div style="height: 14px"></div>

        <div v-if="error" style="color: #b00020; font-weight: 700">{{ error }}</div>

        <div style="height: 14px"></div>

        <label>治愈报告（番剧字幕 + 气泡章节 + 可视化）</label>
        <div v-if="detail?.report?.report_markdown" style="margin-top: 10px">
          <ReportView :markdown="detail.report.report_markdown" />
        </div>
        <div v-else class="muted" style="margin-top: 10px">
          点击“调用 DeepSeek 生成报告”后，这里会出现治愈报告。你可以先把自己从“非要有答案”的压力里放出来。
        </div>
      </div>
    </div>
  </div>
</template>

