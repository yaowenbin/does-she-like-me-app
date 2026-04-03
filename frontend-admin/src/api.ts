import { http } from './http'

export type GiftCodeStatus = 'unused' | 'used' | 'expired' | 'revoked'
export type AdminGiftCodeRow = {
  code: string
  credits: number
  status: GiftCodeStatus
  created_at?: string | null
  expires_at?: string | null
  revoked_at?: string | null
  used_by_device?: string | null
  used_at?: string | null
}

export async function adminListGiftCodes(): Promise<AdminGiftCodeRow[]> {
  const { data } = await http.get<AdminGiftCodeRow[]>('/api/admin/gift-codes')
  return data
}

export async function adminCreateGiftCodes(body: {
  generate?: { count: number; credits: number; expires_in_days: number; prefix?: string }
}): Promise<{ created: number; skipped_invalid: number; generated_plaintext: string | null }> {
  const { data } = await http.post('/api/admin/gift-codes', body)
  return data
}

export type AdminFeedbackStats = {
  days: number
  total: number
  accurate: number
  inaccurate: number
  accuracy_rate: number
  by_day: Array<{ day: string; accurate: number; inaccurate: number }>
  recent: Array<{ archive_id: string; device_id: string; verdict: 'accurate' | 'inaccurate'; note: string; created_at: string }>
}

export async function adminGetFeedbackStats(days = 30, recentLimit = 30): Promise<AdminFeedbackStats> {
  const { data } = await http.get<AdminFeedbackStats>('/api/admin/feedback/stats', {
    params: { days, recent_limit: recentLimit },
  })
  return data
}

export type AdminTuningRows = {
  total_rows: number
  rows: Array<{ device_id: string; skill_id: string; delta: number; updated_at: string }>
}

export async function adminGetTuningRows(limit = 200): Promise<AdminTuningRows> {
  const { data } = await http.get<AdminTuningRows>('/api/admin/tuning/rows', { params: { limit } })
  return data
}

export async function adminUpsertDeviceTuning(deviceId: string, deltas: Record<string, number>): Promise<{ ok: boolean; affected: number }> {
  const { data } = await http.post<{ ok: boolean; affected: number }>('/api/admin/tuning/device/upsert', {
    device_id: deviceId,
    deltas,
  })
  return data
}

export async function adminResetDeviceTuning(deviceId: string): Promise<{ ok: boolean; affected: number }> {
  const { data } = await http.post<{ ok: boolean; affected: number }>('/api/admin/tuning/device/reset', {
    device_id: deviceId,
  })
  return data
}

export type AdminQualityMetrics = {
  days: number
  total_reports: number
  evidence_coverage_rate: number
  actionable_rate: number
  stability_sample_groups: number
  stability_rate: number
}

export async function adminGetQualityMetrics(days = 30): Promise<AdminQualityMetrics> {
  const { data } = await http.get<AdminQualityMetrics>('/api/admin/quality/metrics', {
    params: { days },
  })
  return data
}
