import { apiFetch } from './client'

export type AudioExportItem = {
  response_id: string
  participant_id: string
  participant_label: string
  export_filename: string
  received_at: string | null
  has_storage: boolean
}

export type AudioExportQaGroup = {
  qa_item_id: string
  question_label: string
  items: AudioExportItem[]
}

export type AudioExportChapter = {
  chapter_label: string
  chapter_key: string
  qa_groups: AudioExportQaGroup[]
}

export function fetchAudioExport() {
  return apiFetch<{ chapters: AudioExportChapter[] }>('/api/v1/export/audio')
}

export async function downloadAudioZip(responseIds: string[]) {
  const response = await fetch('/api/v1/export/audio/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ response_ids: responseIds }),
  })
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { message?: string }
    throw new Error(payload.message ?? response.statusText)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'audio_export.zip'
  anchor.click()
  URL.revokeObjectURL(url)
}
