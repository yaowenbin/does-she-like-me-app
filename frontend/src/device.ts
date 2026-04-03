const DEVICE_KEY = 'dslm_device_id_v1'

/** 供 HTTP 客户端注入 X-Device-Id */
export function getOrCreateDeviceId(): string {
  let id = localStorage.getItem(DEVICE_KEY)
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(DEVICE_KEY, id)
  }
  return id
}

export function deviceHeaders(): Record<string, string> {
  return { 'X-Device-Id': getOrCreateDeviceId() }
}
