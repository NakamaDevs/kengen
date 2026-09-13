"""Review Trivy dependency findings under the NAK-911 policy."""
REVIEWED_MPL = {
    "github.com/go-sql-driver/mysql": "v1.10.0",
    "github.com/hashicorp/go-retryablehttp": "v0.7.8",
    "github.com/hashicorp/go-cleanhttp": "v0.5.2",
}
NOTICE_LICENSES = {"Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MIT"}


def _evaluate(report):
    if report.get("SchemaVersion") != 2 or report.get("ArtifactType") != "filesystem":
        return ["Unsupported dependency report format."]
    results = report.get("Results")
    if not isinstance(results, list) or not results:
        return ["Dependency report has no results."]
    packages = {}
    failures = []
    license_count = 0
    for result in results:
        vulnerabilities = result.get("Vulnerabilities", [])
        if not isinstance(vulnerabilities, list):
            return ["Invalid vulnerability results."]
        if vulnerabilities:
            failures.append("Unresolved vulnerabilities in " + result["Target"])
        if result.get("Class") == "lang-pkgs" and result.get("Type") == "gomod" and result.get("Target") == "go.mod":
            for package in result.get("Packages", []):
                packages.setdefault(package["Name"], []).append(package.get("Version"))
    if not packages:
        return ["Root Go package inventory is missing."]
    for result in results:
        licenses = result.get("Licenses", [])
        if result.get("Class") == "license" and result.get("Target") != "go.mod":
            failures.append("Unreviewed license target: " + result["Target"])
        for finding in licenses:
            license_count += 1
            name = finding["Name"]
            package = finding["PkgName"]
            versions = packages.get(package, [])
            exact_package = len(versions) == 1 and isinstance(versions[0], str) and bool(versions[0])
            trusted_finding = (result.get("Class") == "license" and result.get("Target") == "go.mod"
                               and finding.get("FilePath") == "go.mod" and finding.get("Confidence") == 1)
            notice = (name in NOTICE_LICENSES and finding.get("Category") == "notice" and finding.get("Severity") == "LOW")
            inherited = (exact_package and name == "MPL-2.0" and finding.get("Category") == "reciprocal"
                         and finding.get("Severity") == "MEDIUM" and REVIEWED_MPL.get(package) == versions[0])
            if not (exact_package and trusted_finding and (notice or inherited)):
                failures.append("License review required: " + package + " (" + name + ")")
    if not license_count:
        failures.append("License findings are missing.")
    return failures


def evaluate(report):
    """Reject malformed reports, vulnerabilities, and findings outside the policy."""
    try:
        return _evaluate(report)
    except (AttributeError, KeyError, TypeError, ValueError):
        return ["Malformed dependency report."]


def main():
    import argparse
    import json
    import os
    from pathlib import Path
    import subprocess
    import tempfile

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Review an existing Trivy JSON report.")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="kengen-dependencies-") as folder:
        report_path = args.report
        if report_path is None:
            report_path = Path(folder) / "report.json"
            config_path = Path(folder) / "trivy.yaml"
            config_path.write_text("{}\n")
            # Keep ambient Trivy filters from silently omitting findings.
            env = {k: v for k, v in os.environ.items() if not k.startswith("TRIVY_")}
            subprocess.run(["trivy", "--config", str(config_path), "fs", "--scanners", "vuln,license",
                            "--format", "json", "--list-all-pkgs", "--ignorefile", os.devnull,
                            "--ignore-policy", "", "--output", str(report_path), "--quiet", "."],
                           env=env, check=True)
        try:
            failures = evaluate(json.loads(report_path.read_text()))
        except (OSError, ValueError):
            failures = ["Cannot read the dependency report."]
        for failure in failures:
            print(failure)
        if failures:
            return 1
        print("Dependency review passed: no vulnerabilities or unreviewed license findings.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
