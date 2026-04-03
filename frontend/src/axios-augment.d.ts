import 'axios'

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** 为 true 时不弹出全局错误 Message（如静默刷新配置） */
    skipGlobalErrorMessage?: boolean
  }
}
