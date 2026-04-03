<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NCard, NDataTable, NInput, NInputNumber } from 'naive-ui'
import { toast } from '../../http'
import { adminCreateGiftCodes, adminListGiftCodes, type AdminGiftCodeRow } from '../../api'

const loading = ref(false)
const rows = ref<AdminGiftCodeRow[]>([])

const genCount = ref(20)
const genCredits = ref(5)
const genExpire = ref(30)
const genPrefix = ref('LOVE')
const generated = ref('')

const columns = [
  { title: '卡密', key: 'code' },
  { title: '额度', key: 'credits' },
  { title: '状态', key: 'status' },
  { title: '创建时间', key: 'created_at' },
  { title: '到期', key: 'expires_at' },
]

async function refreshCodes() {
  loading.value = true
  try {
    rows.value = await adminListGiftCodes()
  } finally {
    loading.value = false
  }
}

async function generateCodes() {
  loading.value = true
  try {
    const res = await adminCreateGiftCodes({
      generate: {
        count: Number(genCount.value || 20),
        credits: Number(genCredits.value || 5),
        expires_in_days: Number(genExpire.value || 30),
        prefix: genPrefix.value.trim() || 'LOVE',
      },
    })
    generated.value = res.generated_plaintext || ''
    toast.success(`已生成 ${res.created} 条`)
    await refreshCodes()
  } finally {
    loading.value = false
  }
}

void refreshCodes()
</script>

<template>
  <div class="sectionWrap">
    <n-card class="sectionCard" title="卡密运营">
      <div class="opsRow">
        <n-input-number v-model:value="genCount" :min="1" />
        <n-input-number v-model:value="genCredits" :min="1" />
        <n-input-number v-model:value="genExpire" :min="1" />
        <n-input v-model:value="genPrefix" placeholder="prefix" />
        <n-button :loading="loading" type="primary" @click="generateCodes">生成卡密</n-button>
      </div>

      <n-input
        v-model:value="generated"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="生成结果（明文会显示在这里）"
      />

      <n-data-table
        :columns="columns"
        :data="rows"
        :loading="loading"
        :row-key="(r) => r.code"
        :pagination="{ pageSize: 15, showSizePicker: true, pageSizes: [15, 30, 50] }"
        size="small"
        striped
        style="margin-top: 12px"
      />
    </n-card>
  </div>
</template>

