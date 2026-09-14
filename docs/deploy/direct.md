# Direct deployment on the M1 mini

Run `mise run deploy:dokploy` from a clean, committed local main checkout.
The task sends the source to the M1 mini through SSH, builds a Linux ARM64 image,
scans it, pushes it to the mini registry, and updates Kengen through the Dokploy
API. It then checks HTTPS and tests authorization. No dashboard edits are needed.
Use `mise run deploy:dokploy -- --tag v1.2.3` to deploy a release tag on main.
Use `mise run deploy:status` to check the current service without a build.

The task requires Python 3.11 or later, Git, and SSH access through `macmini`.
The mini provides Docker, mise, and Python at `/opt/homebrew/bin/python3`.
It stores transferred source in `/Users/hdb/homelab/kengen/releases/<commit>`.
Only committed files enter the build context. The local cache is not transferred
with the source or included in the image.

## Dokploy credentials

Run `mise run deploy:credentials` once to import the Dokploy API key from
1Password. The task first checks the environment and `mise.local.toml`. It
opens 1Password only if the key is absent. Enable 1Password CLI integration for
the first import. Use `mise run deploy:credentials -- --prompt` for hidden manual
entry if needed.

The cache is a mode 0600 `mise.local.toml` file with an `[env]` table. It is ignored
by Git and Docker. Local mise files with `.yaml` or `.tunnel` suffixes are also
ignored. Use the TOML filename for mise to load the settings. Do not print the
environment or run `mise env` in shared logs: these commands can show the key.

Run `mise run deploy:credentials:save` to back up the key once to the Secure Note
`Kengen deploy credential` in the `prj_nakamadevs_homelab` vault. Another machine
can import this item. Normal deployments do not call 1Password while a cached
key exists. The SSH task caches the key on the mini through encrypted stdin at
`/Users/hdb/homelab/kengen/mise.local.toml`, with mode 0600.

This cache handles the Dokploy key only. Use native AWS sessions and profiles
for AWS access.

## GitHub deployment

The published-release workflow calls `deploy.yml` from main, as in Keikaku.
You can also run Deploy Kengen manually, with an optional tag. The dedicated
`nakama-kengen-deploy` group accepts only Kengen's main deployment workflow on
the M1 mini. The job tests upstream behavior, builds the requested source,
then uses the same API deployment task. Set the `DOKPLOY_API_KEY` repository
secret and `KENGEN_DOKPLOY_COMPOSE_ID` variable. CI does not open 1Password.

Activation requires the runner service, repository Actions, and
`KENGEN_DEPLOY_APPROVED=true`. Keep workflows that need unavailable Linux
runners disabled. Until activation is complete, use the local mise task.

## Runtime settings

The API task uses `deploy/dokploy/direct.compose.yaml` as the raw Compose source.
It preserves existing environment settings and changes `KENGEN_IMAGE_DIGEST`
to an immutable `localhost:5050/kengen@sha256:...` reference. It saves a private
snapshot before updates in `~/.kengen/dokploy-snapshots` on the mini.

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
Application source: local main commit `b0b0c18a5595c48b6a7c7e933aabb1638ea4f7fd`.
Image: `localhost:5050/kengen@sha256:fb774e70ad316a99eb807bf55bad688f413b5bc1fa6fae1c9761192ce337ae41`.

Production deployment and the HTTPS smoke test passed on 2026-09-14 UTC.
The image scan and the mise/API deployment both passed. The Dokploy key is
cached on the MacBook and mini, backed up in 1Password, and set as a GitHub
repository secret. Runner activation remains pending; Actions are disabled.
The macOS system CA bundle is required by the mini's command-line Python.
Do not disable certificate verification.

The API key remains in `auth.env` on the mini. Use this file only in trusted
backend processes. Do not put the key in browser code.
