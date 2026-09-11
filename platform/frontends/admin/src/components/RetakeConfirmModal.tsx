import { useEffect, useRef } from 'react'

type RetakeConfirmModalProps = {
  blob: Blob | null
  onConfirm: () => void
  onCancel: () => void
}

export function RetakeConfirmModal({ blob, onConfirm, onCancel }: RetakeConfirmModalProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const objectUrlRef = useRef<string | null>(null)

  useEffect(() => {
    if (!blob || !audioRef.current) {
      return
    }
    const url = URL.createObjectURL(blob)
    objectUrlRef.current = url
    audioRef.current.src = url
    return () => {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current)
        objectUrlRef.current = null
      }
    }
  }, [blob])

  if (!blob) {
    return null
  }

  return (
    <div className="record-modal" role="dialog" aria-modal="true">
      <div className="record-modal-backdrop" onClick={onCancel} />
      <div className="record-modal-panel">
        <h3>Replace this recording?</h3>
        <p>Listen to what you just recorded. If you continue, the existing take will be replaced.</p>
        <audio ref={audioRef} controls preload="auto" />
        <div className="action-row">
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" onClick={onConfirm}>
            Replace recording
          </button>
        </div>
      </div>
    </div>
  )
}
