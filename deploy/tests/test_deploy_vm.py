import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('deploy_vm', Path(__file__).resolve().parents[1]/'deploy_vm.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeploymentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in deploy.REQUIRED:
            self.add(name)
        self.manifest = self.root/'allowlist.txt'
        self.manifest.write_text('\n'.join(deploy.REQUIRED))

    def add(self, name):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')
        return path

    def test_runtime_files_present_and_secrets_data_caches_absent(self):
        bad = ['platform/backend/.env.backup', 'message-bot/app/participants.csv',
               'platform/backend/__pycache__/app.pyc', 'platform/backend/tests/test_api.py',
               'platform/backend/uploads/user.wav', 'platform/backend/session.sqlite3',
               'platform/frontends/admin/dist/assets/main.js.map']
        for name in bad:
            self.add(name)
        self.add('platform/backend/new_runtime.py')
        with self.manifest.open('a') as f:
            f.write('\nplatform/backend/**/*\nmessage-bot/app/**/*\n')
        # The messaging wildcard needs an actual permitted runtime file.
        self.add('message-bot/app/__init__.py')
        selected = {p.as_posix() for p in deploy.select_files(self.root, self.manifest)}
        self.assertTrue(set(deploy.REQUIRED) <= selected)
        self.assertIn('platform/backend/new_runtime.py', selected)
        self.assertFalse(set(bad) & selected)

    def test_deployment_datasets_allowed_but_results_and_participant_data_blocked(self):
        good = ['evaluation/datasets/passages/tier1_bsb/acts_20_7-12.txt',
                'evaluation/datasets/qa/tier1_gold72_canonical_5opt/t1_acts20_all_formats.json',
                'evaluation/datasets/qa/tier1_hard66_canonical/t1_acts20.json',
                deploy.DATA_CSV, 'QA_algorithm/inputs/tier1_qa_verse_windows_canonical.json']
        bad = ['evaluation/outputs/results.json', 'evaluation/datasets/participants.csv',
               'evaluation/datasets/qa/tier1_hard66_canonical/t1_acts20.json.bak_overlap_2026-09-30',
               'evaluation/datasets/qa/tier1_gold72_canonical_5opt/t1_acts20_all_formats.json.prestemfix']
        for name in good + bad:
            self.add(name)
        with self.manifest.open('a') as f:
            f.write('\nevaluation/**/*\nQA_algorithm/inputs/*.json\n')
        selected = {p.as_posix() for p in deploy.select_files(self.root, self.manifest)}
        self.assertTrue(set(good) <= selected)
        self.assertFalse(set(bad) & selected)

    def test_missing_runtime_fails_closed(self):
        (self.root/deploy.REQUIRED[0]).unlink()
        with self.assertRaises(ValueError):
            deploy.select_files(self.root, self.manifest)

    def test_symlink_and_parent_traversal_rejected(self):
        link = self.root/'platform/backend/linked.py'
        link.symlink_to(self.root/'config.py')
        original = self.manifest.read_text()
        for entry in ['platform/backend/linked.py', '../outside.py', '/etc/passwd']:
            self.manifest.write_text(original+'\n'+entry)
            with self.assertRaises(ValueError):
                deploy.select_files(self.root, self.manifest)

    def test_transfer_defaults_to_preview_without_deletions(self):
        target = deploy.destination('user@vm', '/opt/eten-whatsapp-bot')
        preview = deploy.transfer_command(self.root, target, apply=False)
        self.assertIn('--dry-run', preview)
        actual = deploy.transfer_command(self.root, target, apply=True)
        self.assertNotIn('--dry-run', actual)
        self.assertFalse(any(s.startswith('--delete') for s in actual))
        for host, directory in [('vm;touch bad', '/opt/app'), ('vm', '/'), ('vm', '/opt/../etc')]:
            with self.assertRaises(ValueError):
                deploy.destination(host, directory)

if __name__ == '__main__':
    unittest.main()
