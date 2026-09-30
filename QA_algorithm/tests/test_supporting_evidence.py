import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[1] / 'scripts/anchor_irt/build_tier1_verse_windows.py'
spec = importlib.util.spec_from_file_location('windows', PATH)
windows = importlib.util.module_from_spec(spec)
spec.loader.exec_module(windows)


class EvidenceWindowsTest(unittest.TestCase):
    def test_build_prefers_verified_evidence_and_rejects_invalid_quotes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            passage = root / 'fixtures/passages/tier1/2kgs_6_24-7_20.txt'
            passage.parent.mkdir(parents=True)
            passage.write_text('3 Four men waited. 4 If we stay, we will die. 5 They went. 6 They found food.')
            (root / 'fixtures/obscure_narrative_passages_tier1.csv').write_text(
                'id,reference,chapter_start,verse_start,chapter_end,verse_end\nt1_2kgs6_7,2 Kings 7:3-6,7,3,7,6\n')
            record = dict(passage_id='t1_2kgs6_7', question='Why go?', answer='They might die.', reference='7:3',
                          supporting_verse_ids=['7:4'], supporting_evidence=[dict(verse_id='7:4', text='we will die')])
            qa_file = root / 'qa.json'
            qa_file.write_text(json.dumps([record]))
            legacy = {windows.span_key('t1_2kgs6_7', 'Why go?'): {'required_span': ['7:3']}}
            result, missing = windows.build(qa_root=root, qa_file=qa_file, spans=legacy, seed=1)
            self.assertFalse(missing)
            self.assertEqual(result['windows'][0]['required_span'], ['7:4'])
            self.assertEqual(result['span_source'], 'qa_supporting_evidence')
            self.assertFalse(windows.verify(result, root, qa_file))
            record['supporting_evidence'][0]['text'] = 'not in the passage'
            qa_file.write_text(json.dumps([record]))
            result, _ = windows.build(qa_root=root, qa_file=qa_file, spans=legacy, seed=1)
            self.assertEqual(result['windows'], [])
            self.assertEqual(result['excluded'][0]['reason'], 'invalid_supporting_evidence')
            record.pop('supporting_verse_ids'); record.pop('supporting_evidence')
            qa_file.write_text(json.dumps([record]))
            result, _ = windows.build(qa_root=root, qa_file=qa_file, spans=legacy, seed=1)
            self.assertEqual(result['windows'][0]['required_span'], ['7:3'])

    def test_noncontiguous_evidence_includes_intervening_verses(self):
        verse_text = {'6:33': 'first', '7:1': 'middle', '7:2': 'last'}
        ann = windows.evidence_annotation({'supporting_verse_ids': ['7:2', '6:33'],
            'supporting_evidence': [{'verse_id': '7:2', 'text': 'last'}, {'verse_id': '6:33', 'text': 'first'}]}, verse_text)
        self.assertEqual(ann['required_span'], list(verse_text))
        self.assertEqual(windows.candidate_windows(list(verse_text), ann['required_span']), [list(verse_text)])

    def test_oversized_span_has_no_window(self):
        self.assertEqual(windows.candidate_windows(['1:1', '1:2', '1:3', '1:4'], ['1:1', '1:4']), [])

if __name__ == '__main__':
    unittest.main()
