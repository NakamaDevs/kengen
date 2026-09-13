# Kengen Dokploy production runbook

Kengen uses the existing Dokploy instance on the Mac mini `hdbmm`.
The host runs macOS on Apple Silicon. OrbStack runs the Linux containers.
The local registry is `localhost:5050`; the local Dokploy API is
`http://localhost:3000`. Tailscale already connects this host to the tailnet.

The release flow follows Keikaku at commit
`40af71e3476262b8943062192930376e6f04eb74`. Kengen uses a Python standard-library
deployment task with its own service identity checks. It uses
`deploy/dokploy/production.compose.yaml` as raw Compose input.

## Scope and limits

Installing this code does not deploy the stack, change DNS, enable GitHub
Actions, or register a runner. The deployment task writes only to the Kengen
Compose service after it checks the service name and app name.

Dokploy routes HTTP to `kengen:8080` through its managed proxy. The Compose
file has no host port mappings. PostgreSQL, gRPC, metrics, profiler, playground,
and Dokploy administration stay private.

## Required Dokploy environment names

Set these values in Dokploy before validating or deploying. Do not put values
in Compose files, Git, shell history, tickets, or chat.

| Name | Purpose |
| --- | --- |
| `KENGEN_IMAGE_DIGEST` | Immutable Kengen image reference, including `@sha256:`. |
| `KENGEN_OIDC_ISSUER` | HTTPS issuer URL for the Kagi/Keycloak realm. |
| `KENGEN_OIDC_AUDIENCE` | Audience issued for the Kengen service identity. |
| `KENGEN_OIDC_CLIENT_IDS` | Exact allowed service client IDs from the signed `azp` claim. |
| `KENGEN_OIDC_SUBJECTS` | Non-secret allow-list of Kengen service identity subjects. |
| `KENGEN_POSTGRES_PASSWORD` | Password for the Kengen PostgreSQL role. |

The Compose interpolation expressions require every value. Docker Compose stops
before creating containers when one is empty or missing. The validation script
also requires an `https://` OIDC issuer and an image digest. The service uses
OIDC. It never falls back to unauthenticated mode.

## Service authentication

NAK-908 creates the Kagi/Keycloak confidential Kengen service identity. Use its
client-credentials flow from a trusted backend. Request a token with the
configured Kengen audience. Set `KENGEN_OIDC_SUBJECTS` to that identity's exact
`sub` claim. Send that service token to the raw Kengen API.

Create a separate confidential client, such as `keikaku-kengen`, for these calls.
Keep browser login on the existing `keikaku` client. Set
`KENGEN_OIDC_CLIENT_IDS` to the service client ID. The production stack reads
only the signed `azp` claim and rejects a missing or unlisted client ID.
A matching audience and subject are still required.

The optional server setting is `authn.oidc.allowedClientIDs`, with flag
`--authn-oidc-allowed-client-ids` and environment variable
`OPENFGA_AUTHN_OIDC_ALLOWED_CLIENT_IDS`. An empty server list preserves the
upstream client policy. The production stack requires a nonempty list.

`KENGEN_OIDC_SUBJECTS` is required. An empty OpenFGA OIDC subject list accepts
every subject from a valid issuer. This stack must accept only the NAK-908
service identity subject.

To rotate the service identity, use this exact temporary value:
`KENGEN_OIDC_SUBJECTS=<old-sub>,<new-sub>`. Validate the new client-credentials
token. If rotation uses a new client ID, include both exact client IDs in
`KENGEN_OIDC_CLIENT_IDS` during the overlap. Then remove the old subject and
client ID. Do not use spaces. Do not remove the current
subject before the new token works.

Do not send browser tokens or end-user tokens to the raw Kengen API. A browser
must call its own backend. That backend must exchange or obtain a confidential
service token before it calls Kengen.

## Initial service configuration

1. Create a Dokploy Compose service from raw Compose source.
2. Paste `deploy/dokploy/production.compose.yaml` without changing image pins.
3. Set only the required environment names in the Dokploy service environment.
4. Configure the approved HTTP domain route to service `kengen` and port `8080`.
5. Review the rendered Compose configuration.
6. Confirm that it contains no `ports` entries.
7. Validate the Compose file before the first deploy.

The `migrate` service runs once after PostgreSQL is ready. Kengen starts only
after migration finishes successfully. PostgreSQL data persists in the
`kengen-postgres` named volume.

## Validate before deployment

Run the repository checks from the repository root:

```sh
go test ./deploy/dokploy
sh deploy/dokploy/validate-production.sh
```

Also inspect Dokploy's rendered configuration. Confirm all images have a
`@sha256:` digest. Confirm only port `8080` is exposed to Dokploy's internal
proxy. Do not add a host port mapping for any service.

## Health and observation

After an approved deployment, use the Dokploy service status and container logs.
The Kengen container health check uses its local gRPC health endpoint. The
public deployment check is `GET /healthz` through the approved HTTP route.

Use a Kagi/Keycloak confidential service token for OpenFGA API checks. Keep
tokens outside command history. Do not enable metrics, profiler, playground,
or gRPC publication for diagnosis. Use Dokploy logs and health state instead.

## Backup

Before any upgrade, take a logical PostgreSQL backup from the `postgres`
container. Store the backup in the approved encrypted backup location. Record
the image digest, backup time, and schema migration state with the change.

Do not copy a backup into this repository. Test the restore procedure on an
isolated Dokploy service before relying on it for recovery.

## Restore

1. Stop the Kengen service through Dokploy.
2. Create a fresh PostgreSQL volume for a restore test, or replace the approved
   production volume only during an approved recovery.
3. Restore the approved logical backup with PostgreSQL tools in the database
   container.
4. Set the same required environment names.
5. Run the one-shot `migrate` service.
6. Start Kengen and confirm `/healthz`.
7. Run an authenticated authorization check before returning traffic.

## Rollback

Database migrations can be irreversible. Do not roll back an image until its
database compatibility is confirmed. For an application-only rollback, set
`KENGEN_IMAGE_DIGEST` to the previous approved immutable digest and redeploy.

If the previous image cannot read the migrated database, stop. Restore the
matching PostgreSQL backup into the affected volume. Then deploy the matching
previous image digest. Validate health and an authenticated authorization check.

## Upstream upgrades

Review each OpenFGA upstream release and its migration notes. Build a Kengen
image from the reviewed commit. Scan it, record its immutable digest, and test
the Compose stack with a restored backup outside production.

Approve the application image and PostgreSQL image changes separately. Update
the pinned PostgreSQL digest only after testing its compatibility with a backup.
Do not use mutable tags such as `latest` or a major-version tag without a
digest. Take a fresh backup before every approved upgrade.

## Mac mini release automation

1. Merge the reviewed integration PR into protected `main`.
2. Complete OPS-283 and NAK-902. Register a dedicated runner on `hdbmm` in
   `nakama-kengen-deploy`, with labels `self-hosted`, `macOS`, `ARM64`, and
   `host-hdbmm`. Keep Keikaku's existing registration in its current group.
   Allow only `NakamaDevs/kengen` and the reusable workflow
   `NakamaDevs/kengen/.github/workflows/deploy.yml@refs/heads/main`.
   Do not allow untrusted pull requests to use this registration.
3. Create the `kengen-production` GitHub environment with the required review
   controls. Store `DOKPLOY_API_KEY` as a repository secret. Give this key only
   the Dokploy access required for Kengen where the installed version supports it.
4. Complete NAK-908. Set the required identity settings in the Kengen Dokploy
   environment. The release runner uses those stored values. It has no service
   account client secret and does not generate one.
5. Create the Kengen Compose service with the initial configuration above. Use
   name `kengen`, app-name prefix `nakamadevs-kengen-`, and the production
   environment of project `NakamaDevs`. Record its ID in the repository variable
   `KENGEN_DOKPLOY_COMPOSE_ID`. Never use Keikaku's ID or a shared `DOKPLOY_COMPOSE_ID`.
6. Set Kengen DNS to the mini's tailnet address, `100.116.123.8`, following
   Keikaku. Use the existing Traefik Cloudflare DNS challenge for TLS. Connect
   Tailscale to reach the domain. Check the DNS record and certificate before
   the first deployment.
7. After the authentication and network review, set repository variable
   `KENGEN_DEPLOY_APPROVED=true`. An administrator can enable Actions after
   the runner boundary review. Keep this switch unset until then.
8. Create a version tag such as `v1.0.0` on a reviewed commit on `main`, then
   publish a non-prerelease GitHub release. `release.yml` calls `deploy.yml`
   from `main`. A manual redeploy uses `deploy.yml` from `main` and a tag input.

```sh
gh workflow run deploy.yml --ref main -f tag=v1.0.0
```

The workflow checks the tag before it passes the Dokploy key to the task.
The task checks that the tag resolves to a commit on `origin/main`. It creates
an isolated Git worktree for that commit, runs the narrow upstream check and
`mise run verify`, then builds `linux/arm64`. Trivy must accept the image before
it is pushed. The task resolves the registry digest and verifies the image's
platform and source-commit label before deployment.

The runner must have Git, Mise, `/usr/bin/python3` (3.9 or later), the Docker
CLI, and access to `/Users/hdb/.orbstack/run/docker.sock`. The workflow installs
the repository's pinned Go and check tools in its own temporary Mise directory.
It uses a Docker config without a login-keychain credential helper. Docker CLI
plugins come from `/Users/hdb/.docker/cli-plugins`, as in Keikaku.

The Mac mini can also run the task locally. Supply the approved configuration
through the existing secret-management process. Do not put credentials on the
command line. The local task requires `KENGEN_DEPLOY_APPROVED=true`.

```sh
mise run test:deploy
mise run deploy:dokploy -- --tag v1.0.0
```

If the service ID is unset, the task finds exactly one `NakamaDevs` project and
its `production` environment. It finds Kengen or creates it after the identity
settings pass validation. A new service can receive a generated database
password. An existing service with a missing database password stops deployment;
restore the original value. Stored identity settings and credentials take
precedence over local values. Only the selected image digest changes on a
normal redeploy. Unknown environment keys are preserved.

The task checks existing domain settings before an update. It refuses a route
to another service or port. It adds the Kengen HTTP domain only when no domain
exists. It never adds a host port mapping.

## Deployment evidence and recovery

Every update first creates an owner-only snapshot in
`~/.kengen/dokploy-snapshots` (directory mode 0700, file mode 0600).
Snapshots contain credentials. Keep them on the deployment host and in the
approved encrypted backup store. Never upload them as CI artifacts.

The task tracks a new deployment record with a unique title. It does not accept
an old `done` status as success. An error, cancellation, unknown status, timeout,
or failed HTTPS `/healthz` check fails the task. After the first release, use the
NAK-908 identity to run an authenticated API check and confirm that a request
without a token is refused. Observe health and logs before closing NAK-903.

The upstream server has `/healthz`; this integration does not add `/readyz`.
Resolve NAK-903's readiness criterion through a reviewed upstream-compatible
change or an explicit issue decision before closing the issue.

To restore the stored environment without starting a deployment:

```sh
mise run deploy:dokploy -- --restore-env /private/path/kengen-snapshot.json
```

Restore verifies both the current service and the snapshot against
`KENGEN_DOKPLOY_COMPOSE_ID`, validates the stored settings, and saves the current
state before it writes the old environment. It does not restore PostgreSQL data.
Follow the database restore procedure above when the schema requires it.

For an application rollback, use the previous reviewed tag and its recorded
immutable image. The task pulls the digest and checks its platform and source
commit. The image must have been built by this release task.

```sh
mise run deploy:dokploy -- --tag v1.0.0 --image 'localhost:5050/kengen@sha256:<recorded-digest>'
```

To stop automatic releases, unset `KENGEN_DEPLOY_APPROVED`, cancel a queued run,
and remove Kengen's access to the dedicated runner group if required. This does
not stop an already running container or change Keikaku's runner access.
