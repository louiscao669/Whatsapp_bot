import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import {
  markReviewQaReviewed,
  removeReviewQaItem,
  revertReviewQaItem,
  updateReviewQaItem,
  type ReviewQaItem,
  type ReviewQaTab,
} from '../api/reviewQa'

const LETTERS = ['A', 'B', 'C', 'D'] as const

type ReviewQaUnreviewedItemProps = {
  item: ReviewQaItem
  onAction: (tab: ReviewQaTab, message: string) => void
  onError: (message: string) => void
}

export function ReviewQaUnreviewedItem({ item, onAction, onError }: ReviewQaUnreviewedItemProps) {
  const [questionText, setQuestionText] = useState(item.question_text)
  const [questionType, setQuestionType] = useState(item.question_type)
  const [expectedAnswer, setExpectedAnswer] = useState(item.expected_answer)
  const [choices, setChoices] = useState([...item.mcq_choices])
  const [correctChoice, setCorrectChoice] = useState(item.mcq_correct_choice ?? '')
  const [showPassage, setShowPassage] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const choiceSlots = questionType === 'mcq' ? 4 : questionType === 'tf' ? 2 : 0
  const isChoiceType = questionType === 'mcq' || questionType === 'tf'
  const displayQuestionType = questionType === 'tf' ? 'mcq' : questionType

  function updateChoice(index: number, value: string) {
    setChoices((current) => {
      const next = [...current]
      next[index] = value
      return next
    })
  }

  async function runAction(action: () => Promise<{ tab: ReviewQaTab; message: string }>) {
    setSubmitting(true)
    try {
      const result = await action()
      onAction(result.tab, result.message)
    } catch (err) {
      onError(err instanceof ApiError ? err.message : 'Action failed')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleSave(event: FormEvent) {
    event.preventDefault()
    await runAction(async () => {
      const result = await updateReviewQaItem(item.id, {
        question_text: questionText,
        question_type: questionType,
        expected_answer: expectedAnswer,
        mcq_choices: choices,
        mcq_correct_choice: correctChoice,
      })
      return { tab: result.tab, message: result.message }
    })
  }

  return (
    <article className={`review-qa-item review-qa-type-${questionType}`}>
      <header className="review-qa-item-header">
        <button type="button" className="review-qa-passage-link" onClick={() => setShowPassage((v) => !v)}>
          {item.passage}
        </button>
        <span className="detail-meta">{item.question_type}</span>
      </header>

      {showPassage && item.passage_text ? (
        <div className="review-qa-passage-detail">
          <p className="detail-text">{item.passage_text}</p>
        </div>
      ) : null}

      <form className="review-qa-form" onSubmit={handleSave}>
        <div className="review-qa-fields">
          <div className="review-qa-field">
            <label htmlFor={`question-${item.id}`}>Question</label>
            <textarea
              id={`question-${item.id}`}
              value={questionText}
              onChange={(e) => setQuestionText(e.target.value)}
              required
              rows={3}
            />
          </div>

          <div className="review-qa-field review-qa-field-type">
            <label htmlFor={`type-${item.id}`}>Question type</label>
            <select
              id={`type-${item.id}`}
              value={displayQuestionType}
              onChange={(e) => setQuestionType(e.target.value)}
            >
              <option value="open">Open</option>
              <option value="mcq">MCQ (4 choices)</option>
            </select>
          </div>

          {isChoiceType ? (
            <div className="review-qa-mcq-block">
              <p className="review-qa-block-title">Answer choices</p>
              <div className="review-qa-choice-row">
                {LETTERS.map((letter, index) => (
                  <div
                    key={letter}
                    className="review-qa-choice-slot"
                    style={{ display: index < choiceSlots ? undefined : 'none' }}
                  >
                    <label htmlFor={`choice-${item.id}-${letter}`}>
                      {letter}
                      {correctChoice === letter ? ' (Correct)' : ''}
                    </label>
                    <input
                      id={`choice-${item.id}-${letter}`}
                      type="text"
                      value={choices[index] ?? ''}
                      onChange={(e) => updateChoice(index, e.target.value)}
                    />
                  </div>
                ))}
              </div>
              <div className="review-qa-field review-qa-field-type">
                <label htmlFor={`correct-${item.id}`}>Correct choice</label>
                <select
                  id={`correct-${item.id}`}
                  value={correctChoice}
                  onChange={(e) => setCorrectChoice(e.target.value)}
                >
                  <option value="">Select…</option>
                  {LETTERS.slice(0, choiceSlots).map((letter) => (
                    <option key={letter} value={letter}>
                      {letter}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          ) : (
            <div className="review-qa-field">
              <label htmlFor={`answer-${item.id}`}>Answer</label>
              <textarea
                id={`answer-${item.id}`}
                value={expectedAnswer}
                onChange={(e) => setExpectedAnswer(e.target.value)}
                rows={3}
              />
            </div>
          )}
        </div>

        <footer className="review-qa-form-footer">
          <button type="submit" className="btn-primary" disabled={submitting}>
            Save
          </button>
          <div className="action-row">
            <button
              type="button"
              disabled={submitting}
              onClick={() =>
                runAction(async () => {
                  const result = await markReviewQaReviewed(item.id)
                  return { tab: result.tab, message: result.message }
                })
              }
            >
              Mark as reviewed
            </button>
            <button
              type="button"
              disabled={submitting || !item.has_original}
              onClick={() =>
                runAction(async () => {
                  const result = await revertReviewQaItem(item.id)
                  return { tab: result.tab, message: result.message }
                })
              }
            >
              Revert to original
            </button>
            <button
              type="button"
              className="btn-danger"
              disabled={submitting}
              onClick={() => {
                if (!window.confirm('Remove this QA from assignment? It will move to Removed QAs.')) {
                  return
                }
                runAction(async () => {
                  const result = await removeReviewQaItem(item.id)
                  return { tab: result.tab, message: result.message }
                })
              }}
            >
              Remove
            </button>
          </div>
        </footer>
      </form>
    </article>
  )
}
