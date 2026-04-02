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

const API_BASE = import.meta.env.VITE_API_BASE_URL?.toString().replace(/\/$/, '') || ''

function url(path: string) {
  const p = path.startsWith('/') ? path : `/${path}`
  return API_BASE ? `${API_BASE}${p}` : p
}

async function jsonFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(url(path), {
    ...init,
    headers: {
      ...(init.headers || {}),
      'Content-Type': 'application/json',
    },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`)
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

export async function analyzeArchive(
  archiveId: string,
  input: { temperature: number }
): Promise<{ archive_id: string; model: string; report_markdown: string }> {
  return jsonFetch(`/api/archives/${archiveId}/analyze`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

