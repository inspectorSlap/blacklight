import ast
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import build_fixtures, build_registry, roster, runner, selfqual, simulation
from harness.checks import anchor_checks
from harness.targets import SoundReferenceTarget, MutantTarget


class ExtractionTests(unittest.TestCase):
    def test_historical_approval_is_not_inherited(self):
        self.assertEqual(build_registry.OPERATOR_APPROVAL['status'], 'PENDING')
        self.assertIsNone(build_registry.OPERATOR_APPROVAL['approved_at'])
        self.assertEqual(build_registry.OPERATOR_APPROVAL['decisions'], {})

    def test_reference_has_no_oracle_checker_or_mutant_imports(self):
        for path in (ROOT / 'harness/reference').glob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level:
                    self.assertEqual(node.level, 1, path.name)
                    self.assertIn(node.module, (None, 'interval', 'archive'), path.name)
                names = [a.name for a in node.names] if isinstance(node, (ast.Import, ast.ImportFrom)) else []
                self.assertFalse(any(n.startswith(('harness.oracle', 'harness.checks', 'harness.mutants')) for n in names), path.name)

    def test_exact_oracle_matches_all_retained_anchors(self):
        findings, count = anchor_checks.verify_oracle(anchor_checks.load_anchors())
        self.assertEqual(count, 57)
        self.assertFalse(selfqual._fails(findings))

    def test_blocked_is_not_a_pass(self):
        self.assertEqual(len(selfqual._fails([{'severity': 'BLOCKED'}])), 1)

    def test_synthetic_roster_rejects_reordering(self):
        panel = build_fixtures.build_clean_panel()
        payload = panel[0]['payload']
        self.assertTrue(roster.assert_payload(payload))
        payload['lights'][0]['semantic_specimens'].reverse()
        with self.assertRaises(roster.RosterViolation):
            roster.assert_payload(payload)

    def test_simulation_payload_reproduces_from_coordinates(self):
        cell = simulation.build_grid()[0]
        first = simulation.build_payload(cell, 8, 0)
        self.assertEqual(first, simulation.build_payload(cell, 8, 0))
        self.assertNotEqual(first, simulation.build_payload(cell, 8, 1))

    def test_clean_reference_clears_sample_scenario(self):
        scenario = build_fixtures.build_clean_panel()[0]
        self.assertFalse(selfqual._fails(runner.run_analysis_scenario(SoundReferenceTarget(), scenario, strict=True)))

    def test_cli_cannot_enable_external_execution(self):
        for command in ('campaign', 'ordered-dryrun'):
            p = subprocess.run([sys.executable, '-m', 'harness.cli', command], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn('NOT_IMPLEMENTED', p.stderr)

    def test_demo_refuses_existing_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'keep.txt'
            marker.write_text('retain')
            p = subprocess.run([sys.executable, '-m', 'harness.cli', 'demo', '--workspace', directory], cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn('already exists', p.stderr)
            self.assertEqual(marker.read_text(), 'retain')

    def test_archived_supervisor_cannot_execute(self):
        p = subprocess.run([sys.executable, str(ROOT / 'incubator/operations/supervisor.py'), 'start'], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('Design archive only', p.stderr)

    def test_export_scan_and_canary(self):
        spec = importlib.util.spec_from_file_location('audit_export', ROOT / 'scripts/audit_export.py')
        scanner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scanner)
        self.assertEqual(scanner.audit(ROOT), [])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'bad.txt').write_text('/Use' + 'rs/private-person/notes')
            self.assertTrue(scanner.audit(root))

if __name__ == '__main__':
    unittest.main()
