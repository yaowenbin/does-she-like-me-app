<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NCard, NDataTable, NInput, NPopconfirm } from 'naive-ui'
import { toast } from '../../http'
import {
  adminGetTuningRows,
  adminResetDeviceTuning,
  adminUpsertDeviceTuning,
  type AdminTuningRows,
} from '../../api'

const loading = ref(false)
const deviceId = ref('')
const deltaInput = ref('S1=0.01\nS3=0.01\nS10=0.005')
const tuningRows = ref<AdminTuningRows | null>(null)

function parseDeltas(input: string): Record<string, number> {
  const out: Record<string, number> = {}
  for (const line of input.split(/\r?\n/)) {
    const t = line.trim()
    if (!t) continue
    const [k, v] = t.split('=')
    const sid = (k || '').trim().toUpperCase()
    const n = Number((v || '').trim())
    if (!/^S([1-9]|10)$/.test(sid)) continue
    if (!Number.isFinite(n)) continue
    out[sid] = n
  }
  return out
}

const tuningColumns = [
  { title: '设备', key: 'device_id' },
  { title: '技能', key: 'skill_id' },
  { title: 'Δ', key: 'delta' },
  { title: '更新时间', key: 'updated_at' },
]

async function refreshTuning() {
  loading.value = true
  try {
    tuningRows.value = await adminGetTuningRows(200)
  } finally {
    loading.value = false
  }
}

async function applyTuning() {
  if (deviceId.value.trim().length < 8) return toast.warning('请输入有效 device_id')
  const deltas = parseDeltas(deltaInput.value)
  if (!Object.keys(deltas).length) return toast.warning('请输入至少一条 Sx=数值')

  loading.value = true
  try {
    const r = await adminUpsertDeviceTuning(deviceId.value.trim(), deltas)
    toast.success(`已写入 ${r.affected} 条调优`)
    await refreshTuning()
  } finally {
    loading.value = false
  }
}

async function resetTuning() {
  if (deviceId.value.trim().length < 8) return toast.warning('请输入有效 device_id')
  loading.value = true
  try {
    const r = await adminResetDeviceTuning(deviceId.value.trim())
    toast.success(`已重置 ${r.affected} 条`)
    await refreshTuning()
  } finally {
    loading.value = false
  }
}

void refreshTuning()
</script>

<template>
  <div class="sectionWrap">
    <n-card class="sectionCard" title="调优配置">
      <n-card title="设备调优" class="innerCard">
        <div class="opsCol">
          <n-input v-model:value="deviceId" placeholder="device_id" />
          <n-input
            v-model:value="deltaInput"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 8 }"
          />
          <div class="opsRow">
            <n-button type="primary" :loading="loading" @click="applyTuning">写入调优</n-button>
            <n-popconfirm @positive-click="resetTuning">
              <template #trigger>
                <n-button type="error" secondary :loading="loading">重置设备调优</n-button>
              </template>
              确认重置该设备所有调优？
            </n-popconfirm>
          </div>
        </div>
      </n-card>

      <n-card title="最近调优明细" class="innerCard" style="margin-top: 12px">
        <n-data-table
          :columns="tuningColumns"
          :data="tuningRows?.rows || []"
          :loading="loading"
          :row-key="(r) => `${r.device_id}-${r.skill_id}-${r.updated_at}`"
          :pagination="{ pageSize: 15, showSizePicker: true, pageSizes: [15, 30, 50] }"
          size="small"
          striped
        />
      </n-card>
    </n-card>
  </div>
</template>

