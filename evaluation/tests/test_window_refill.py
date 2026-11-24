from evaluation.scripts.pipeline.build_prepared_window_conditions import Edit, choose


def test_nested_refill_keeps_passed_lower_dose_and_excludes_overlapping_replacements():
    clean = {'1:1': '甲' * 100}
    # The longer replacement would overwrite the existing 15% edit. The new
    # compatible phrase brings the high dose within tolerance by itself.
    pool = {
        0: [Edit('1:1', 0, '甲'*15, '乙')],
        'overlap': [Edit('1:1', 10, '甲'*15, '丙')],
        'fresh': [Edit('1:1', 50, '甲'*14, '丁')],
    }
    result = choose(pool, clean, [15, 30], 2, False, conflicts=[(0, 1)],
                    fixed={15: [0]}, baseline_chars={15: 15, 30: 15})
    assert result == {15: [0], 30: [0, 'fresh']}
