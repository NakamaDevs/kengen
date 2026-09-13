"""Offline deployment contract tests. No production credentials or Docker required."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("deploy", Path(__file__).with_name("deploy.py"))
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

DIGEST = "localhost:5050/kengen@sha256:" + "a" * 64


def runtime():
    # Generate test data at runtime; never use a production secret.
    import secrets
    return {"KENGEN_POSTGRES_PASSWORD": secrets.token_urlsafe(32),
            "KENGEN_OIDC_ISSUER": "https://auth.example.test/realms/test",
            "KENGEN_OIDC_AUDIENCE": "kengen",
            "KENGEN_OIDC_SUBJECTS": "service-sub",
            "KENGEN_OIDC_CLIENT_IDS": "keikaku-kengen"}


class FakeAPI:
    def __init__(self):
        self.current = {"composeId": "kengen-id", "name": "kengen",
                        "appName": "nakamadevs-kengen-test", "env": deploy.render_env(runtime()),
                        "composeFile": "old", "composeStatus": "done"}
        self.writes = []
        self.domains = []
        self.statuses = ["running", "done"]
        self.deployed = False
        self.title = ""

    def call(self, method, route, data=None):
        if method == "POST":
            self.writes.append((route, data))
        if route == "project.all":
            return [{"name": "NakamaDevs", "environments": [{"name": "production",
                     "environmentId": "prod", "compose": [self.current]}]}]
        if route == "compose.one":
            value = dict(self.current)
            if self.deployed:
                value["composeStatus"] = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return value
        if route == "deployment.allByCompose":
            if not self.deployed:
                return [{"deploymentId": "old", "status": "done", "title": "old"}]
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return [{"deploymentId": "new", "status": status, "title": self.title}]
        if route == "domain.byComposeId":
            return self.domains
        if route == "compose.deploy":
            self.deployed = True
            self.title = data["title"]
        return {}


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.validation = patch.object(deploy, "validate_compose")
        self.validation.start()
        self.addCleanup(self.validation.stop)

    def test_invalid_compose_stops_before_mutation(self):
        api = FakeAPI()
        with patch.object(deploy, "validate_compose", side_effect=deploy.DeployError("invalid Compose")):
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(deploy.DeployError):
                    deploy.deploy(api, "kengen-id", DIGEST, {}, Path(folder))
        self.assertEqual(api.writes, [])

    def test_configured_id_must_belong_to_production(self):
        api = FakeAPI()
        api.call = lambda *args: [{"name": "NakamaDevs", "environments": [
            {"name": "production", "environmentId": "prod", "compose": []}]}]
        with self.assertRaises(deploy.DeployError):
            deploy.ensure_service(api, "staging-id", runtime(), DIGEST)

    def test_fresh_service_requires_auth_before_creation(self):
        writes = []
        def call(method, route, data=None):
            if method == "GET":
                return [{"name": "NakamaDevs", "environments": [
                    {"name": "production", "environmentId": "prod", "compose": []}]}]
            writes.append(data)
            return {"composeId": "new"}
        api = FakeAPI()
        api.call = call
        with self.assertRaises(deploy.DeployError):
            deploy.ensure_service(api, None, {}, DIGEST)
        self.assertEqual(writes, [])
        self.assertEqual(deploy.ensure_service(api, None, runtime(), DIGEST), "new")
        self.assertEqual(writes[0]["environmentId"], "prod")
        self.assertEqual(writes[0]["name"], "kengen")

    def test_wrong_service_is_rejected_before_writes(self):
        api = FakeAPI()
        api.current["name"] = "keikaku"
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(deploy.DeployError, "target service"):
                deploy.deploy(api, "kengen-id", DIGEST, {}, Path(folder), timeout=0)
        self.assertEqual(api.writes, [])

    def test_wrong_app_prefix_is_rejected(self):
        api = FakeAPI()
        api.current["appName"] = "nakamadevs-kengenish-test"
        with self.assertRaises(deploy.DeployError):
            deploy.verify_service(api.current, "kengen-id")

    def test_existing_credentials_win_and_snapshot_precedes_update(self):
        api = FakeAPI()
        old = api.current["env"]
        with tempfile.TemporaryDirectory() as folder:
            snapshots = Path(folder)
            def check_update(method, route, data=None):
                if route == "compose.update":
                    saved = list(snapshots.glob("*.json"))
                    self.assertEqual(len(saved), 1)
                    self.assertEqual(saved[0].stat().st_mode & 0o777, 0o600)
                    self.assertEqual(json.loads(saved[0].read_text())["env"], old)
                return FakeAPI.call(api, method, route, data)
            api.call = check_update
            with patch.object(deploy, "check_health"), patch.object(deploy.time, "sleep"):
                deploy.deploy(api, "kengen-id", DIGEST, runtime(), snapshots)
        updated = next(data for route, data in api.writes if route == "compose.update")
        merged = deploy.parse_env(updated["env"])
        for key, value in deploy.parse_env(old).items():
            self.assertEqual(merged[key], value)
        self.assertEqual(merged["KENGEN_IMAGE_DIGEST"], DIGEST)
        self.assertIn("@sha256:", merged["KENGEN_IMAGE_DIGEST"])

    def test_missing_stored_password_stops_instead_of_regenerating(self):
        api = FakeAPI()
        values = runtime()
        del values["KENGEN_POSTGRES_PASSWORD"]
        api.current["env"] = deploy.render_env(values)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(deploy.DeployError, "stored database password"):
                deploy.deploy(api, "kengen-id", DIGEST, runtime(), Path(folder))
        self.assertEqual(api.writes, [])

    def test_invalid_authentication_stops_before_writes(self):
        for key, value in [("KENGEN_OIDC_ISSUER", "http://auth.test"),
                           ("KENGEN_OIDC_CLIENT_IDS", ""), ("KENGEN_OIDC_CLIENT_IDS", "a, b"),
                           ("KENGEN_OIDC_CLIENT_IDS", "a,,b"), ("KENGEN_OIDC_SUBJECTS", "a, b"), ("KENGEN_OIDC_AUDIENCE", "")]:
            api = FakeAPI()
            values = runtime()
            values[key] = value
            api.current["env"] = deploy.render_env(values)
            with tempfile.TemporaryDirectory() as folder, patch.object(deploy, "check_health"), patch.object(deploy.time, "sleep"):
                with self.assertRaises(deploy.DeployError):
                    deploy.deploy(api, "kengen-id", DIGEST, {}, Path(folder))
            self.assertEqual(api.writes, [])

    def test_wrong_domain_route_stops_before_update(self):
        api = FakeAPI()
        api.domains = [{"host": deploy.HOST, "serviceName": "web", "port": 8000, "https": True}]
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(deploy.DeployError, "domain"):
                deploy.deploy(api, "kengen-id", DIGEST, {}, Path(folder))
        self.assertEqual(api.writes, [])

    def test_error_idle_unknown_and_timeout_fail(self):
        for status in ["error", "idle", "unknown", "running"]:
            api = FakeAPI()
            api.statuses = [status]
            with tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(deploy.DeployError):
                    deploy.deploy(api, "kengen-id", DIGEST, {}, Path(folder), timeout=0)

    def test_domain_targets_only_kengen_http(self):
        api = FakeAPI()
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(deploy, "check_health") as health, patch.object(deploy.time, "sleep"):
                deploy.deploy(api, "kengen-id", DIGEST, {}, Path(folder))
        domain = next(data for route, data in api.writes if route == "domain.create")
        self.assertEqual((domain["host"], domain["serviceName"], domain["port"]), (deploy.HOST, "kengen", 8080))
        self.assertTrue(domain["https"])
        health.assert_called_once()

    def test_old_success_does_not_count_as_new_deployment(self):
        api = FakeAPI()
        api.deployed = False
        original = api.call
        def stale(method, route, data=None):
            if route == "deployment.allByCompose":
                return [{"deploymentId": "old", "status": "done", "title": "old"}]
            return original(method, route, data)
        api.call = stale
        api.statuses = ["done"]
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(deploy, "check_health") as health:
                with self.assertRaises(deploy.DeployError):
                    deploy.deploy(api, "kengen-id", DIGEST, {}, Path(folder), timeout=0)
                health.assert_not_called()

    def test_invalid_digest_rejected(self):
        for image in ["localhost:5050/kengen:latest", "localhost:5050/kengen@sha256:x", "other@sha256:" + "a" * 64]:
            with self.assertRaises(deploy.DeployError):
                deploy.validate_digest(image)

    def test_env_round_trip_and_duplicate_rejection(self):
        values = {"A": "a$b#c=quote'\"slash\\", "B": "normal"}
        self.assertEqual(deploy.parse_env(deploy.render_env(values)), values)
        with self.assertRaises(deploy.DeployError):
            deploy.parse_env("A=first\nA=second\n")

    def test_api_rejects_unapproved_destinations(self):
        import secrets
        for url in ["http://example.test", "https://dokploy.lecksfrawen.com.evil.test",
                    "http://localhost:3000@evil.test", "https://dokploy.lecksfrawen.com/path"]:
            with self.assertRaises(deploy.DeployError):
                deploy.API(url, secrets.token_urlsafe())

    def test_image_must_match_commit_and_arm64(self):
        good = {"Os": "linux", "Architecture": "arm64", "Config": {"Labels": {
            "org.opencontainers.image.revision": "a" * 40}}}
        for changed in [dict(good, Architecture="amd64"), dict(good, Config={})]:
            with patch.object(deploy, "command", side_effect=["", json.dumps([changed])]):
                with self.assertRaises(deploy.DeployError):
                    deploy.verify_image(DIGEST, "a" * 40)
        with patch.object(deploy, "command", side_effect=["", json.dumps([good])]):
            deploy.verify_image(DIGEST, "a" * 40)

    def test_restore_refuses_another_service_and_never_deploys(self):
        api = FakeAPI()
        values = deploy.parse_env(api.current["env"])
        values["KENGEN_IMAGE_DIGEST"] = DIGEST
        api.current["env"] = deploy.render_env(values)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            saved = deploy.snapshot(api.current, root)
            deploy.restore_environment(api, "kengen-id", saved, root)
            self.assertEqual([route for route, _ in api.writes], ["compose.update"])
            api.writes = []
            record = json.loads(saved.read_text())
            record["composeId"] = "keikaku-id"
            saved.write_text(json.dumps(record))
            with self.assertRaises(deploy.DeployError):
                deploy.restore_environment(api, "kengen-id", saved, root)
            self.assertEqual(api.writes, [])

    def test_command_does_not_pass_deployment_credentials(self):
        import secrets
        marker = secrets.token_urlsafe()
        with patch.dict(os.environ, {"DOKPLOY_API_KEY": marker}):
            with patch.object(deploy.subprocess, "run") as run:
                run.return_value.stdout = "ok"
                deploy.command(["git", "status"])
                self.assertNotIn("DOKPLOY_API_KEY", run.call_args.kwargs["env"])

    def test_release_tags_cannot_inject_shell_or_select_branches(self):
        for tag in ["main", "--help", "v1.0.0;echo bad", "v1.0.0$(id)", "../main"]:
            with self.assertRaises(deploy.DeployError):
                deploy.validate_tag(tag)
        deploy.validate_tag("v1.2.3-rc.1")

    def test_unmerged_release_stops_before_archive(self):
        calls = []
        def command(args, **kwargs):
            calls.append(args)
            if "merge-base" in args:
                raise deploy.DeployError("unmerged")
            return "a" * 40
        with patch.object(deploy, "command", side_effect=command):
            with self.assertRaises(deploy.DeployError):
                deploy.resolve_release("v1.0.0")
        self.assertFalse(any("archive" in args for args in calls))


if __name__ == "__main__":
    unittest.main()
