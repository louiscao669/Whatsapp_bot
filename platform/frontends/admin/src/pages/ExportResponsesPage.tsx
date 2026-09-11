export function ExportResponsesPage() {
  return (
    <section className="panel">
      <h2>Export responses</h2>
      <p className="hint">Download all participant responses as a CSV file.</p>
      <div className="action-row">
        <a className="review-workbench-toolbar-link" href="/api/v1/export/responses.csv" download>
          Download responses CSV
        </a>
      </div>
    </section>
  )
}
