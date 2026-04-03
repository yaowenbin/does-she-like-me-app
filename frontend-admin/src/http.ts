import axios, { AxiosHeaders, type AxiosError } from 'axios'
import { createDiscreteApi } from 'naive-ui'

const API_BASE = import.meta.env.VITE_API_BASE_URL?.toString().replace(/\/$/, '') || ''

export const { message: toast } = createDiscreteApi(['message'], {
  messageProviderProps: { max: 3 },
})

export const http = axios.create({
  baseURL: API_BASE || undefined,
  timeout: 180_000,
})

http.interceptors.request.use((config) => {
  const headers = AxiosHeaders.from(config.headers ?? {})
  const adminTok = sessionStorage.getItem('dslm_admin_token')
  if (adminTok) headers.set('Authorization', `Bearer ${adminTok}`)
  config.headers = headers
  return config
})

http.interceptors.response.use(
  (res) => res,
  (err: AxiosError) => {
    const cfg = err.config as { skipGlobalErrorMessage?: boolean } | undefined
    if (!cfg?.skipGlobalErrorMessage) {
      const data = err.response?.data as { detail?: unknown } | undefined
      let text = '请求失败'
      if (data != null && typeof data === 'object' && 'detail' in data) {
        const d = (data as { detail: unknown }).detail
        if (typeof d === 'string') text = d
        else if (d != null) text = JSON.stringify(d)
      } else if (err.message) text = err.message
      toast.error(text, { duration: 4000 })
    }
    return Promise.reject(err)
  }
)
