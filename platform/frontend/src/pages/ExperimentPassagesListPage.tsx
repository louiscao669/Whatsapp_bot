import { useCallback, useEffect, useState, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  fetchExperimentPassages,
  type ExperimentPassageRow,
} from '../api/experimentPassages'

export function ExperimentPassagesListPage() {
  const navigate = useNavigate()
  const [items, setItems] = useState<ExperimentPassageRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadItems = useCallback(() => {
    setError('')
    return fetchExperimentPassages()
      .then(({ items: loaded }) => setItems(loaded))
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Failed to load experiment passages'),
      )
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    loadItems()
  }, [loadItems])

  function open(id: string) {
    navigate(`/experiment-passages/${id}`)
  }

  function handleRowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, id: string) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      open(id)
    }
  }

  if (loading) return <p className="loading-message">Loading experiment passages…</p>

  return (
    <section className="panel">
      <div className="panel-heading-row">
        <h2>Experiment passages</h2>
      </div>
      <p className="hint">
        Pilot condition variants (one per chapter × condition). Click a row to read the full
        passage text.
      </p>
      {error ? <p className="error-message">{error}</p> : null}

      {items.length === 0 ? (
        <p>No experiment passages found.</p>
      ) : (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Chapter</th>
                <th>Condition</th>
                <th>Name</th>
                <th>Language</th>
                <th>Reference</th>
                <th>Characters</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.id}
                  className="data-table-row-clickable"
                  tabIndex={0}
                  role="link"
                  aria-label={`Open Luke ${item.chapter} ${item.name ?? item.condition}`}
                  onClick={() => open(item.id)}
                  onKeyDown={(event) => handleRowKeyDown(event, item.id)}
                >
                  <td>{item.chapter}</td>
                  <td>{item.condition}</td>
                  <td>{item.name ?? '—'}</td>
                  <td>{item.language}</td>
                  <td>{item.passage_reference ?? '—'}</td>
                  <td>{item.char_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
