import { ApiError, apiFetch, clearApiCache } from './client'

export type RecordTake = {
  id: string
  recording_type: string
  language: string
  version: number
  choice_letter: string | null
  media_url: string
  has_storage: boolean
  created_at: string | null
  label: string
}

export type RecordAnswerSlot = {
  letter: string
  text: string
  is_correct: boolean
  recording: RecordTake | null
}

export type RecordAnswer =
  | { kind: 'open'; text: string; recording: RecordTake | null }
  | { kind: 'mcq' | 'tf'; slots: RecordAnswerSlot[] }

export type RecordRow = {
  qa_item_id: string
  passage: string
  question: string
  question_type: string
  answer: RecordAnswer
  question_recording: RecordTake | null
}

export type RecordDashboard = {
  language: string | null
  language_options: string[]
  items: RecordRow[]
}

export function fetchRecordDashboard(language?: string) {
  const params = language ? `?language=${encodeURIComponent(language)}` : ''
  return apiFetch<RecordDashboard>(`/api/v1/record${params}`)
}

export type UploadRecordingParams = {
  qaItemId: string
  recordingType: 'question' | 'answer'
  language: string
  mode: 'new' | 'retake'
  blob: Blob
  choiceLetter?: string
  recordingId?: string
  version?: number
}

export async function uploadRecording(params: UploadRecordingParams) {
  const formData = new FormData()
  formData.append('qa_item_id', params.qaItemId)
  formData.append('recording_type', params.recordingType)
  formData.append('language', params.language)
  formData.append('mode', params.mode)
  if (params.choiceLetter) {
    formData.append('choice_letter', params.choiceLetter)
  }
  if (params.recordingId) {
    formData.append('recording_id', params.recordingId)
  }
  if (params.version != null) {
    formData.append('version', String(params.version))
  }
  formData.append('audio', params.blob, 'recording.webm')

  const response = await fetch('/api/v1/record/upload', {
    method: 'POST',
    body: formData,
    credentials: 'include',
  })
  const payload = (await response.json().catch(() => ({}))) as {
    ok?: boolean
    message?: string
    error?: string
    recording?: RecordTake
  }
  if (!response.ok) {
    throw new ApiError(payload.message ?? response.statusText, response.status, payload.error)
  }
  clearApiCache('/api/v1/record')
  return payload
}

export function cacheBustMediaUrl(recording: RecordTake): RecordTake {
  if (!recording.created_at) {
    return recording
  }
  const separator = recording.media_url.includes('?') ? '&' : '?'
  return {
    ...recording,
    media_url: `${recording.media_url}${separator}v=${encodeURIComponent(recording.created_at)}`,
  }
}

export function patchRecordingAfterUpload(
  dashboard: RecordDashboard,
  qaItemId: string,
  recordingType: 'question' | 'answer',
  recording: RecordTake,
  choiceLetter?: string,
): RecordDashboard {
  const patchedRecording = cacheBustMediaUrl(recording)
  return {
    ...dashboard,
    items: dashboard.items.map((row) => {
      if (row.qa_item_id !== qaItemId) {
        return row
      }
      if (recordingType === 'question') {
        return { ...row, question_recording: patchedRecording }
      }
      const answer = row.answer
      if (answer.kind === 'open') {
        return { ...row, answer: { ...answer, recording: patchedRecording } }
      }
      const letter = choiceLetter?.toUpperCase()
      return {
        ...row,
        answer: {
          ...answer,
          slots: answer.slots.map((slot) =>
            slot.letter === letter ? { ...slot, recording: patchedRecording } : slot,
          ),
        },
      }
    }),
  }
}

export function patchRecordingAfterDelete(
  dashboard: RecordDashboard,
  qaItemId: string,
  recording: RecordTake,
): RecordDashboard {
  const recordingType = recording.recording_type
  const choiceLetter = recording.choice_letter
  return {
    ...dashboard,
    items: dashboard.items.map((row) => {
      if (row.qa_item_id !== qaItemId) {
        return row
      }
      if (recordingType === 'question') {
        return { ...row, question_recording: null }
      }
      const answer = row.answer
      if (answer.kind === 'open') {
        return { ...row, answer: { ...answer, recording: null } }
      }
      return {
        ...row,
        answer: {
          ...answer,
          slots: answer.slots.map((slot) =>
            slot.letter === choiceLetter ? { ...slot, recording: null } : slot,
          ),
        },
      }
    }),
  }
}

export function deleteRecording(recordingId: string) {
  return apiFetch<{ ok: true; message: string }>(`/api/v1/record/recordings/${recordingId}`, {
    method: 'DELETE',
  })
}
