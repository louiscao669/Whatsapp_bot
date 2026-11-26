import type { QaItemRow } from './api/qaItems'

export type SearchScope = 'all' | 'question' | 'answer' | 'options'
export type SearchMatch = { item: QaItemRow; label: string; text: string }
export type QuestionGroup = {
  key: string
  current: QaItemRow[]
  history: QaItemRow[]
  matches: SearchMatch[]
}

function normalize(text: string) {
  return text.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g, ' ').trim()
}

function searchFields(item: QaItemRow, scope: SearchScope) {
  const fields = []
  if (scope === 'all' || scope === 'question') fields.push({ label: 'Question', text: item.question })
  if (scope === 'all' || scope === 'answer') fields.push({ label: 'Answer', text: item.answer })
  if (scope === 'all' || scope === 'options') {
    fields.push(...item.mcq_choices.map((text, index) => ({
      label: `Option ${String.fromCharCode(65 + index)}`, text,
    })))
  }
  return fields
}

export function groupQuestions(items: QaItemRow[]): QuestionGroup[] {
  const groups = new Map<string, QuestionGroup>()
  for (const item of items) {
    const key = JSON.stringify([item.bank_id, item.passage_id, item.form_group_id || item.id, item.question_type])
    const group: QuestionGroup = groups.get(key) || { key, current: [], history: [], matches: [] }
    if (item.is_current) group.current.push(item)
    else group.history.push(item)
    groups.set(key, group)
  }
  for (const group of groups.values()) {
    group.current.sort((a, b) => a.question_type.localeCompare(b.question_type))
    group.history.sort((a, b) => b.created_at.localeCompare(a.created_at))
  }
  // Keep distinct current records individually navigable, even when multiple
  // delivery windows point to revisions with the same form group and type.
  return Array.from(groups.values()).flatMap((group) => {
    if (group.current.length <= 1) return [group]
    const current = [...group.current].sort((a, b) =>
      b.created_at.localeCompare(a.created_at) || a.id.localeCompare(b.id))
    return current.map((item, index) => ({
      ...group,
      key: JSON.stringify([group.key, item.id]),
      current: [item],
      // Count and display older revisions once, alongside the newest record.
      history: index === 0 ? group.history : [],
    }))
  })
}

export function filterQuestionGroups(
  groups: QuestionGroup[],
  { bank, query, scope, searchHistory }: {
    bank: string; query: string; scope: SearchScope; searchHistory: boolean
  },
): QuestionGroup[] {
  const terms = normalize(query).split(' ').filter(Boolean)
  return groups.flatMap((group) => {
    if (bank && group.current[0]?.bank_id !== bank) return []
    if (!terms.length) return [group]
    const candidates = searchHistory ? [...group.current, ...group.history] : group.current
    const matches = candidates.flatMap((item) => {
      const fields = searchFields(item, scope)
      if (!terms.every((term) => fields.some((field) => normalize(field.text).includes(term)))) return []
      return fields.filter((field) => terms.some((term) => normalize(field.text).includes(term)))
        .map((field) => ({ item, ...field }))
    })
    return matches.length ? [{ ...group, matches }] : []
  })
}
