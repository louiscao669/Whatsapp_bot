import { useState } from 'react'
import { QaItemsImportPanel } from '../components/QaItemsImportPanel'

export function QaItemsAddPage() {
  const [message, setMessage] = useState('')

  return (
    <section className="panel">
      <h2>Add QAs</h2>
      {message ? <p className="success-message">{message}</p> : null}
      <QaItemsImportPanel onImported={() => setMessage('Import completed.')} />
    </section>
  )
}
