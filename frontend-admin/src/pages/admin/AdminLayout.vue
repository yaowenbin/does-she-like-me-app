<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { NButton, NLayout, NLayoutContent, NLayoutSider, NMenu } from 'naive-ui'
import type { MenuOption } from 'naive-ui'

const router = useRouter()
const route = useRoute()

const menuOptions: MenuOption[] = [
  { label: '卡密运营', key: 'codes' },
  { label: '反馈统计', key: 'feedback' },
  { label: '调优配置', key: 'tuning' },
]

const menuKey = ref<string>('codes')

watch(
  () => route.name,
  () => {
    if (route.name === 'feedback') menuKey.value = 'feedback'
    else if (route.name === 'tuning') menuKey.value = 'tuning'
    else menuKey.value = 'codes'
  },
  { immediate: true },
)

watch(menuKey, (k) => {
  if (k === 'codes' && route.name === 'codes') return
  if (k === 'feedback' && route.name === 'feedback') return
  if (k === 'tuning' && route.name === 'tuning') return

  if (k === 'codes') router.push('/admin/codes')
  else if (k === 'feedback') router.push('/admin/feedback')
  else router.push('/admin/tuning')
})

function logout() {
  sessionStorage.removeItem('dslm_admin_token')
  router.push('/login')
}

const currentPageTitle = computed(() => {
  if (menuKey.value === 'feedback') return '反馈统计'
  if (menuKey.value === 'tuning') return '调优配置'
  return '卡密运营'
})
</script>

<template>
  <n-layout has-sider class="adminBody">
    <n-layout-sider class="adminSider" width="220" bordered>
      <n-menu :options="menuOptions" v-model:value="menuKey" />
    </n-layout-sider>

    <n-layout-content class="adminContent">
      <div class="adminNav">
        <div class="adminNavInner">
          <div class="adminBrand">
            <p class="adminEyebrow">Gift codes · Admin</p>
            <h1 class="adminTitle">运营中心</h1>
            <p class="adminSubtitle">{{ currentPageTitle }} · 批量入库、状态可视、调优与复位</p>
          </div>
          <div class="auth">
            <n-button quaternary round @click="logout">退出</n-button>
          </div>
        </div>
      </div>

      <router-view />
    </n-layout-content>
  </n-layout>
</template>

