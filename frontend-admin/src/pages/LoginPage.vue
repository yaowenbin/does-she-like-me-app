<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCard, NInput, NSpin } from 'naive-ui'
import { toast } from '../http'

const router = useRouter()

const token = ref(sessionStorage.getItem('dslm_admin_token') || '')
const loading = ref(false)
const booted = ref(false)

async function doLogin() {
  const tok = token.value.trim()
  if (tok.length < 8) return toast.warning('请输入有效管理密钥')

  loading.value = true
  try {
    sessionStorage.setItem('dslm_admin_token', tok)
    // 基本鉴权：拉一下列表触发 401/403 提示（后端会用 http 拦截器弹 toast）。
    // 如果你后面要做扫码登录，这里就会改成“换取 token -> 跳转”。
    await router.push('/admin/codes')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  booted.value = true
})
</script>

<template>
  <div class="loginWrap">
    <n-card class="loginCard" :bordered="false">
      <div class="loginCardInner">
        <div class="loginBadge">
          <svg class="loginBadgeSvg" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M12 21s-7-4.5-9-9c-1.2-3 1.2-6 4.5-6 1.8 0 3.1.8 4.5 2 1.4-1.2 2.7-2 4.5-2 3.3 0 5.7 3 4.5 6-2 4.5-9 9-9 9Z"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linejoin="round"
            />
          </svg>
        </div>
        <h1 class="loginTitle">管理员登录</h1>
        <p class="loginDesc">
          后面你要做扫码登录的话，把 token 获取替换到这里就行；页面结构已经拆干净，不会揉成一团。
        </p>

        <div style="margin-top: 16px">
          <n-input
            v-model:value="token"
            type="password"
            show-password-on="mousedown"
            placeholder="输入管理密钥"
            :disabled="loading"
          />
        </div>

        <div style="margin-top: 12px; display: flex; gap: 10px; flex-wrap: wrap">
          <n-button type="primary" strong :loading="loading" @click="doLogin">进入后台</n-button>
          <n-button quaternary :disabled="loading" @click="token = ''">清空</n-button>
        </div>

        <div v-if="booted" class="qrHint">
          <div class="qrTitle">扫码登录（占位）</div>
          <div class="qrDesc">后续接入二维码流程：获取 token -> 跳转 /admin/*。</div>
        </div>
      </div>
    </n-card>
    <div v-if="loading" class="loadingOverlay" aria-hidden="true">
      <n-spin size="large" />
    </div>
  </div>
</template>

<style scoped>
.loginWrap {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 62vh;
}

.loginCard {
  width: min(520px, 92vw);
  border-radius: 16px;
}

.loginCard :deep(.n-card__content) {
  padding: 0 !important;
}

.loginCardInner {
  padding: 1.75rem 1.5rem 2rem;
}

.loginBadge {
  width: 54px;
  height: 54px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 14px;
  background: linear-gradient(145deg, rgba(244, 114, 182, 0.22), rgba(99, 102, 241, 0.14));
  border: 1px solid rgba(244, 114, 182, 0.25);
  color: #f9a8d4;
}

.loginBadgeSvg {
  width: 28px;
  height: 28px;
}

.loginTitle {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 700;
  color: #f8fafc;
}

.loginDesc {
  margin: 0.35rem 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: rgba(148, 163, 184, 0.95);
}

.qrHint {
  margin-top: 18px;
  padding: 12px 12px;
  border-radius: 14px;
  border: 1px dashed rgba(148, 163, 184, 0.24);
  background: rgba(8, 10, 14, 0.35);
}

.qrTitle {
  font-weight: 650;
  font-size: 13px;
  color: rgba(226, 232, 240, 0.95);
}

.qrDesc {
  margin-top: 6px;
  font-size: 12px;
  color: rgba(148, 163, 184, 0.95);
  line-height: 1.55;
}

.loadingOverlay {
  position: fixed;
  inset: 0;
  background: rgba(3, 4, 8, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
</style>

