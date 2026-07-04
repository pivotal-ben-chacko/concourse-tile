# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A VMware Tanzu Ops Manager **tile** that packages Concourse 7.9 as an Ops Manager product, built with [kiln](https://github.com/pivotal-cf/kiln). The output is a `.pivotal` file (a zip of `metadata/`, `releases/`, `migrations/`) uploaded to Ops Manager. There is no application source code here — the "code" is the tile metadata, split into kiln template parts.

## Build and deploy commands

```bash
# Build the tile (kiln binary lives in ./bin, gitignored; darwin-arm64 from github.com/pivotal-cf/kiln releases)
./bin/kiln bake --output-file concourse-<version>.pivotal

# Re-download the BOSH release tarballs into releases/ if missing (pinned by Kilnfile.lock)
./bin/kiln fetch

# Cut a new version: edit the `version` file, commit (kiln stamps the git SHA), then bake
```

kiln requires a clean-ish git checkout — it runs `git status` to stamp `kiln_metadata` into the tile.

Ops Manager access goes through the jump box — see the `opsman` skill (`.claude/skills/opsman/SKILL.md`). Short version: `scp` the `.pivotal` to `ubuntu@192.168.2.85:~/`, then `ssh ubuntu@192.168.2.85 'source ~/env.sh && om upload-product --product ~/<file>.pivotal'`, then `om stage-product --product-name concourse --product-version <version>`. `om apply-changes` deploys — confirm with the user first. Staging/config changes are rejected while an Apply Changes is running. When sourcing `env.sh` in a script, redirect its output (`source ~/env.sh >/dev/null 2>&1`) — it prints login noise to stdout that corrupts JSON parsing of `om curl` output.

## How the tile source fits together

`kiln bake` interpolates `base.yml`, which pulls in the parts by name:

- `base.yml` — top-level metadata: product name/label, `variables:` (BOSH-generated credentials like `postgres_password`, referenced in manifests as `(((var)))`), `$( release "..." )` entries, stemcell criteria, and `$( property / form / instance_group "..." )` references.
- `properties/*.yml` — one property blueprint per file. Referenced in forms/manifests with `(( .properties.<name>.value ))` accessors.
- `forms/settings.yml` — the operator UI. Every `property_input` must reference an existing blueprint; adding a configurable property means touching both a `properties/` file and the form.
- `instance_groups/{web,worker,db}.yml` — the three BOSH instance groups. Each `manifest:` block is YAML-in-a-string that becomes that job's BOSH properties; only properties the BOSH job's spec declares belong there (web: `add_local_users`, `external_url`, `ldap_auth`, `main_team.auth`, `postgresql`, `tls`, `token_signing_key`, `worker_gateway`; worker: `drain_timeout`, `worker_gateway.worker_key`; db: `databases`). The worker finds the web node's TSA via BOSH links, not manifest properties.
- `Kilnfile` / `Kilnfile.lock` — release pinning (bpm, concourse, postgres from bosh.io, with sha1s). `stemcell_criteria` in `base.yml` is inline (not `$( stemcell )`) to keep `enable_patch_security_updates: true`; keep it in sync with the lock file when bumping stemcells.

## The auth selector pattern

`properties/auth_selector.yml` is a `selector` with `internal_option` (local users, default) and `ldap_option` branches. **Both options define `named_manifests` with the same names** (`ldap_auth_snippet`, `main_team_auth_snippet`) — that is what lets the web manifest's `parsed_manifest(...)` accessors resolve whichever option is selected, so operators can switch auth modes and redeploy freely. The internal option's `ldap_auth_snippet` is `{}` (renders `ldap_auth: {}`, which the BOSH job treats as unset).

When adding a property to a selector option, touch three places: the option's `property_blueprints`, its snippet under `named_manifests`, and the option's `property_inputs` in `forms/settings.yml`.

Invariants to preserve:

- Local admin login stays enabled in both modes (`add_local_users` plus the local user in both `main_team_auth_snippet`s) so switching to LDAP can never lock the operator out.
- Optional LDAP fields left blank render as `null`, which the concourse release treats as unset — safe. Don't give group-search fields defaults: a partially-configured group search breaks LDAP login.
