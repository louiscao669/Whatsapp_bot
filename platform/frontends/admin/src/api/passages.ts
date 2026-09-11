import { ApiError, apiFetch } from './client'

export type PassageItem = {
  id: string
  language: string
  translation_name: string | null
  chapter_number: number
  verse_count: number
  verses: string
}

export function fetchPassageItems() {
  return apiFetch<{ items: PassageItem[] }>('/api/v1/passages')
}

export type PassageVerseDetail = {
  verse_number: string
  position: number
  text: string
}

export type PassageDetail = {
  id: string
  language: string
  translation_name: string | null
  chapter_number: number
  created_at: string | null
  updated_at: string | null
  verse_count: number
  verses: PassageVerseDetail[]
}

export function fetchPassageDetail(id: string, chapterNumber: number) {
  return apiFetch<PassageDetail>(
    `/api/v1/passages/${encodeURIComponent(id)}/${chapterNumber}`,
  )
}

export function fetchPassageTranslationNames(language?: string) {
  const query = language ? `?language=${encodeURIComponent(language)}` : ''
  return apiFetch<{ names: string[] }>(`/api/v1/passages/translation-names${query}`)
}

export type ImportPassageResult = {
  ok: true
  message: string
  translation: {
    id: string
    language: string
    name: string | null
    chapter_number: number
    verse_count: number
  }
}

export function importPassageTranslation(payload: {
  translation_text: string
  language: string
  chapter_number: number
  name?: string
}) {
  return apiFetch<ImportPassageResult>('/api/v1/passages/import', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function importPassageTranslationFromFile(
  file: File,
  fields: { language: string; chapter_number: number; name?: string },
) {
  const formData = new FormData()
  formData.append('translation_file', file)
  formData.append('language', fields.language)
  formData.append('chapter_number', String(fields.chapter_number))
  formData.append('name', fields.name ?? '')
  const response = await fetch('/api/v1/passages/import', {
    method: 'POST',
    body: formData,
    credentials: 'include',
  })
  const payload = (await response.json().catch(() => ({}))) as ImportPassageResult & {
    error?: string
    message?: string
  }
  if (!response.ok) {
    throw new ApiError(payload.message ?? response.statusText, response.status, payload.error)
  }
  return payload
}
