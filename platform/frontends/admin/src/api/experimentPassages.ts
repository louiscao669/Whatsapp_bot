import { apiFetch } from './client'

export type ExperimentPassageRow = {
  id: string
  chapter: number
  condition: string
  name: string | null
  language: string
  passage_reference: string | null
  char_count: number
  verse_count: number
}

export type ExperimentPassageDetail = ExperimentPassageRow & {
  passage_text: string
  created_at: string | null
  verses: Array<{ verse_number: string; position: number; text: string }>
}

export function fetchExperimentPassages() {
  return apiFetch<{ items: ExperimentPassageRow[] }>('/api/v1/experiment-passages')
}

export function fetchExperimentPassageDetail(id: string) {
  return apiFetch<ExperimentPassageDetail>(
    `/api/v1/experiment-passages/${encodeURIComponent(id)}`,
  )
}
