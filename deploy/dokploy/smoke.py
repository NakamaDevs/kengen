"""Check a running Kengen API with its private preshared key file."""
import argparse
import json
from pathlib import Path
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://kengen.lecksfrawen.com")
    parser.add_argument("--key-file", type=Path,
                        default=Path("/Users/hdb/.local/share/dokploy/secrets/kengen/auth.env"))
    args = parser.parse_args()
    values = dict(line.split("=", 1) for line in args.key_file.read_text().splitlines() if "=" in line)
    key = values["OPENFGA_AUTHN_PRESHARED_KEYS"]

    def request(method, path, data=None, token=key):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        body = None if data is None else json.dumps(data).encode()
        req = urllib.request.Request(args.url.rstrip("/") + path, body, headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                body = response.read()
                return response.status, json.loads(body) if body else None
        except urllib.error.HTTPError as error:
            return error.code, None

    assert request("GET", "/healthz", token=None)[0] == 200, "Health check failed"
    for token in (None, "invalid-smoke-test-key"):
        assert request("GET", "/stores", token=token)[0] in (401, 403), "Invalid access accepted"
    assert request("GET", "/stores")[0] == 200, "Authenticated access failed"
    status, store = request("POST", "/stores", {"name": "kengen-deployment-smoke"})
    assert status == 201, "Store creation failed"
    path = "/stores/" + store["id"]
    try:
        model = {"schema_version": "1.1", "type_definitions": [
            {"type": "user"},
            {"type": "document", "relations": {"viewer": {"this": {}}},
             "metadata": {"relations": {"viewer": {"directly_related_user_types": [{"type": "user"}]}}}},
        ]}
        status, result = request("POST", path + "/authorization-models", model)
        assert status == 201, "Model creation failed"
        model_id = result["authorization_model_id"]
        tuple_key = {"user": "user:alice", "relation": "viewer", "object": "document:smoke"}
        assert request("POST", path + "/write", {
            "authorization_model_id": model_id, "writes": {"tuple_keys": [tuple_key]}})[0] == 200
        for user, expected in (("alice", True), ("bob", False)):
            status, result = request("POST", path + "/check", {
                "authorization_model_id": model_id,
                "tuple_key": dict(tuple_key, user="user:" + user),
            })
            assert status == 200 and result["allowed"] is expected, "Authorization result failed"
    finally:
        assert request("DELETE", path)[0] == 204, "Test store cleanup failed"
    print("PASS: health, rejected invalid access, authenticated store/model/tuple writes, allow/deny checks, cleanup.")


if __name__ == "__main__":
    main()
