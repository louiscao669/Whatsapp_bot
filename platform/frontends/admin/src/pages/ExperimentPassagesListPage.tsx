import { type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApiResource } from '../hooks/useApiResource'
import {
  fetchExperimentPassages,
} from '../api/experimentPassages'

export function ExperimentPassagesListPage() {
  const navigate = useNavigate()
  const { data, loading, error } = useApiResource(
    '/api/v1/experiment-passages', fetchExperimentPassages, null, 'Failed to load experiment passages',
  )
  const items = data?.items ?? []

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
                <th>Verses</th>
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
                  <td>{item.verse_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
