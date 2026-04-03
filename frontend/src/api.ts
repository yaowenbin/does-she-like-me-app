import axios from 'axios'
import { http, toast } from './http'

export type ArchiveSummary = {
  id: string
  name: string
  stage: string
  scenario: string
  tags: Record<string, any>
  created_at: string
  updated_at: string
  has_upload: boolean
  has_report: boolean
}

export type ArchiveDetail = {
  archive: ArchiveSummary
  report: null | {
    model: string
    report_markdown: string
    scoring?: {
      input_signal?: Record<string, any>
      scoring_result?: Record<string, any>
      friendly_summary?: Record<string, any>
    }
    created_at: string
  }
}

export async function listArchives(): Promise<ArchiveSummary[]> {
  const { data } = await http.get<ArchiveSummary[]>('/api/archives')
  return data
}

export async function createArchive(input: {
  name?: string
  stage?: string
  scenario?: string
  tags?: Record<string, any>
}): Promise<{ id: string }> {
  const { data } = await http.post<{ id: string }>('/api/archives', {
    name: input.name || '',
    stage: input.stage || '',
    scenario: input.scenario || '',
    tags: input.tags || {},
  })
  return data
}

export async function getArchiveDetail(archiveId: string): Promise<ArchiveDetail> {
  const { data } = await http.get<ArchiveDetail>(`/api/archives/${archiveId}`)
  return data
}

export async function importWxTxt(archiveId: string, file: File): Promise<any> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post(`/api/archives/${archiveId}/import/wx-txt`, form)
  return data
}

export async function importPaste(
  archiveId: string,
  input: { text: string; filename?: string }
): Promise<any> {
  const { data } = await http.post(`/api/archives/${archiveId}/import/paste`, {
    text: input.text,
    filename: input.filename || '',
  })
  return data
}

export async function importOcr(
  archiveId: string,
  files: File[],
  input?: { lang?: string }
): Promise<any> {
  if (!files || files.length === 0) {
    toast.warning('请先选择截图图片')
    throw new Error('no files')
  }
  const form = new FormData()
  for (const f of files) form.append('files', f)
  const lang = input?.lang?.trim()
  const qs = lang ? `?lang=${encodeURIComponent(lang)}` : ''
  const { data } = await http.post(`/api/archives/${archiveId}/import/ocr${qs}`, form)
  return data
}

export type AnalyzeFeatures = {
  pipeline_version: string
  deep_reason_extra_credits: number
  reasoner_model: string
  entitlements_enforced: boolean
}

export type UsageStep = {
  step: string
  model: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  prompt_cache_hit_tokens?: number | null
  prompt_cache_miss_tokens?: number | null
}

export type AnalyzeResultDto = {
  archive_id: string
  model: string
  report_markdown: string
  pipeline_version?: string
  deep_reasoning_requested?: boolean
  deep_reasoning_used?: boolean
  reasoner_failed?: boolean
  reasoner_error?: string | null
  usage_steps?: UsageStep[]
  execution_trace?: Array<{
    step: string
    status: string
    model?: string | null
    error?: string | null
  }>
  input_signal?: Record<string, any>
  scoring_result?: Record<string, any>
  friendly_summary?: Record<string, any>
}

export type AnalyzePlan = {
  archive_id: string
  can_analyze: boolean
  blockers: string[]
  required_credits: number
  deep_reason_extra_credits: number
  deep_reasoning_enabled: boolean
  has_upload: boolean
  has_report: boolean
  pipeline_steps: string[]
}

export async function getAnalyzeFeatures(): Promise<AnalyzeFeatures> {
  const { data } = await http.get<AnalyzeFeatures>('/api/config/analyze', {
    skipGlobalErrorMessage: true,
  })
  return data
}

export async function analyzeArchive(
  archiveId: string,
  input: { temperature: number; deep_reasoning?: boolean }
): Promise<AnalyzeResultDto> {
  const { data } = await http.post<AnalyzeResultDto>(`/api/archives/${archiveId}/analyze`, {
    temperature: input.temperature,
    deep_reasoning: Boolean(input.deep_reasoning),
  })
  return data
}

export async function getAnalyzePlan(archiveId: string, deepReasoning: boolean): Promise<AnalyzePlan> {
  const { data } = await http.get<AnalyzePlan>(`/api/archives/${archiveId}/analyze/plan`, {
    params: { deep_reasoning: deepReasoning },
    skipGlobalErrorMessage: true,
  })
  return data
}

export type EntitlementsMe = {
  device_id: string
  credits: number
  oa_follow_bonus_claimed: boolean
  entitlements_enforced: boolean
}

export async function getEntitlementsMe(): Promise<EntitlementsMe> {
  const { data } = await http.get<EntitlementsMe>('/api/entitlements/me', {
    skipGlobalErrorMessage: true,
  })
  return data
}

export async function redeemGiftCode(code: string): Promise<{ ok: boolean; added: number; credits: number }> {
  const { data } = await http.post<{ ok: boolean; added: number; credits: number }>(
    '/api/entitlements/redeem',
    { code }
  )
  return data
}

export async function getWechatScene(): Promise<{ short_code: string; hint: string }> {
  const { data } = await http.get<{ short_code: string; hint: string }>('/api/entitlements/wechat-scene', {
    skipGlobalErrorMessage: true,
  })
  return data
}

export async function downloadReportPdf(archiveId: string): Promise<Blob> {
  const { data } = await http.get(`/api/archives/${archiveId}/export/pdf`, {
    responseType: 'blob',
  })
  return data as Blob
}

/** —— 运营后台（Bearer = sessionStorage dslm_admin_token）—— */

export type GiftCodeStatus = 'unused' | 'used' | 'expired' | 'revoked'

export type AdminGiftCodeRow = {
  code: string
  credits: number
  status: GiftCodeStatus
  created_at: string | null
  expires_at: string | null
  revoked_at: string | null
  used_by_device: string | null
  used_at: string | null
}

export async function adminListGiftCodes(): Promise<AdminGiftCodeRow[]> {
  const { data } = await http.get<AdminGiftCodeRow[]>('/api/admin/gift-codes')
  return data
}

export type AdminCreateGiftCodesBody = {
  items?: { code: string; credits: number }[]
  generate?: { count: number; credits: number; expires_in_days: number; prefix?: string }
  manual_expires_in_days?: number
}

export type AdminCreateGiftCodesResult = {
  created: number
  skipped_invalid: number
  generated_plaintext: string | null
}

export async function adminCreateGiftCodes(body: AdminCreateGiftCodesBody): Promise<AdminCreateGiftCodesResult> {
  const { data } = await http.post<AdminCreateGiftCodesResult>('/api/admin/gift-codes', body)
  return data
}

export async function adminRevokeGiftCodes(codes: string[]): Promise<{ revoked: number }> {
  const { data } = await http.post<{ revoked: number }>('/api/admin/gift-codes/revoke', { codes })
  return data
}

export function isAxiosCanceled(e: unknown): boolean {
  return axios.isAxiosError(e) && e.code === 'ERR_CANCELED'
}
