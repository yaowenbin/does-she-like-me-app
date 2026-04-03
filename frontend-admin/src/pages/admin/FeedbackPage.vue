<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NButton, NCard, NInputNumber, NStatistic, NTag } from 'naive-ui'
import { toast } from '../../http'
import { adminGetFeedbackStats, type AdminFeedbackStats } from '../../api'

const loading = ref(false)
const days = ref(30)
const stats = ref<AdminFeedbackStats | null>(null)

const accuracyPct = computed(() => Math.round((stats.value?.accuracy_rate || 0) * 100))

async function refreshAll() {
  loading.value = true
  try {
    stats.value = await adminGetFeedbackStats(days.value, 30)
  } catch {
    toast.error('加载反馈统计失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void refreshAll()
})
</script>

<template>
  <div class="sectionWrap">
    <n-card class="sectionCard" title="反馈统计">
      <div class="opsRow">
        <n-input-number v-model:value="days" :min="1" :max="365" />
        <n-button :loading="loading" @click="refreshAll">刷新</n-button>
      </div>

      <div class="stats">
        <n-statistic label="总反馈" :value="stats?.total || 0" />
        <n-statistic label="更准" :value="stats?.accurate || 0" />
        <n-statistic label="不太准" :value="stats?.inaccurate || 0" />
        <n-statistic label="准确率" :value="`${accuracyPct}%`" />
      </div>

      <n-card title="最近反馈时间线" class="innerCard">
        <div v-for="(item, idx) in stats?.recent || []" :key="`${idx}-${item.created_at}`" class="line">
          <n-tag :type="item.verdict === 'accurate' ? 'success' : 'warning'" size="small">
            {{ item.verdict === 'accurate' ? '更准' : '不太准' }}
          </n-tag>
          <span>{{ item.created_at }}</span>
          <code>{{ item.device_id.slice(0, 12) }}...</code>
          <span>{{ item.note || '无备注' }}</span>
        </div>
      </n-card>
    </n-card>
  </div>
</template>

