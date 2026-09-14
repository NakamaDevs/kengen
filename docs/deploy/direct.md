# Direct deployment on the M1 mini

Use `deploy/dokploy/direct.compose.yaml` as the raw Compose source in Dokploy.
Set `KENGEN_IMAGE_DIGEST` to the built `localhost:5050/kengen@sha256:...` image.
Deploy the service with the Dokploy Deploy button. GitHub Actions are not required.

This stack uses the built-in preshared API key method. Send the key as
`Authorization: Bearer <key>`. The OIDC stack remains available in
`production.compose.yaml` for a later Kagi integration.

The mini stores credentials in `/Users/hdb/.local/share/dokploy/secrets/kengen/`:

- `auth.env`: `OPENFGA_AUTHN_PRESHARED_KEYS`.
- `database.env`: `OPENFGA_DATASTORE_PASSWORD`.
- `postgres.env`: `POSTGRES_PASSWORD`, with the same database password.

These files have mode 0600 in a directory with mode 0700. Keep them outside Git.
Dokploy mounts this directory at the same path. Back up the files with the database.
Do not regenerate the database password when a data volume already exists.

Set the Dokploy domain to `kengen.lecksfrawen.com`, service `kengen`, port `8080`,
HTTPS, and the existing `letsencrypt` resolver. DNS points to `100.116.123.8`.
Connect Tailscale to use this endpoint, as with Keikaku.

Check `/healthz`, an authenticated `/stores` request, and a request with an
invalid key. The invalid key must be rejected. The database volume persists
across normal redeployments. The API does not include a browser dashboard.

Run the smoke test on the mini with
`SSL_CERT_FILE=/etc/ssl/cert.pem /usr/bin/python3 /Users/hdb/homelab/kengen/smoke.py`. It creates and removes
a test store, writes a model and tuple, and checks both allowed and denied access.

## Current deployment

Dokploy service: `kengen` (`nakamadevs-kengen-s5isof`).
Service ID: `Rngd-n1Wq6CMj3uPIe7Q_`.
Application source: local main merge `0a160e6c`.
Image: `localhost:5050/kengen@sha256:c3f4b5395e63adfbe58131db6ca0ab9f8abe52da8ee0017a72b54708b06c7217`.

Production deployment and the HTTPS smoke test passed on 2026-09-14 UTC.
The macOS system CA bundle is required by the mini's command-line Python.
Do not disable certificate verification.

The API key remains in `auth.env` on the mini. Use this file only in trusted
backend processes. Do not put the key in browser code.
