import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import {
  createTestParticipant,
  fetchTestParticipantOptions,
  pilotUrl,
  type CreatedTestParticipant,
  type TestParticipantOptions,
} from '../api/participants'
import { fetchSystemLanguages } from '../api/systemLanguages'

const DEFAULT_LANGUAGE = 'zh'

export function TestParticipantPanel({ onCreated }: { onCreated: () => void }) {
  const [displayName, setDisplayName] = useState('')
  const [language, setLanguage] = useState(DEFAULT_LANGUAGE)
  const [languages, setLanguages] = useState<string[]>([DEFAULT_LANGUAGE])
  const [buildPlan, setBuildPlan] = useState(true)
  const [qaSets, setQaSets] = useState<TestParticipantOptions['qa_sets']>([])
  const [qaSet, setQaSet] = useState('')
  const [whTypeOptions, setWhTypeOptions] = useState<string[]>([])
  const [whTypes, setWhTypes] = useState<string[]>([])
  // Plan conditions to keep (none ticked = all). Adequacy/fluency are shortcuts that
  // tick their conditions; what is sent is always the condition list.
  const [dimensionOptions, setDimensionOptions] = useState<Record<string, string[]>>({})
  const [conditionOptions, setConditionOptions] = useState<{ key: string; label: string }[]>([])
  const [conditions, setConditions] = useState<string[]>([])
  // Test participants answer MCQ only unless this is unticked (server default too).
  const [mcqOnly, setMcqOnly] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [created, setCreated] = useState<CreatedTestParticipant | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    fetchSystemLanguages()
      .then(({ languages: options }) =>
        setLanguages(Array.from(new Set([DEFAULT_LANGUAGE, ...options])).sort()),
      )
      .catch(() => undefined) // the default language still works
    fetchTestParticipantOptions()
      .then((options) => {
        setQaSets(options.qa_sets)
        setWhTypeOptions(options.wh_types ?? [])
        setDimensionOptions(options.quality_dimensions ?? {})
        setConditionOptions(options.conditions ?? [])
        const keys = options.qa_sets.map((set) => set.key)
        setQaSet(keys.includes(options.default_qa_set) ? options.default_qa_set : keys[0] ?? '')
      })
      .catch(() => undefined) // the server falls back to its default set
  }, [])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    setCreated(null)
    setCopied(false)
    try {
      const result = await createTestParticipant({
        display_name: displayName,
        language,
        build_plan: buildPlan,
        qa_set: buildPlan && qaSet ? qaSet : undefined,
        wh_types: buildPlan && whTypes.length ? whTypes : undefined,
        question_forms: mcqOnly ? ['mcq'] : ['mcq', 'open'],
        conditions: buildPlan && conditions.length ? conditions : undefined,
      })
      setCreated(result)
      setDisplayName('')
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create test participant')
    } finally {
      setSubmitting(false)
    }
  }

  async function copyLink(url: string) {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  const link = created?.pilot_path ? pilotUrl(created.participant_id) : ''
  const selectedSet = qaSets.find((set) => set.key === qaSet)
  const whCounts = (mcqOnly ? selectedSet?.mcq_wh_counts : selectedSet?.wh_counts) ?? {}
  const whSelectedCount = whTypes.reduce((sum, type) => sum + (whCounts[type] ?? 0), 0)

  function toggleWhType(type: string, checked: boolean) {
    setWhTypes((current) =>
      checked ? [...current.filter((t) => t !== type), type] : current.filter((t) => t !== type),
    )
  }

  function toggleCondition(key: string, checked: boolean) {
    setConditions((current) =>
      checked ? [...current.filter((c) => c !== key), key] : current.filter((c) => c !== key),
    )
  }

  const dimensionNames = Object.keys(dimensionOptions)
  const dimensionTicked = (name: string) =>
    (dimensionOptions[name] ?? []).every((c) => conditions.includes(c))

  // Ticking a dimension adds its conditions; unticking removes them, except ones that
  // another still-ticked dimension also needs (the shared clean anchors).
  function toggleDimension(name: string, checked: boolean) {
    const own = dimensionOptions[name] ?? []
    setConditions((current) => {
      if (checked) return Array.from(new Set([...current, ...own]))
      const keep = new Set(
        dimensionNames
          .filter((other) => other !== name && dimensionTicked(other))
          .flatMap((other) => dimensionOptions[other] ?? []),
      )
      return current.filter((c) => !own.includes(c) || keep.has(c))
    })
  }

  const orderedConditions = conditionOptions
    .map((option) => option.key)
    .filter((key) => conditions.includes(key))
  const keptGroupCount = orderedConditions.reduce((n, c) => n + (c === 'clean' ? 2 : 1), 0)

  return (
    <details className="detail-card test-participant-panel">
      <summary>Create test participant</summary>
      <p className="hint">
        Creates a participant flagged as <strong>TEST</strong> with its own pilot plan, so you
        can walk through <code>/pilot</code> as a participant would. Test participants are
        skipped by <code>build_experiment_plan.py --all-consented</code> and the pilot
        exports, and can be deleted from their detail page.
      </p>
      <form className="mutation-form" onSubmit={handleSubmit}>
        <label htmlFor="test-participant-name">Name (optional)</label>
        <input
          id="test-participant-name"
          type="text"
          value={displayName}
          placeholder="e.g. gold72 walkthrough"
          onChange={(event) => setDisplayName(event.target.value)}
          maxLength={200}
        />
        <label htmlFor="test-participant-language">Language</label>
        <select
          id="test-participant-language"
          value={language}
          onChange={(event) => setLanguage(event.target.value)}
        >
          {languages.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <label htmlFor="test-participant-qa-set">Question set</label>
        <select
          id="test-participant-qa-set"
          value={qaSet}
          disabled={!buildPlan || qaSets.length === 0}
          onChange={(event) => {
            setQaSet(event.target.value)
            setWhTypes([])
          }}
        >
          {qaSets.length === 0 ? <option value="">No question set imported</option> : null}
          {qaSets.map((set) => (
            <option key={set.key} value={set.key}>
              {set.label} — {set.windows} questions
            </option>
          ))}
        </select>
        {whTypeOptions.length ? (
          <fieldset className="wh-type-options" disabled={!buildPlan || !qaSet}>
            <legend>Question types (none ticked = all)</legend>
            {whTypeOptions.map((type) => (
              <label key={type} className="checkbox-label">
                <input
                  type="checkbox"
                  checked={whTypes.includes(type)}
                  disabled={!whCounts[type] && !whTypes.includes(type)}
                  onChange={(event) => toggleWhType(type, event.target.checked)}
                />
                {type} ({whCounts[type] ?? 0})
              </label>
            ))}
            {whTypes.length ? (
              <p className="hint">
                Only {whTypes.join('/')} questions: {whSelectedCount} in this set. Conditions
                whose window group has none are skipped, so the Latin square is incomplete.
              </p>
            ) : null}
          </fieldset>
        ) : null}
        {conditionOptions.length ? (
          <fieldset className="wh-type-options" disabled={!buildPlan}>
            <legend>Passage conditions (none ticked = all)</legend>
            {dimensionNames.length ? (
              <p className="hint">
                Shortcuts:{' '}
                {dimensionNames.map((name) => (
                  <label key={name} className="checkbox-label inline-checkbox">
                    <input
                      type="checkbox"
                      checked={dimensionTicked(name)}
                      onChange={(event) => toggleDimension(name, event.target.checked)}
                    />
                    {name}
                  </label>
                ))}
              </p>
            ) : null}
            {conditionOptions.map((option) => (
              <label key={option.key} className="checkbox-label">
                <input
                  type="checkbox"
                  checked={conditions.includes(option.key)}
                  onChange={(event) => toggleCondition(option.key, event.target.checked)}
                />
                {option.label}
              </label>
            ))}
            {orderedConditions.length ? (
              <p className="hint">
                Only {orderedConditions.join(', ')}: the plan keeps those conditions'
                window groups ({keptGroupCount} of 8) and drops the rest.
              </p>
            ) : null}
          </fieldset>
        ) : null}
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={mcqOnly}
            onChange={(event) => setMcqOnly(event.target.checked)}
          />
          Multiple-choice questions only (skip open-ended)
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={buildPlan}
            onChange={(event) => setBuildPlan(event.target.checked)}
          />
          Build pilot plan (8 conditions, Latin square)
        </label>
        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Creating…' : 'Create test participant'}
        </button>
      </form>
      {error ? <p className="error-message">{error}</p> : null}
      {created ? (
        <div className="test-participant-result">
          <p className="success-message">
            Created{' '}
            <Link to={`/participants/${created.participant_id}`}>{created.display_name}</Link>
            {created.qa_set ? ` on ${created.qa_set}` : ''}
            {created.wh_types?.length
              ? `, ${created.wh_types.join('/')} questions only (${created.wh_question_count ?? 0})`
              : ''}
            {created.conditions?.length
              ? `, ${created.conditions.join('/')} only (${created.plan.length} groups)`
              : ''}
            {created.question_forms?.length === 1 ? `, ${created.question_forms[0].toUpperCase()} only` : ''}
            {created.block_index !== null ? ` (slot rotation ${created.block_index})` : ''}.
          </p>
          {link ? (
            <p className="test-participant-link">
              <a href={link} target="_blank" rel="noreferrer">
                {link}
              </a>{' '}
              <button type="button" className="btn-secondary btn-sm" onClick={() => copyLink(link)}>
                {copied ? 'Copied' : 'Copy link'}
              </button>
            </p>
          ) : (
            <p className="hint">No plan was built, so there is no pilot link yet.</p>
          )}
          {created.plan.length ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Window group</th>
                    <th>Condition</th>
                  </tr>
                </thead>
                <tbody>
                  {created.plan.map((cell) => (
                    <tr key={cell.sequence_index}>
                      <td>{cell.sequence_index + 1}</td>
                      <td>{cell.group}</td>
                      <td>{cell.condition}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </details>
  )
}
