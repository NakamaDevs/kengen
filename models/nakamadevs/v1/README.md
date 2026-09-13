# NakamaDevs authorization model v1

`model.fga` is the canonical authorization contract for NakamaDevs applications.
It uses OpenFGA schema `1.1`.

## Identity format

Keycloak identifies each subject as `<realm-id>:<sub>`.
Use the immutable Keycloak `sub` claim and its realm identifier.
The OpenFGA boundary encodes it as `user:<realm-id>|<sub>`.
For example, `user:nakamadevs|5f5aeb53-9ec9-4f26-bc9f-6243ac77e75a` is valid.

Keycloak identifies each organization as `<realm-id>:<organization-id>`.
The OpenFGA boundary encodes it as `organization:<realm-id>|<organization-id>`.
For example, `organization:nakamadevs|acme` is only a test identifier.
Production identifiers must be opaque, stable values.

Use `EncodeSubject` and `EncodeOrganization` at every OpenFGA boundary.
The encoder rejects `|`, `:`, `#`, spaces, and control characters in components.
This prevents collisions and keeps identifiers valid for OpenFGA.

Do not use email addresses, login names, display names, or group names.
Those values can change.

The v1 model has explicit product types.
Keikaku uses `keikaku_node:<node-id>`.
Published content uses `article:<article-id>`.
Each type has its own parent relation and cannot inherit through another type.

## Relations

An organization has five ordered roles:

`owner` → `administrator` → `editor` → `commenter` → `viewer`.

Each role contains the role to its left.
Applications can grant each role directly to a user.

A Keikaku node or article can have a direct `organization`, a direct `parent`, and direct role grants.
Each role inherits from the same product type parent and organization.
A child can inherit through any number of same-type parents.

Only `viewer` can contain `user:*`.
This relation makes a resource public when it inherits from an organization or parent with a public viewer.
Public readers cannot comment, edit, administer, or own resources.

## Source of truth and migration

This directory is the source of truth for the NakamaDevs v1 contract.
OpenFGA creates an authorization-model ID when an application writes this model.
That ID is deployment state, not a source identifier.

Never change the meaning of a released model version.
Create `models/nakamadevs/v2/` for a breaking relation or identifier change.
Keep v1 loaded until no tuple or authorization request uses its model ID.

To migrate, write the new model, backfill compatible tuples, move application requests to its model ID, verify allow and deny cases, then retire the old model.
Keep the old model ID available for rollback until the migration completes.

## Upstream OpenFGA upgrades

An OpenFGA server upgrade is separate from a NakamaDevs model upgrade.
Do not change this model only because `go.mod` changes.

For every upstream OpenFGA upgrade, run the model tests against the upgraded server and validate the model through `WriteAuthorizationModel`.
Review OpenFGA schema and validation changes before creating a new NakamaDevs model version.
