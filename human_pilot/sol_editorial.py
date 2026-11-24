"""Explicit, user-authorized passage corrections and reversible study holds."""
ITEM = '2kgs_7_1-20/v17-18:1'
VERSE = '7:17'
REVISION = 'officer-referent-2026-11-20'
HOLD = dict(id=ITEM, status='withheld', held_from_pilot=True,
            decision_type='manual_hold', decision_date='2026-11-20',
            reason='Study owner requested a temporary hold after identifying the ambiguous '
                   'object 他 in 2 Kings 7:17. The clean passage and derived variants have '
                   'a documented manual referent clarification; the question remains excluded '
                   'until explicitly released from review.')


def clarify_verse(body):
    """Clarify the death/injury object while retaining manipulated roles and syntax."""
    role = '军官'
    head = body.split('，', 1)[0]
    for changed_role in ('使者', '士兵'):
        if changed_role in head and '军官' not in head:
            role = changed_role
    noun = '那位' + role
    for verb in ('踩死', '打死', '刺伤'):
        body = body.replace('把他' + verb, '把' + noun + verb)
    body = body.replace('踩死了他', '踩死了' + noun)
    body = body.replace('践踏他在这网关', '践踏那位军官在这网关')
    return body
