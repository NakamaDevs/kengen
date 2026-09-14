"""Regression tests for the dependency review boundary."""
import copy
import json
import os
import subprocess
import sys
from unittest.mock import patch
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("policy", Path(__file__).resolve().parents[2] / "scripts/review_dependencies.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def report():
    return {"SchemaVersion": 2, "ArtifactType": "filesystem", "Results": [
        {"Target": "go.mod", "Class": "lang-pkgs", "Type": "gomod", "Packages": [
            {"Name": "github.com/hashicorp/go-cleanhttp", "Version": "v0.5.2"}]},
        {"Target": "go.mod", "Class": "license", "Licenses": [
            {"PkgName": "github.com/hashicorp/go-cleanhttp", "FilePath": "go.mod", "Name": "MPL-2.0", "Category": "reciprocal", "Severity": "MEDIUM", "Confidence": 1}]}]}


class PolicyTests(unittest.TestCase):
    def test_exact_inherited_version(self):
        self.assertEqual(policy.evaluate(report()), [])

    def test_each_inherited_module(self):
        for name, version in policy.REVIEWED_MPL.items():
            data = report()
            data["Results"][0]["Packages"][0].update(Name=name, Version=version)
            data["Results"][1]["Licenses"][0]["PkgName"] = name
            self.assertEqual(policy.evaluate(data), [])

    def test_new_versions_and_modules_fail(self):
        for name, version in [("github.com/hashicorp/go-cleanhttp", "v0.5.3"), ("example.test/new-module", "v0.5.2")]:
            data = report()
            data["Results"][0]["Packages"][0].update(Name=name, Version=version)
            data["Results"][1]["Licenses"][0]["PkgName"] = name
            self.assertTrue(policy.evaluate(data))

    def test_vulnerabilities_are_never_waived(self):
        for severity in ["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]:
            data = report()
            data["Results"][0]["Vulnerabilities"] = [{"VulnerabilityID": "TEST-VULNERABILITY", "Severity": severity}]
            self.assertTrue(policy.evaluate(data))

    def test_notice_licenses(self):
        for name in policy.NOTICE_LICENSES:
            data = report()
            data["Results"][1]["Licenses"][0].update(Name=name, Category="notice", Severity="LOW")
            self.assertEqual(policy.evaluate(data), [])

    def test_unknown_and_changed_findings_fail(self):
        for change in [{"Name": "GPL-3.0-only"}, {"Name": "UNKNOWN"}, {"Category": "restricted"}, {"Severity": "HIGH"}, {"Confidence": 0.5}, {"FilePath": "vendor/LICENSE"}]:
            data = report()
            data["Results"][1]["Licenses"][0].update(change)
            self.assertTrue(policy.evaluate(data))

    def test_missing_or_ambiguous_package_version_fails(self):
        for packages in [[], [{"Name": "github.com/hashicorp/go-cleanhttp"}], [
            {"Name": "github.com/hashicorp/go-cleanhttp", "Version": "v0.5.2"},
            {"Name": "github.com/hashicorp/go-cleanhttp", "Version": "v0.5.3"}]]:
            data = report()
            data["Results"][0]["Packages"] = packages
            self.assertTrue(policy.evaluate(data))

    def test_malformed_and_empty_report_fails(self):
        for data in [{}, [], {"SchemaVersion": 2, "Results": []}, {"SchemaVersion": 3, "Results": report()["Results"]}]:
            self.assertTrue(policy.evaluate(data))

    def test_extra_targets_are_checked(self):
        data = report()
        extra = copy.deepcopy(data["Results"][1])
        extra["Target"] = "other/go.mod"
        data["Results"].append(extra)
        self.assertTrue(policy.evaluate(data))

    def test_scanner_cannot_inherit_filters(self):
        def scan(args, env, check):
            self.assertTrue(check)
            self.assertFalse(any(k.startswith("TRIVY_") for k in env))
            self.assertEqual(args[args.index("--scanners") + 1], "vuln,license")
            self.assertEqual(args[args.index("--ignorefile") + 1], os.devnull)
            self.assertEqual(args[args.index("--ignore-policy") + 1], "")
            self.assertEqual(Path(args[args.index("--config") + 1]).read_text(), "{}\n")
            Path(args[args.index("--output") + 1]).write_text(json.dumps(report()))
        with patch.dict(os.environ, {"TRIVY_SEVERITY": "CRITICAL", "TRIVY_SKIP_FILES": "go.mod"}), patch.object(sys, "argv", ["review_dependencies.py"]), patch.object(subprocess, "run", side_effect=scan):
            self.assertEqual(policy.main(), 0)

    def test_scanner_failure_fails(self):
        with patch.object(sys, "argv", ["review_dependencies.py"]), patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(1, "trivy")):
            with self.assertRaises(subprocess.CalledProcessError):
                policy.main()

    def test_missing_license_results_fail(self):
        data = report()
        data["Results"].pop()
        self.assertTrue(policy.evaluate(data))


if __name__ == "__main__":
    unittest.main()
