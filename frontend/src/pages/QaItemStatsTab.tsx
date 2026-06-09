import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { fetchQaItemStats, type QaItemStats } from '../api/qaItems'

type QaItemStatsTabProps = {
  qaItemId: string
  selectedLanguages: string[]
  onLanguagesChange: (languages: string[]) => void
}

function StatsBarChart({ rows }: { rows: QaItemStats['bar_chart'] }) {
  if (!rows.length) {
    return null
  }
  const maxCount = Math.max(...rows.map((row) => row.count), 1)

  return (
    <div className="qa-stats-bar-chart" role="img" aria-label="Answer choice distribution">
      {rows.map((row) => {
        const widthPct = maxCount ? Math.round((100 * row.count) / maxCount) : 0
        return (
          <div key={row.letter} className="qa-stats-bar-row">
            <span>{row.letter}</span>
            <div className="qa-stats-bar-track">
              <div
                className={row.is_correct ? 'qa-stats-bar-fill is-correct' : 'qa-stats-bar-fill'}
                style={{ width: `${widthPct}%` }}
              />
            </div>
            <span>{row.count}</span>
          </div>
        )
      })}
    </div>
  )
}

export function QaItemStatsTab({
  qaItemId,
  selectedLanguages,
  onLanguagesChange,
}: QaItemStatsTabProps) {
  const [stats, setStats] = useState<QaItemStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')

    fetchQaItemStats(qaItemId, selectedLanguages)
      .then((data) => {
        if (!cancelled) {
          setStats(data.stats)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Failed to load statistics')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [qaItemId, selectedLanguages])

  if (loading) {
    return <p className="loading-message">Loading response statistics…</p>
  }

  if (error) {
    return <p className="error-message">{error}</p>
  }

  if (!stats) {
    return null
  }

  const languageOptions = stats.language_options.length
    ? stats.language_options
    : stats.selected_languages

  return (
    <section className="detail-card stats-tab">
      <h3>Response statistics</h3>
      <p className="detail-meta">
        Question type: <strong>{stats.question_type}</strong> · {stats.total_responses}{' '}
        response(s) in the selected language scope.
      </p>

      <form
        className="language-filter"
        onSubmit={(event) => {
          event.preventDefault()
          const form = event.currentTarget
          const select = form.elements.namedItem('languages') as HTMLSelectElement
          const values = Array.from(select.selectedOptions).map((option) => option.value)
          onLanguagesChange(values)
        }}
      >
        <label htmlFor="stats-languages">Target language(s)</label>
        <select
          id="stats-languages"
          name="languages"
          multiple
          size={Math.min(Math.max(languageOptions.length, 3), 6)}
          defaultValue={stats.selected_languages}
        >
          {languageOptions.map((language) => (
            <option key={language} value={language}>
              {language}
            </option>
          ))}
        </select>
        <p className="hint">Hold Cmd/Ctrl to select multiple. Leave all selected for every language.</p>
        <button type="submit">Apply language filter</button>
      </form>

      {stats.summary_cards.length ? (
        <div className="qa-stats-grid">
          {stats.summary_cards.map((card) => (
            <div key={card.label} className="qa-stats-card">
              <strong>{card.count}</strong>
              <span>{card.label}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="detail-meta">No responses in the selected language scope.</p>
      )}

      {stats.bar_chart.length ? (
        <>
          <h4>Answer distribution</h4>
          <StatsBarChart rows={stats.bar_chart} />
        </>
      ) : null}

      <h4>Participants ({stats.participants.length})</h4>
      {stats.participants.length ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Participant</th>
                <th>Language</th>
                <th>Response time</th>
                <th>Type</th>
                <th>Answer</th>
                <th>Correctness</th>
              </tr>
            </thead>
            <tbody>
              {stats.participants.map((row, index) => (
                <tr key={`${row.participant}-${row.received_at}-${index}`}>
                  <td>{row.participant || '—'}</td>
                  <td>{row.language || '—'}</td>
                  <td>{row.received_at || '—'}</td>
                  <td>{row.response_type}</td>
                  <td>{row.answer || '—'}</td>
                  <td>{row.correctness}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="detail-meta">No participant responses in this language scope.</p>
      )}
    </section>
  )
}
