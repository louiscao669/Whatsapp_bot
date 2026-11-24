from evaluation.scripts.pipeline.build_prepared_window_conditions import Edit
from evaluation.scripts.pipeline.match_window_defects import DOSES, place


def toy_window(mis_weights):
    parts = ['甲'*15, '乙'*15, '丙'*15, '丁'*15, '戊'*40]
    clean = ''.join(parts)
    clauses = [Edit('1', i*15, part, '') for i, part in enumerate(parts)]
    groups = {
        'omission': {i: [e] for i, e in enumerate(clauses)},
        'grammar': {i: [Edit('1', i*15, parts[i], '工'+parts[i][1:])] for i in (0, 1)},
        'mistranslation': {i: [Edit('1', i*15, parts[i][:size], '人')] for i, size in enumerate(mis_weights)},
    }
    conditions = {family+str(d): {'status': 'within_target'} for family, doses in DOSES.items() for d in doses}
    conditions['clean'] = {'verses': {'1': clean}}
    window = dict(id='test', clean_content_chars=100, conditions=conditions)
    return window, groups, [Edit('1', 0, '甲', '')]


def test_joint_placement_can_match_clauses_with_different_covered_characters():
    w, groups, evidence = toy_window([14, 14])
    plan, feasible = place(w, groups, evidence, 2, 77)
    assert feasible == {'15': True, '30': True}
    assert plan['mistranslation30'] == plan['omission30'] == plan['grammar30'] == [0, 1]
    assert plan['mistranslation15'] == plan['omission15']
    assert set(plan['omission15']) < set(plan['omission30'])
    assert (plan, feasible) == place(w, groups, evidence, 2, 77)


def test_reviewed_phrases_can_require_more_clauses_at_the_same_dose():
    w, groups, evidence = toy_window([7, 8, 7, 8])
    plan, feasible = place(w, groups, evidence, 2, 77)
    assert feasible == {'15': False, '30': False}
    assert len(plan['mistranslation30']) == 4
    assert len(plan['omission30']) == len(plan['grammar30']) == 2
    assert set(plan['omission30']) & set(plan['grammar30']) & set(plan['mistranslation30'])
