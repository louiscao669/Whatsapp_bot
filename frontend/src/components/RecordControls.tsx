import { useRef, useState } from 'react'
import { ApiError } from '../api/client'
import { type RecordTake, uploadRecording } from '../api/record'

type RecordControlsProps = {
  qaItemId: string
  recordingType: 'question' | 'answer'
  language: string
  mode: 'new' | 'retake'
  label: string
  choiceLetter?: string
  recordingId?: string
  version?: number
  onComplete: (message: string, recording: RecordTake) => void
  onError: (message: string) => void
  onRetakePreview?: (blob: Blob) => Promise<boolean>
}

export function RecordControls({
  qaItemId,
  recordingType,
  language,
  mode,
  label,
  choiceLetter,
  recordingId,
  version,
  onComplete,
  onError,
  onRetakePreview,
}: RecordControlsProps) {
  const [state, setState] = useState<'idle' | 'recording' | 'uploading'>('idle')
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  function releaseStream() {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop())
    mediaStreamRef.current = null
  }

  async function startRecording() {
    setState('recording')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaStreamRef.current = stream
      chunksRef.current = []
      const recorder = new MediaRecorder(stream)
      mediaRecorderRef.current = recorder
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data)
        }
      }
      recorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || 'audio/webm',
        })
        releaseStream()
        mediaRecorderRef.current = null
        chunksRef.current = []

        if (blob.size === 0) {
          onError('No audio captured')
          setState('idle')
          return
        }

        try {
          if (mode === 'retake' && onRetakePreview) {
            const confirmed = await onRetakePreview(blob)
            if (!confirmed) {
              setState('idle')
              return
            }
          }
          setState('uploading')
          const result = await uploadRecording({
            qaItemId,
            recordingType,
            language,
            mode,
            blob,
            choiceLetter,
            recordingId,
            version,
          })
          if (!result.recording) {
            throw new ApiError('Recording saved but server returned no recording data', 500)
          }
          onComplete(result.message ?? 'Recording saved', result.recording)
        } catch (err) {
          onError(err instanceof ApiError ? err.message : 'Recording upload failed')
        } finally {
          setState('idle')
        }
      }
      recorder.start()
    } catch (err) {
      setState('idle')
      onError(
        `Microphone access denied or unavailable: ${
          err instanceof Error ? err.message : String(err)
        }`,
      )
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop()
    }
  }

  if (state === 'recording') {
    return (
      <button type="button" className="btn-danger" onClick={stopRecording}>
        Stop
      </button>
    )
  }

  return (
    <button type="button" disabled={state === 'uploading'} onClick={startRecording}>
      {state === 'uploading' ? 'Saving…' : label}
    </button>
  )
}
