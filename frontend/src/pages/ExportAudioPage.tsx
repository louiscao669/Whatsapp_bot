import { useEffect, useState } from 'react'
import { ApiError, getCachedApiData } from '../api/client'
import { downloadAudioZip, fetchAudioExport, type AudioExportChapter } from '../api/exports'

export function ExportAudioPage() {
  const cachedExport = getCachedApiData<{ chapters: AudioExportChapter[] }>('/api/v1/export/audio')
  const [chapters, setChapters] = useState<AudioExportChapter[]>(cachedExport?.chapters ?? [])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(!cachedExport)
  const [error, setError] = useState('')
  const [downloading, setDownloading] = useState(false)

  useEffect(() => {
    fetchAudioExport()
      .then((data) => setChapters(data.chapters))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load audio export')
      })
      .finally(() => setLoading(false))
  }, [])

  function toggle(id: string, checked: boolean) {
    setSelected((current) => {
      const next = new Set(current)
      if (checked) {
        next.add(id)
      } else {
        next.delete(id)
      }
      return next
    })
  }

  async function handleDownload() {
    if (!selected.size) {
      setError('Select at least one audio recording.')
      return
    }
    setDownloading(true)
    setError('')
    try {
      await downloadAudioZip([...selected])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed')
    } finally {
      setDownloading(false)
    }
  }

  if (loading) {
    return <p className="loading-message">Loading audio export…</p>
  }

  return (
    <section className="panel">
      <h2>Export Audio</h2>
      <p className="hint">Select participant audio responses and download as a ZIP archive.</p>
      {error ? <p className="error-message">{error}</p> : null}

      <div className="action-row">
        <button type="button" disabled={downloading} onClick={handleDownload}>
          {downloading ? 'Preparing ZIP…' : `Download selected (${selected.size})`}
        </button>
      </div>

      {chapters.map((chapter) => (
        <section key={chapter.chapter_key} className="detail-card">
          <h3>{chapter.chapter_label}</h3>
          {chapter.qa_groups.map((group) => (
            <div key={group.qa_item_id} className="export-qa-group">
              <h4>{group.question_label}</h4>
              <ul className="export-audio-list">
                {group.items.map((item) => (
                  <li key={item.response_id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={selected.has(item.response_id)}
                        disabled={!item.has_storage}
                        onChange={(event) => toggle(item.response_id, event.target.checked)}
                      />
                      <span>{item.export_filename}</span>
                      <span className="detail-meta">
                        {item.participant_label} ({item.wa_id})
                      </span>
                    </label>
                    {item.has_storage ? (
                      <a href={`/api/v1/export/audio/${item.response_id}`}>Download one</a>
                    ) : (
                      <span className="detail-meta">No stored file</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      ))}
    </section>
  )
}
