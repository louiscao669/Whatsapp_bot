"""Explicit user review decisions; model evidence remains separately recorded."""
from copy import deepcopy

POLICY = 'grammar_user_adjudications_v1'
DECISIONS = ({
    'id': '2026-11-23-lion-corpse',
    'date': '2026-11-23',
    'authority': 'user',
    'user_instruction': '狮子尸体 should be rejected',
    'verdict': 'reject',
    'reason_code': 'corpse_referent_changed',
    'before': '驴和狮子都站在尸体旁边。',
    'after': '驴和狮子尸体旁边站在都。',
    'reason': 'Rejected by user: 狮子尸体 introduces a lion-corpse reading; '
              'the source describes the donkey and living lion beside the man’s body.',
    'manual_wording': False,
}, {
    'id': '2026-11-23-micah-arriver',
    'date': '2026-11-23',
    'authority': 'user',
    'user_instruction': 'yes reject this as well',
    'verdict': 'reject',
    'reason_code': 'arrival_participant_ambiguity',
    'before': '来到米迦的家。',
    'after': '米迦的来到家。',
    'reason': 'Rejected by user: 米迦的来到家 allows a reading in which Micah '
              'comes home; the source describes the Danites arriving at Micah’s house.',
    'manual_wording': False,
}, {
    'id': '2026-11-23-possessive-speaker',
    'date': '2026-11-23',
    'authority': 'user',
    'user_instruction': 'okay remove it, can apply repair to it agian',
    'verdict': 'reject',
    'reason_code': 'possessive_speaker_category_disagreement',
    'before': '我对她说：',
    'after': '我的对她说：',
    'reason': 'Rejected by user after reviewing the complete 2 Kings 6:29–31 draft: '
              'the grammar and meaning reviewers disagree over whether 我的 is '
              'an invalid word form or an elliptical possessive subject. Exclude '
              'this edit without treating a speaker change as established.',
    'manual_wording': False,
}, {
    'id': '2026-11-23-collective-speech-noun',
    'date': '2026-11-23',
    'authority': 'user',
    'user_instruction': '说 → 话语 remove this one and try to repair it',
    'verdict': 'reject',
    'reason_code': 'speech_noun_category_disagreement',
    'before': '因为众人说：',
    'after': '因为众人话语：',
    'reason': 'Rejected by user after the 2 Chronicles 26:21–23 editorial hold: '
              'reviewers disagree over whether 众人话语 is an invalid predicate '
              'or a noun phrase giving a reason. Exclude this exact edit from '
              'all doses rather than retain the unresolved grammar classification.',
    'manual_wording': False,
},)


def decisions_for(edit):
    """Match the source/edit pair, never ban a phrase in unrelated clean text."""
    return [deepcopy(d) for d in DECISIONS
            if edit.get('before') == d['before'] and edit.get('after') == d['after']]


def eligible(candidate):
    # Old cached approvals must not bypass a later user rejection.
    return candidate['status'] == 'pass' and not decisions_for(candidate)


def apply_review(review, edits):
    decisions = {d['id']: d for edit in edits for d in decisions_for(edit)}
    if not decisions:
        return review
    return dict(review, model_status=review.get('model_status', review['status']),
                status='needs_repair', manual_adjudications=list(decisions.values()))


def apply_candidate(candidate):
    return apply_review(candidate, [candidate])
