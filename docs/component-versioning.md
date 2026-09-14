# Independent component versions

Kengen has three separate release tracks:

| Component | Version source | Tag format | Initial component release |
| --- | --- | --- | --- |
| Authorization models | `models/VERSION` | `models/vMAJOR.MINOR.PATCH` | `models/v1.0.0` |
| Tuple viewer | `internal/viewer/VERSION` | `viewer/vMAJOR.MINOR.PATCH` | `viewer/v0.1.0` |
| OpenFGA server | Existing server release process | `vMAJOR.MINOR.PATCH` | Unchanged |

A model change does not bump the viewer or server. A viewer change does not bump
models. Component tags identify source snapshots; the viewer is still built into
the Kengen server image. Model releases do not upload or migrate a live store.
OpenFGA's generated authorization-model IDs remain separate deployment state.

Use Conventional Commits with component scopes:

- `feat(models): add a compatible relation` for a minor model release.
- `feat(models)!: change identity encoding` for a major model release.
- `fix(viewer): correct tuple pagination` for a patch viewer release.
- `feat(viewer): add a model diagram` for a minor viewer release.
- `chore(release): version viewer 0.2.0` for the version and changelog commit.

For models, any change that alters existing authorization results is a breaking
change. Create a new major contract directory, such as `models/nakamadevs/v2`,
and document its migration. Do not change the meaning of a released version.
Documentation or test corrections that preserve the contract can use patch
releases. While the viewer is below 1.0, document breaking changes in a minor
release; use major releases for breaking changes after 1.0.

## Release one component

1. Run `mise run version:show`.
2. Run `mise run version:bump -- viewer patch` (or `models minor`, for example).
3. Update that component's `CHANGELOG.md`, review the diff, and run its tests.
4. Commit the code, version, and notes with a Conventional Commit message.
5. From clean local main, run `mise run version:tag -- viewer` (or `models`).
6. Push main and that exact tag, for example:
   `git push --atomic origin main refs/tags/viewer/v0.1.1`.

The task changes only the selected version file. It does not make a commit,
contact GitHub, or bump other components. Tag creation refuses dirty checkouts,
branches other than main, and existing tag names. Never force-update release tags.

The published-release workflow accepts server tags starting with `v` only.
Publishing a `models/v...` or `viewer/v...` GitHub release does not trigger a
server deployment. Use the existing deployment task when a viewer change is
ready to go live.
