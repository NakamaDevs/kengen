#!/bin/sh
# Validate the required Dokploy environment before Docker Compose reads it.
set -eu

: "${KENGEN_IMAGE_DIGEST:?KENGEN_IMAGE_DIGEST must be set}"
: "${KENGEN_OIDC_ISSUER:?KENGEN_OIDC_ISSUER must be set}"
: "${KENGEN_OIDC_AUDIENCE:?KENGEN_OIDC_AUDIENCE must be set}"
: "${KENGEN_OIDC_SUBJECTS:?KENGEN_OIDC_SUBJECTS must be set}"
: "${KENGEN_POSTGRES_PASSWORD:?KENGEN_POSTGRES_PASSWORD must be set}"

case "$KENGEN_IMAGE_DIGEST" in
  *@sha256:*) ;;
  *)
    printf '%s\n' 'KENGEN_IMAGE_DIGEST must include @sha256:' >&2
    exit 1
    ;;
esac

case "$KENGEN_OIDC_ISSUER" in
  https://?*) ;;
  *)
    printf '%s\n' 'KENGEN_OIDC_ISSUER must start with https://' >&2
    exit 1
    ;;
esac

case "$KENGEN_OIDC_SUBJECTS" in
  *[[:space:]]*|,*|*,|*,,*)
    printf '%s\n' 'KENGEN_OIDC_SUBJECTS must be a comma-separated list without whitespace' >&2
    exit 1
    ;;
  *[![:space:]]*) ;;
  *)
    printf '%s\n' 'KENGEN_OIDC_SUBJECTS must not be empty' >&2
    exit 1
    ;;
esac

if [ "${1:-}" = "--validate-only" ]; then
  exit 0
fi

exec docker compose -f "$(dirname "$0")/production.compose.yaml" config --quiet
