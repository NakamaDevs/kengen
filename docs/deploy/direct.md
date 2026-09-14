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

Run the smoke test on the mini with `python3 smoke.py`. It creates and removes
a test store, writes a model and tuple, and checks both allowed and denied access.
