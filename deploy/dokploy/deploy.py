#!/usr/bin/env python3
"""Deploy reviewed Kengen releases to Dokploy on hdbmm (NAK-903).

Uses Python's standard library. API bodies, environments, and command output
must never be printed: they can contain credentials.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
HOST = "kengen.lecksfrawen.com"
IMAGE = "localhost:5050/kengen"
AUTH = ("KENGEN_OIDC_ISSUER", "KENGEN_OIDC_AUDIENCE", "KENGEN_OIDC_SUBJECTS")
PASSWORD = "KENGEN_POSTGRES_PASSWORD"


class DeployError(Exception):
    """An error that is safe to print."""


def validate_tag(tag):
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?", tag):
        raise DeployError("Use a release tag such as v1.2.3.")


def validate_digest(image):
    if not re.fullmatch(re.escape(IMAGE) + r"@sha256:[0-9a-f]{64}", image):
        raise DeployError("Use an immutable localhost:5050/kengen image digest.")


def parse_env(text):
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or key in values:
            raise DeployError("Invalid or duplicate environment key.")
        try:
            if value.startswith('"'):
                value = json.loads(value).replace("$$", "$")
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1].replace("\\'", "'")
        except (ValueError, TypeError):
            raise DeployError("Invalid quoted environment value.") from None
        values[key] = value
    return values


def render_env(values):
    # Single quotes prevent Compose interpolation, including $ in passwords.
    # Reject multiline values instead of silently changing the environment.
    lines = []
    for key, value in values.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or not isinstance(value, str):
            raise DeployError("Invalid environment entry.")
        if any(c in value for c in "\r\n\0"):
            raise DeployError("Multiline environment values are not supported.")
        lines.append(key + "='" + value.replace("'", "\\'") + "'\n")
    return "".join(lines)


def validate_runtime(values):
    for key in (*AUTH, PASSWORD):
        if not values.get(key, "").strip():
            raise DeployError("Missing required setting: " + key)
    issuer = urllib.parse.urlsplit(values[AUTH[0]])
    if issuer.scheme != "https" or not issuer.hostname or issuer.username or issuer.password or issuer.query or issuer.fragment:
        raise DeployError("KENGEN_OIDC_ISSUER must be an HTTPS issuer URL.")
    if not re.fullmatch(r"[^\s,]+(?:,[^\s,]+)*", values[AUTH[2]]):
        raise DeployError("KENGEN_OIDC_SUBJECTS must contain exact subjects without spaces.")


def verify_service(current, compose_id):
    if (current.get("composeId") != compose_id or current.get("name", "").lower() != "kengen"
            or not current.get("appName", "").startswith("nakamadevs-kengen-")):
        raise DeployError("The target service is not Kengen. No update was sent.")


def merged_environment(current, defaults, image):
    stored = parse_env(current.get("env") or "")
    if stored and not stored.get(PASSWORD):
        raise DeployError("Restore the stored database password before deployment.")
    merged = dict(stored)
    for key in (*AUTH, PASSWORD):
        if not merged.get(key) and defaults.get(key):
            merged[key] = defaults[key]
    if not stored and not merged.get(PASSWORD):
        merged[PASSWORD] = secrets.token_urlsafe(48)
    merged["KENGEN_IMAGE_DIGEST"] = image
    validate_runtime(merged)
    return render_env(merged)


def snapshot(current, directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise DeployError("Snapshot directory must be private (mode 0700).")
    fd, path = tempfile.mkstemp(prefix="kengen-", suffix=".json", dir=directory)
    with os.fdopen(fd, "w") as file:
        json.dump({key: current.get(key) for key in
                   ("composeId", "name", "appName", "composeFile", "env", "composeStatus")}, file)
    return Path(path)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class API:
    def __init__(self, url, key):
        parsed = urllib.parse.urlsplit(url)
        local = parsed.hostname in ("localhost", "127.0.0.1") and parsed.port == 3000
        remote = parsed.scheme == "https" and parsed.hostname == "dokploy.lecksfrawen.com"
        if not ((parsed.scheme == "http" and local) or remote) or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise DeployError("Use local Dokploy on port 3000 or its approved HTTPS domain.")
        if not key:
            raise DeployError("DOKPLOY_API_KEY is missing.")
        self.url, self.key = url.rstrip("/") + "/api/", key
        self.opener = urllib.request.build_opener(NoRedirect())

    def call(self, method, route, data=None):
        url = self.url + route
        body = None
        if method == "GET":
            url += "?" + urllib.parse.urlencode(data or {})
        else:
            body = json.dumps(data or {}).encode()
        request = urllib.request.Request(url, body, method=method,
                                         headers={"x-api-key": self.key, "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise DeployError("Dokploy " + route + " returned HTTP " + str(error.code)) from None
        except (OSError, ValueError):
            raise DeployError("Dokploy " + route + " failed. Check the service locally.") from None


def ensure_service(api, compose_id, defaults, image):
    projects = api.call("GET", "project.all")
    projects = [p for p in projects if p.get("name", "").lower() == "nakamadevs"]
    if len(projects) != 1:
        raise DeployError("Expected one NakamaDevs project.")
    environments = [e for e in projects[0].get("environments", []) if e.get("name") == "production"]
    if len(environments) != 1:
        raise DeployError("Expected one production environment.")
    environment = environments[0]
    if compose_id:
        selected = [item for item in environment.get("compose", [])
                    if item.get("composeId") == compose_id and item.get("name", "").lower() == "kengen"]
        if len(selected) != 1:
            raise DeployError("The configured service ID does not select Kengen in production.")
        return compose_id
    services = [s for s in environment.get("compose", []) if s.get("name", "").lower() == "kengen"]
    if len(services) > 1:
        raise DeployError("More than one Kengen service exists.")
    if services:
        return services[0]["composeId"]
    # Validate before the first write. A missing identity must not create a stack.
    merged_environment({}, defaults, image)
    result = api.call("POST", "compose.create", {"name": "kengen", "appName": "nakamadevs-kengen",
                     "environmentId": environment["environmentId"], "composeType": "docker-compose"})
    return result["composeId"]


def check_domain(domains):
    if len(domains) > 1:
        raise DeployError("Unexpected domain on the Kengen service.")
    for domain in domains:
        if (domain.get("host") != HOST or domain.get("serviceName") != "kengen"
                or str(domain.get("port")) != "8080" or domain.get("https") is not True
                or domain.get("path", "/") not in (None, "", "/")
                or domain.get("internalPath", "/") not in (None, "", "/")):
            raise DeployError("The existing domain does not match the Kengen HTTP route.")


def check_health(timeout=120):
    deadline = time.monotonic() + timeout
    opener = urllib.request.build_opener(NoRedirect())
    while True:
        try:
            with opener.open("https://" + HOST + "/healthz", timeout=10) as response:
                if response.status == 200:
                    return
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise DeployError("Kengen HTTPS health check failed.")
        time.sleep(5)


def validate_compose(env):
    with tempfile.TemporaryDirectory(prefix="kengen-compose-") as directory:
        path = Path(directory) / "runtime.env"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as file:
            file.write(env)
        command(["docker", "compose", "--env-file", str(path), "-f",
                 str(ROOT / "deploy/dokploy/production.compose.yaml"), "config", "--quiet"])


def deploy(api, compose_id, image, defaults, snapshot_dir, timeout=900):
    validate_digest(image)
    current = api.call("GET", "compose.one", {"composeId": compose_id})
    verify_service(current, compose_id)
    if current.get("composeStatus") == "running":
        raise DeployError("A Kengen deployment is already running.")
    env = merged_environment(current, defaults, image)
    validate_compose(env)
    domains = api.call("GET", "domain.byComposeId", {"composeId": compose_id})
    check_domain(domains)
    previous = api.call("GET", "deployment.allByCompose", {"composeId": compose_id})
    previous_ids = {item["deploymentId"] for item in previous}
    snapshot(current, snapshot_dir)
    compose_file = (ROOT / "deploy/dokploy/production.compose.yaml").read_text()
    api.call("POST", "compose.update", {"composeId": compose_id, "sourceType": "raw",
                                        "composeFile": compose_file, "env": env})
    if not domains:
        api.call("POST", "domain.create", {"composeId": compose_id, "host": HOST,
                 "domainType": "compose", "serviceName": "kengen", "port": 8080,
                 "https": True, "certificateType": "letsencrypt"})
    title = "kengen " + image + " " + secrets.token_hex(8)
    api.call("POST", "compose.deploy", {"composeId": compose_id, "title": title})
    deadline = time.monotonic() + timeout
    while True:
        records = api.call("GET", "deployment.allByCompose", {"composeId": compose_id})
        matching = [item for item in records if item.get("deploymentId") not in previous_ids
                    and item.get("title") == title]
        if len(matching) > 1:
            raise DeployError("More than one deployment matched this request.")
        status = matching[0].get("status") if matching else "running"
        if status == "done":
            check_health()
            return compose_id
        if status != "running":
            raise DeployError("Dokploy did not complete the deployment successfully.")
        if time.monotonic() >= deadline:
            raise DeployError("Dokploy deployment timed out.")
        time.sleep(5)


def command(args, cwd=ROOT):
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("KENGEN_") and not any(part in key.upper() for part in ("TOKEN", "PASSWORD", "SECRET", "API_KEY"))}
    try:
        result = subprocess.run(args, cwd=cwd, env=environment, check=True, capture_output=True, text=True)
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        # Commands and their output can contain runtime environment values.
        raise DeployError("A " + args[0] + " command failed. No command output was logged.") from None


def resolve_release(tag):
    validate_tag(tag)
    command(["git", "fetch", "origin", "main", "--tags"])
    commit = command(["git", "rev-parse", "--verify", "refs/tags/" + tag + "^{commit}"])
    command(["git", "merge-base", "--is-ancestor", commit, "origin/main"])
    return commit


@contextmanager
def release_source(commit):
    # A separate Git index keeps verification and generated mocks off main.
    with tempfile.TemporaryDirectory(prefix="kengen-release-") as directory:
        source = Path(directory) / "source"
        command(["git", "worktree", "add", "--detach", str(source), commit])
        try:
            yield source
        finally:
            command(["git", "worktree", "remove", "--force", str(source)])


def verify_image(image, commit):
    validate_digest(image)
    command(["docker", "pull", "--platform", "linux/arm64", image])
    info = json.loads(command(["docker", "image", "inspect", image]))[0]
    if (info.get("Os") != "linux" or info.get("Architecture") != "arm64"
            or info.get("Config", {}).get("Labels", {}).get("org.opencontainers.image.revision") != commit):
        raise DeployError("The image platform or source commit does not match the release.")


def build(tag, commit):
    with release_source(commit) as source:
        print("Verify the exact release commit.", flush=True)
        command(["mise", "trust", "--yes", str(source / "mise.toml")])
        command(["make", "test", "FILTER=TestProductionCompose|TestProductionValidation"], cwd=source)
        command(["mise", "run", "verify"], cwd=source)
        if command(["git", "status", "--porcelain"], cwd=source):
            raise DeployError("Verification changed the release worktree. Commit the fixes before release.")
        print("Build the reviewed Linux ARM64 image.", flush=True)
        command(["docker", "build", "--platform", "linux/arm64",
                 "--label", "org.opencontainers.image.revision=" + commit,
                 "--label", "org.opencontainers.image.version=" + tag,
                 "--label", "org.opencontainers.image.source=https://github.com/NakamaDevs/kengen",
                 "-t", IMAGE + ":" + tag, "."], cwd=source)
        print("Scan the image before publication.", flush=True)
        command(["trivy", "image", "--scanners", "vuln", "--severity", "HIGH,CRITICAL",
                 "--exit-code", "1", "--quiet", IMAGE + ":" + tag])
        command(["docker", "push", IMAGE + ":" + tag])
        refs = json.loads(command(["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", IMAGE + ":" + tag]))
        images = [ref for ref in refs if ref.startswith(IMAGE + "@sha256:")]
        if len(images) != 1:
            raise DeployError("Could not resolve one published image digest.")
        verify_image(images[0], commit)
        return images[0]


def restore_environment(api, compose_id, path, snapshot_dir):
    if not compose_id:
        raise DeployError("KENGEN_DOKPLOY_COMPOSE_ID is required for restore.")
    if path.stat().st_mode & 0o077:
        raise DeployError("The restore snapshot must be private (mode 0600).")
    record = json.loads(path.read_text())
    verify_service(record, compose_id)
    values = parse_env(record["env"])
    validate_runtime(values)
    validate_digest(values["KENGEN_IMAGE_DIGEST"])
    ensure_service(api, compose_id, {}, values["KENGEN_IMAGE_DIGEST"])
    current = api.call("GET", "compose.one", {"composeId": compose_id})
    verify_service(current, compose_id)
    if current.get("composeStatus") == "running":
        raise DeployError("A Kengen deployment is already running.")
    snapshot(current, snapshot_dir)
    api.call("POST", "compose.update", {"composeId": compose_id, "env": render_env(values)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--tag", help="Reviewed release tag on main")
    mode.add_argument("--restore-env", type=Path, help="Restore a private snapshot environment without deploying")
    parser.add_argument("--image", help="Redeploy an existing immutable image without a build")
    parser.add_argument("--check-ref", action="store_true", help="Validate the release ref without deploying")
    args = parser.parse_args()
    try:
        if args.restore_env:
            if args.image or args.check_ref:
                raise DeployError("Restore cannot be combined with image or ref checks.")
            api = API(os.environ.get("DOKPLOY_URL", "http://localhost:3000"), os.environ.get("DOKPLOY_API_KEY", ""))
            restore_environment(api, os.environ.get("KENGEN_DOKPLOY_COMPOSE_ID"), args.restore_env,
                                Path.home() / ".kengen/dokploy-snapshots")
            print("Stored environment restored. No deployment was started.")
            return
        commit = resolve_release(args.tag)
        if args.check_ref:
            print("Release commit is on main: " + commit)
            return
        if os.environ.get("KENGEN_DEPLOY_APPROVED") != "true":
            raise DeployError("KENGEN_DEPLOY_APPROVED must be true after the deployment review.")
        api = API(os.environ.get("DOKPLOY_URL", "http://localhost:3000"), os.environ.get("DOKPLOY_API_KEY", ""))
        image = args.image
        if image:
            verify_image(image, commit)
        else:
            image = build(args.tag, commit)
        compose_id = ensure_service(api, os.environ.get("KENGEN_DOKPLOY_COMPOSE_ID"), os.environ, image)
        deploy(api, compose_id, image, os.environ, Path.home() / ".kengen/dokploy-snapshots")
        print("Kengen deployed: " + image)
        print("KENGEN_DOKPLOY_COMPOSE_ID=" + compose_id)
    except (DeployError, OSError, ValueError, KeyError, TypeError):
        # Do not dump exceptions, tracebacks, environment values, or API bodies.
        error = sys.exc_info()[1]
        print(str(error) if isinstance(error, DeployError) else "Deployment failed. Inspect Dokploy locally.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
