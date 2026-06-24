import { useState } from 'react'
import { ApiError } from '../api/client'
import { bulkQaItemsAction } from '../api/qaItems'

type QaItemsBulkPanelProps = {
  selectedIds: string[]
  onComplete: (message: string) => void
  onError: (message: string) => void
  onClearSelection: () => void
}

export function QaItemsBulkPanel({
  selectedIds,
  onComplete,
  onError,
  onClearSelection,
}: QaItemsBulkPanelProps) {
  const [submitting, setSubmitting] = useState(false)

  if (!selectedIds.length) {
    return null
  }

  async function deleteSelected() {
    const confirmed = window.confirm(
      `Delete ${selectedIds.length} question(s) and all related assignments/responses?`,
    )
    if (!confirmed) {
      return
    }

    setSubmitting(true)
    try {
      const result = await bulkQaItemsAction({
        action: 'delete',
        qa_item_ids: selectedIds,
      })
      onComplete(result.message)
      onClearSelection()
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Bulk action failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="detail-card bulk-panel">
      <h3>Bulk actions ({selectedIds.length} selected)</h3>
      <div className="bulk-actions">
        <div className="action-row">
          <button
            type="button"
            className="btn-danger"
            disabled={submitting}
            onClick={deleteSelected}
          >
            Delete selected
          </button>
          <button type="button" className="link-button" onClick={onClearSelection}>
            Clear selection
          </button>
        </div>
      </div>
    </section>
  )
}
