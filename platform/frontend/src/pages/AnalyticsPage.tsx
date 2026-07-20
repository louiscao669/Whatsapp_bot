import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, getCachedApiData } from '../api/client'
import { fetchAnalytics, type AnalyticsDashboard } from '../api/analytics'

const ANALYTICS_PATH = '/api/v1/analytics'

export function AnalyticsPage() {
  const cachedDashboard = getCachedApiData<AnalyticsDashboard>(ANALYTICS_PATH)
  const [dashboard, setDashboard] = useState<AnalyticsDashboard | null>(cachedDashboard)
  const [loading, setLoading] = useState(!cachedDashboard)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchAnalytics()
      .then(setDashboard)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : 'Failed to load analytics')
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <p className="loading-message">Loading Analytics…</p>
  }

  if (error) {
    return <p className="error-message">{error}</p>
  }

  if (!dashboard) {
    return null
  }

  return (
    <section className="panel">
      <h2>Analytics</h2>
      <p className="hint">Aggregate response analytics across participants and questions.</p>

      <section className="detail-card">
        <h3>Summary</h3>
        <dl className="detail-list">
          <dt>Participants</dt>
          <dd>{dashboard.summary.participants}</dd>
          <dt>QA items</dt>
          <dd>{dashboard.summary.qa_items}</dd>
          <dt>Responses</dt>
          <dd>{dashboard.summary.responses}</dd>
          <dt>Flagged</dt>
          <dd>{dashboard.summary.flagged}</dd>
          <dt>Average score</dt>
          <dd>{dashboard.summary.average_score ?? '—'}</dd>
        </dl>
      </section>

      <section className="detail-card">
        <h3>Responses per question</h3>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Passage</th>
                <th>Question</th>
                <th>Responses</th>
                <th>Min required</th>
                <th>Meets target</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.response_counts.map((row) => (
                <tr key={row.qa_item_id}>
                  <td>{row.passage}</td>
                  <td>
                    <Link to={`/qa-items/${row.qa_item_id}`}>{row.question}</Link>
                  </td>
                  <td>{row.response_count}</td>
                  <td>{row.min_required}</td>
                  <td className={row.meets_target ? 'target-met' : 'target-missed'}>
                    {row.meets_target ? 'Yes' : 'No'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="detail-card">
        <h3>Per-question metrics</h3>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Passage</th>
                <th>Question</th>
                <th>Responses</th>
                <th>Flagged</th>
                <th>Flag rate</th>
                <th>Average score</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.per_qa_metrics.map((row, index) => (
                <tr key={`${row.passage}-${index}`}>
                  <td>{row.passage}</td>
                  <td className="question-cell">{row.question}</td>
                  <td>{row.responses}</td>
                  <td>{row.flagged}</td>
                  <td>{row.flag_rate ?? '—'}</td>
                  <td>{row.average_score ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  )
}
