# Kengen Dokploy production runbook

This runbook deploys Kengen in Dokploy. It uses
`deploy/dokploy/production.compose.yaml` as raw Compose input.

## Scope and limits

This change does not create DNS records. It does not deploy the stack. It does
not enable GitHub Actions. It does not change runner groups.

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

`KENGEN_OIDC_SUBJECTS` is required. An empty OpenFGA OIDC subject list accepts
every subject from a valid issuer. This stack must accept only the NAK-908
service identity subject.

To rotate the service identity, use this exact temporary value:
`KENGEN_OIDC_SUBJECTS=<old-sub>,<new-sub>`. Validate the new client-credentials
token. Then remove the old subject. Do not use spaces. Do not remove the current
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
