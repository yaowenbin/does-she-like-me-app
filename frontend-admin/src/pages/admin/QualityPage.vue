<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { NButton, NCard, NInputNumber, NProgress, NStatistic } from 'naive-ui'
import { adminGetQualityMetrics, type AdminQualityMetrics } from '../../api'
import { toast } from '../../http'

const loading = ref(false)
const days = ref(30)
const metrics = ref<AdminQualityMetrics | null>(null)

const evidencePct = computed(() => Math.round((metrics.value?.evidence_coverage_rate || 0) * 100))
const actionablePct = computed(() => Math.round((metrics.value?.actionable_rate || 0) * 100))
const stabilityPct = computed(() => Math.round((metrics.value?.stability_rate || 0) * 100))

async function refreshData() {
  loading.value = true
  try {
    metrics.value = await adminGetQualityMetrics(days.value)
  } catch {
    toast.error('加载质量指标失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void refreshData()
})
</script>

<template>
  <div class="sectionWrap">
    <n-card class="sectionCard" title="报告质量看板">
      <div class="opsRow">
        <n-input-number v-model:value="days" :min="1" :max="365" />
        <n-button :loading="loading" @click="refreshData">刷新</n-button>
      </div>

      <div class="stats">
        <n-statistic label="样本报告数" :value="metrics?.total_reports || 0" />
        <n-statistic label="稳定性样本组" :value="metrics?.stability_sample_groups || 0" />
      </div>

      <n-card class="innerCard" title="核心质量指标">
        <div class="opsCol">
          <div>
            <div class="mutedText">证据覆盖率（每份报告≥3条可追溯证据）</div>
            <n-progress type="line" :percentage="evidencePct" indicator-placement="inside" processing />
          </div>
          <div>
            <div class="mutedText">建议可执行率（含具体行动与观察点）</div>
            <n-progress type="line" :percentage="actionablePct" indicator-placement="inside" processing />
          </div>
          <div>
            <div class="mutedText">结论稳定性（同输入多次分析分差≤8）</div>
            <n-progress type="line" :percentage="stabilityPct" indicator-placement="inside" processing />
          </div>
        </div>
      </n-card>
    </n-card>
  </div>
</template>
