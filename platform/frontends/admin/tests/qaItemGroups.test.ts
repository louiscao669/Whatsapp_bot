/// <reference types="node" />
import assert from 'node:assert/strict'
import test from 'node:test'
import { filterQuestionGroups, groupQuestions } from '../src/qaItemGroups.ts'
import type { QaItemRow } from '../src/api/qaItems.ts'

function item(id: string, changes: Partial<QaItemRow> = {}): QaItemRow {
  return {
    id, bank_id: 'sol/prepared', bank_label: 'Sol Chinese · prepared',
    passage_id: 'reviewed122_sol/Prepared60/t1_2kgs6_7', passage: '2 Kings 6:33–7:2',
    form_group_id: 'same-question', question_type: 'mcq', automatic_form: 'mcq',
    question: '谁教导乌西雅？', answer: '撒迦利亚', mcq_choices: ['母亲', '撒迦利亚', 'King'],
    mcq_correct_choice: 'B', is_current: true, created_at: '2026-11-12T00:00:00+00:00',
    review_status: 'Unreviewed', review_tab: 'unreviewed', response_count: 0,
    flagged_count: 0, average_score: null, min_responses_required: 3, review_priority: 0,
    active: false, ...changes,
  }
}

const defaults = { bank: '', query: '', scope: 'all' as const, searchHistory: false }

test('same question ID stays separate across banks, with old versions retained in history', () => {
  const rows = [item('sol'), item('old', { is_current: false }), item('original', {
    bank_id: 'reviewed/prepared', passage_id: 'reviewed122/Prepared60/t1_2kgs6_7',
  })]
  const groups = groupQuestions(rows)
  assert.equal(groups.length, 2)
  assert.deepEqual(groups[0].current.map((row) => row.id), ['sol'])
  assert.deepEqual(groups[0].history.map((row) => row.id), ['old'])
  assert.equal(filterQuestionGroups(groups, { ...defaults, bank: 'reviewed/prepared' }).length, 1)
})

test('Chinese questions, keyed answers, and distractors are searchable by field', () => {
  const groups = groupQuestions([item('sol')])
  for (const [scope, query] of [['question', '乌西雅'], ['answer', '撒迦'], ['options', '母亲']] as const) {
    assert.equal(filterQuestionGroups(groups, { ...defaults, scope, query }).length, 1)
  }
  assert.equal(filterQuestionGroups(groups, { ...defaults, scope: 'answer', query: '母亲' }).length, 0)
  assert.equal(filterQuestionGroups(groups, { ...defaults, scope: 'question', query: '母亲' }).length, 0)
})

test('normalizes full-width input, English case, and whitespace and supports combined terms', () => {
  const groups = groupQuestions([item('sol')])
  assert.equal(filterQuestionGroups(groups, { ...defaults, query: '  ＫＩＮＧ  ' }).length, 1)
  assert.equal(filterQuestionGroups(groups, { ...defaults, query: '乌西雅   撒迦利亚' }).length, 1)
  assert.equal(filterQuestionGroups(groups, { ...defaults, query: '乌西雅 unknown' }).length, 0)
})

test('previous-version-only matches require opting in and retain current row identity', () => {
  const groups = groupQuestions([item('sol'), item('old', { is_current: false, answer: 'Obsolete wording' })])
  assert.equal(filterQuestionGroups(groups, { ...defaults, query: 'obsolete' }).length, 0)
  const matches = filterQuestionGroups(groups, { ...defaults, query: 'obsolete', searchHistory: true })
  assert.equal(matches.length, 1)
  assert.equal(matches[0].current[0].id, 'sol')
  assert.equal(matches[0].matches[0].item.id, 'old')
  assert.equal(groups[0].matches.length, 0)
})

test('different passages and ungrouped records do not merge on identical wording', () => {
  assert.equal(groupQuestions([item('one'), item('two', { passage_id: 'another-passage' })]).length, 2)
  assert.equal(groupQuestions([item('one', { form_group_id: null }), item('two', { form_group_id: null })]).length, 2)
})

test('visible groups contain only matching banks and never expose history for bulk selection', () => {
  const groups = groupQuestions([item('sol'), item('old', { is_current: false }),
    item('other', { bank_id: 'other' })])
  const visible = filterQuestionGroups(groups, { ...defaults, bank: 'sol/prepared', query: '母亲' })
  assert.deepEqual(visible.flatMap((group) => group.current.map((row) => row.id)), ['sol'])
  assert.equal(filterQuestionGroups(groups, { ...defaults, query: 'no match' }).length, 0)
})
