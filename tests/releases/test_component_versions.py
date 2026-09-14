"""Independent component versions must not change each other or server tags."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('versions', Path(__file__).resolve().parents[2] / 'scripts/component_versions.py')
versions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(versions)


class VersionTests(unittest.TestCase):
    def test_semantic_bumps(self):
        for part, expected in [('major', '3.0.0'), ('minor', '2.5.0'), ('patch', '2.4.7')]:
            self.assertEqual(versions.increment('2.4.6', part), expected)

    def test_reject_invalid_versions(self):
        for version in ['v1.0.0', '01.0.0', '1.2', '1.2.3\nextra', '1.2.3-dev']:
            with self.assertRaises(ValueError):
                versions.increment(version, 'patch')

    def test_bump_only_selected_component(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for component, path in versions.COMPONENTS.items():
                file = root / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('1.0.0\n')
            versions.bump(root, 'viewer', 'minor')
            self.assertEqual(versions.read(root, 'viewer'), '1.1.0')
            self.assertEqual(versions.read(root, 'models'), '1.0.0')

    def test_component_release_tags_do_not_deploy_the_server(self):
        workflow = (Path(__file__).resolve().parents[2] / '.github/workflows/release.yml').read_text()
        self.assertIn("startsWith(github.event.release.tag_name, 'v')", workflow)

    def test_component_tag_names(self):
        self.assertEqual(versions.tag_name('models', '1.0.0'), 'models/v1.0.0')
        self.assertEqual(versions.tag_name('viewer', '0.1.0'), 'viewer/v0.1.0')
