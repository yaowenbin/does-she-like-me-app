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
    created_at: string
  }
}

import { deviceHeaders } from './device'

const API_BASE = import.meta.env.VITE_API_BASE_URL?.toString().replace(/\/$/, '') || ''

function url(path: string) {
  const p = path.startsWith('/') ? path : `/${path}`
  return API_BASE ? `${API_BASE}${p}` : p
}

function formatHttpErrorBody(text: string): string {
  try {
    const j = JSON.parse(text) as { detail?: unknown }
    if (j?.detail != null) {
      return typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    }
  } catch {
    /* 非 JSON */
  }
  return text
}

async function jsonFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || 'GET').toUpperCase()
  const headers: Record<string, string> = {
    ...deviceHeaders(),
    ...(init.headers as Record<string, string> | undefined),
  }
  if (method !== 'GET' && method !== 'HEAD') {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json'
  }
  const res = await fetch(url(path), {
    ...init,
    headers,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    const detail = formatHttpErrorBody(text)
    throw new Error(`HTTP ${res.status}: ${detail || res.statusText}`)
  }
  return (await res.json()) as T
}

export async function listArchives(): Promise<ArchiveSummary[]> {
  return jsonFetch('/api/archives')
}

export async function createArchive(input: {
  name?: string
  stage?: string
  scenario?: string
  tags?: Record<string, any>
}): Promise<{ id: string }> {
  return jsonFetch('/api/archives', {
    method: 'POST',
    body: JSON.stringify({
      name: input.name || '',
      stage: input.stage || '',
      scenario: input.scenario || '',
      tags: input.tags || {},
    }),
  })
}

export async function getArchiveDetail(archiveId: string): Promise<ArchiveDetail> {
  return jsonFetch(`/api/archives/${archiveId}`)
}

export async function importWxTxt(archiveId: string, file: File): Promise<any> {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch(url(`/api/archives/${archiveId}/import/wx-txt`), {
    method: 'POST',
    headers: deviceHeaders(),
    body: form,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`)
  }
  return await res.json()
}

export async function importPaste(
  archiveId: string,
  input: { text: string; filename?: string }
): Promise<any> {
  return jsonFetch(`/api/archives/${archiveId}/import/paste`, {
    method: 'POST',
    body: JSON.stringify({
      text: input.text,
      filename: input.filename || '',
    }),
  })
}

export async function importOcr(
  archiveId: string,
  files: File[],
  input?: { lang?: string }
): Promise<any> {
  if (!files || files.length === 0) {
    throw new Error('请先选择截图图片')
  }
  const form = new FormData()
  for (const f of files) form.append('files', f)

  const lang = input?.lang?.trim()
  const qs = lang ? `?lang=${encodeURIComponent(lang)}` : ''

  const res = await fetch(url(`/api/archives/${archiveId}/import/ocr${qs}`), {
    method: 'POST',
    headers: deviceHeaders(),
    body: form,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`)
  }
  return await res.json()
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
}

export async function getAnalyzeFeatures(): Promise<AnalyzeFeatures> {
  return jsonFetch('/api/config/analyze')
}

export async function analyzeArchive(
  archiveId: string,
  input: { temperature: number; deep_reasoning?: boolean }
): Promise<AnalyzeResultDto> {
  return jsonFetch(`/api/archives/${archiveId}/analyze`, {
    method: 'POST',
    body: JSON.stringify({
      temperature: input.temperature,
      deep_reasoning: Boolean(input.deep_reasoning),
    }),
  })
}

export type EntitlementsMe = {
  device_id: string
  credits: number
  oa_follow_bonus_claimed: boolean
  entitlements_enforced: boolean
}

export async function getEntitlementsMe(): Promise<EntitlementsMe> {
  return jsonFetch('/api/entitlements/me')
}

export async function redeemGiftCode(code: string): Promise<{ ok: boolean; added: number; credits: number }> {
  return jsonFetch('/api/entitlements/redeem', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
}

export async function getWechatScene(): Promise<{ short_code: string; hint: string }> {
  return jsonFetch('/api/entitlements/wechat-scene')
}

export async function downloadReportPdf(archiveId: string): Promise<Blob> {
  const res = await fetch(url(`/api/archives/${archiveId}/export/pdf`), {
    headers: deviceHeaders(),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${formatHttpErrorBody(text) || res.statusText}`)
  }
  return await res.blob()
}

