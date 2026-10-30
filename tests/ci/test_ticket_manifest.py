"""Exercise ticket attribution with the real compatibility validator."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class TicketManifestTests(unittest.TestCase):
    def validate(self, ticket):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            (root / "scripts").mkdir()
            (root / ".nakama").mkdir()
            shutil.copyfile(ROOT / "scripts/validate-upstream-compatibility.sh", root / "scripts/validate-upstream-compatibility.sh")
            (root / "go.mod").write_text("module github.com/openfga/openfga\n")
            (root / "LICENSE").write_text("Apache License\n")
            for command in (["git", "init", "-q"], ["git", "add", "."], ["git", "-c", "user.name=Test Maintainer", "-c", "user.email=maintainer@example.org", "commit", "-qm", "baseline"], ["git", "update-ref", "refs/remotes/origin/main", "HEAD"]):
                subprocess.run(command, cwd=root, check=True, capture_output=True)
            (root / ".nakama/upstream-divergences.toml").write_text(f'[[approved_path]]\npath = "policy.txt"\nissue = "{ticket}"\n[[approved_path]]\npath = ".nakama/upstream-divergences.toml"\nissue = "{ticket}"\n')
            (root / "policy.txt").write_text("policy\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "-c", "user.name=Test Maintainer", "-c", "user.email=maintainer@example.org", "commit", "-qm", "policy"], cwd=root, check=True, capture_output=True)
            return subprocess.run(["bash", "scripts/validate-upstream-compatibility.sh"], cwd=root, capture_output=True, text=True)

    def test_accepts_different_team_keys(self):
        for ticket in ("NAK-123", "DOC-123", "ABC-123", "QA2-123", "Z-1"):
            with self.subTest(ticket=ticket):
                result = self.validate(ticket)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_requires_well_formed_ticket(self):
        for ticket in ("", "NAK-0", "ABC-01", "ABC-x", "ABC-1suffix", "ÅBC-123"):
            with self.subTest(ticket=ticket):
                self.assertNotEqual(self.validate(ticket).returncode, 0)


if __name__ == "__main__":
    unittest.main()
