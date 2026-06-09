export function ExportFlaggedPage() {
  return (
    <section className="panel">
      <h2>Export flagged</h2>
      <p className="hint">Download flagged participant responses awaiting expert review as a CSV file.</p>
      <div className="action-row">
        <a className="review-workbench-toolbar-link" href="/api/v1/export/flagged.csv" download>
          Download flagged CSV
        </a>
      </div>
    </section>
  )
}
