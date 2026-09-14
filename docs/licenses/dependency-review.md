# Dependency license review (NAK-911)

This policy requires independent review before merge. It does not approve a
new dependency, license, or version by matching only the MPL license name.

## Distribution evidence

The reviewed build from commit `90a65abc3efbab2173a4ecc3a783dee5b2ebfabd`
contains these module records (`go version -m`):

| Module | Version | Go source checksum |
| --- | --- | --- |
| github.com/go-sql-driver/mysql | v1.10.0 | h1:Q+1LV8DkHJvSYAdR83XzuhDaTykuDx0l6fkXxoWCWfw= |
| github.com/hashicorp/go-retryablehttp | v0.7.8 | h1:ylXZWnqa7Lhqpk0L1P1LzDtGcCR0rPVUrx/c8Unxc48= |
| github.com/hashicorp/go-cleanhttp | v0.5.2 | h1:035FKYIWjmULyFRBKPs8TBQoi0x6d9G4xc9neXJWAZQ= |

These modules are linked into the executable. This change does not modify
their source, vendor them, or replace their module versions. `go.sum` retains
the source checksums. An image or binary distributed outside the organization
also distributes their executable code.

MPL-2.0 permits a larger work under other terms while retaining the covered
source's license. Executable distribution requires access to the covered
source and a notice that tells recipients how to obtain it. Preserve source
notices and publish any future modifications to MPL-covered source under MPL.
See [MPL sections 3.1–3.4](https://www.mozilla.org/en-US/MPL/2.0/) and
[Mozilla's FAQ, questions 8, 11, 13, and 17](https://www.mozilla.org/en-US/MPL/2.0/FAQ/).

[Third-party notices](../../THIRD_PARTY_NOTICES.md) identify the exact source
archives. The Dockerfile copies these notices and Kengen's Apache-2.0 license
into the image. A separate binary release must include both files. Before
external distribution, verify each source link and preserve a source archive
with the release records. If a source link fails, provide the matching archive
to recipients. Do not distribute modified covered code using an unchanged-source
notice. Kengen's Apache-2.0 license does not relicense the MPL source.

## Gate behavior

The pinned Trivy scan still checks vulnerabilities and licenses. The wrapper
uses an empty Trivy config, no ignore file or ignore policy, and removes ambient
`TRIVY_*` settings that could filter findings. Scanner errors fail the task.

Every vulnerability fails, at every severity. Five identified notice licenses
are permitted: Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, and MIT. Each must
have the expected notice category, LOW severity, exact package metadata, and
full confidence. The only reciprocal-license exceptions are MPL-2.0 on the
three exact module/version pairs above, at MEDIUM severity and full confidence.
A new module, version, license, target, classification, or ambiguous package
version fails review. Malformed reports and absent license results also fail.

This gate evaluates Trivy's reported findings. It does not establish complete
license coverage for every package: the current scanner omits license findings
for some modules. Review the full software inventory before external release.
No blanket severity threshold or reciprocal-license suppression is used.

Run `mise run test:dependency-policy`, then `mise run review:dependencies`.
The quick and full gates both run the policy tests. Only an independently
reviewed PR may change the exception versions or notice-license list.
