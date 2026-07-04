# Concourse Ops Manager Tile

A VMware Tanzu Ops Manager tile that packages [Concourse CI](https://concourse-ci.org/) 7.9 for deployment through Ops Manager on vSphere. The tile deploys three instance groups:

| Instance group | Jobs (release) | Purpose |
|---|---|---|
| `web` | `web` (concourse), `bpm` (bpm) | Concourse ATC/web UI and TSA worker gateway, TLS on 443 |
| `worker` | `worker` (concourse) | General build workers; register with the web node's TSA via BOSH links |
| `tagged_worker` | `worker` (concourse) | Workers advertising a configurable tag (default 0 instances) |
| `db` | `postgres` (postgres) | PostgreSQL hosting the `atc` database |

Ops Manager auto-generates the credentials wired between them (postgres password, token signing key, TSA host key, worker SSH key) via the tile's `variables:` section — nothing to manage by hand.

## Repository layout

The tile is built with [kiln](https://github.com/pivotal-cf/kiln). `kiln bake` interpolates `base.yml`, pulling in the parts by name:

```
base.yml               Top-level metadata template ($( version ), $( icon ), releases, part refs)
properties/            One property blueprint per file (credentials, external_url,
                       tls_credentials, auth_selector)
forms/settings.yml     The operator configuration form
instance_groups/       web.yml, worker.yml, db.yml — BOSH instance groups and their manifests
Kilnfile{,.lock}       Release pinning (bpm 1.1.21, concourse 7.9.0, postgres 44 from bosh.io)
version                Current tile version (single line)
icon.png               Tile icon (base64-embedded at bake time)
releases/              Release tarballs (gitignored; restore with `kiln fetch`)
bin/kiln               kiln binary (gitignored; darwin-arm64 from the kiln GitHub releases)
```

## How and why the tile is built with kiln

**What a tile actually is.** A `.pivotal` file is nothing exotic — it is a zip archive with a fixed folder layout:

```
metadata/metadata.yml    one big YAML file describing the whole product
releases/*.tgz           the BOSH release tarballs containing the actual software
migrations/              scripts for upgrading settings between tile versions
```

The `metadata.yml` is the heart of it. It tells Ops Manager everything: what forms to show the operator, what properties exist, what VMs to create, and how to turn the operator's form answers into a BOSH deployment manifest. For this tile that file is ~1,900 lines. You *could* maintain it by hand — this project originally did — but a file that long, with an embedded base64 icon and repeated boilerplate, is easy to break and hard to review.

**What kiln does.** [kiln](https://github.com/pivotal-cf/kiln) is the tile build tool. `kiln bake` is essentially a smart "assemble and zip" step. When you run it, it:

1. **Starts from `base.yml`**, a template of the metadata with placeholders like `$( version )`, `$( icon )`, and `$( property "auth_selector" )` where content should be injected.
2. **Fills in each placeholder**: the version comes from the `version` file; the icon is read from `icon.png` and base64-encoded automatically (no hand-pasting a wall of base64); each `$( property ... )`, `$( form ... )`, and `$( instance_group ... )` is replaced with the contents of the matching file in `properties/`, `forms/`, or `instance_groups/`.
3. **Resolves the releases** from `Kilnfile.lock`, which pins each BOSH release to an exact version *and* SHA1 checksum. Kiln verifies the tarballs in `releases/` match those checksums, and reads each tarball's internal manifest so the metadata's release list can never drift from what is actually bundled.
4. **Stamps provenance**: the current git commit SHA is embedded in the metadata (`kiln_metadata`), so any tile found in the wild can be traced back to the exact source that produced it. This is why kiln requires the project to be a git repository.
5. **Zips it all up** in the layout above and writes the `.pivotal`.

**Why this beats hand-editing one big YAML file:**

- *Small reviewable pieces.* A change to LDAP settings touches `properties/auth_selector.yml` and `forms/settings.yml` — a focused diff — instead of edits scattered through a 1,900-line file.
- *Reproducible builds.* Anyone who clones this repo can run `kiln fetch` (which re-downloads the exact pinned releases and verifies their checksums) followed by `kiln bake` and get the same tile. Nothing depends on files that happen to be lying around on someone's laptop.
- *Pinned, verified ingredients.* `Kilnfile.lock` works like a package-manager lockfile: bumping Concourse is an explicit, reviewable one-line change, and a corrupted or tampered download fails the checksum comparison instead of silently shipping.
- *No error-prone mechanical steps.* Version, icon encoding, release filenames, and zip layout are all derived automatically — the categories of mistake (stale version string, wrong base64, tarball/metadata mismatch) simply can't happen.
- *Traceability.* The git SHA baked into every artifact answers "which source built the tile that's running in prod?" definitively.

The trade-off is one extra concept (the template placeholders) and the git requirement — cheap compared to what it prevents.

## Prerequisites

- `./bin/kiln` — download from [kiln releases](https://github.com/pivotal-cf/kiln/releases) for your platform if missing
- Release tarballs in `releases/` — run `./bin/kiln fetch` to download them per `Kilnfile.lock`
- A git checkout (kiln stamps the git SHA into the tile metadata)
- SSH access to the jump box `ubuntu@192.168.2.85`, which has the `om` CLI and an `~/env.sh` exporting Ops Manager / BOSH / CredHub credentials

## Building and releasing a new version

1. **Edit the tile source** (`properties/`, `forms/`, `instance_groups/`, `base.yml`). To bump a BOSH release, update its entry in `Kilnfile.lock` and run `./bin/kiln fetch`.

2. **Bump the version** — Ops Manager treats uploads as immutable, so every change needs a new version:

   ```bash
   echo "0.0.56" > version
   ```

3. **Commit, then bake:**

   ```bash
   git add -A && git commit -m "describe the change"
   ./bin/kiln bake --output-file concourse-0.0.56.pivotal
   ```

4. **Upload and stage via the jump box:**

   ```bash
   scp concourse-0.0.56.pivotal ubuntu@192.168.2.85:~/
   ssh ubuntu@192.168.2.85 'source ~/env.sh && om upload-product --product ~/concourse-0.0.56.pivotal'
   ssh ubuntu@192.168.2.85 'source ~/env.sh && om stage-product --product-name concourse --product-version 0.0.56'
   ```

5. **Apply changes** from the Ops Manager UI, or:

   ```bash
   ssh ubuntu@192.168.2.85 'source ~/env.sh && om apply-changes --product-name concourse'
   ```

Notes:

- `minimum_version_for_upgrade` is `0.0.1`, so any newer version upgrades the installed tile in place, preserving operator configuration.
- Renaming or removing a configurable property between versions requires a JavaScript migration under `migrations/`; adding optional properties does not.
- Staging and configuration are rejected while an Apply Changes is running — wait for it to finish.
- The tile requires an **ubuntu-jammy** stemcell in the Ops Manager stemcell library.

## Configuration

All settings live under the tile's single **Settings** form:

- **Local Concourse User** — username/password for Concourse's built-in local auth. This user is always enabled and always on the `main` team, in both auth modes.
- **Web VM domain** — the external URL for the web UI.
- **TLS Certificate** — served by the web node on port 443.
- **Authentication** — a selector with two options that can be switched at any time (change the option, Apply Changes):
  - **Local user authentication** (default) — only the local user above.
  - **LDAP authentication** — exposes the full Concourse LDAP configuration: server host (`host:port`, no `ldap://` scheme — the port is inferred from the TLS settings), bind DN/password, TLS options (no-TLS, skip-verify, StartTLS, CA cert), user search (base DN, filter, username/id/email/name attributes), optional group search, and an LDAP username granted access to the `main` team. Grant further users/teams with `fly set-team`.

  LDAP gotchas: fill in *all* group-search fields or none — a partially configured group search breaks LDAP login (typical values: filter `(objectClass=groupOfNames)`, user attribute `DN`, group attribute `member`, name attribute `cn`). Because the local admin stays enabled, a bad LDAP config can't lock you out — log in locally and switch back.

- **Tagged Worker Pool Tag** — the tag advertised by workers in the `tagged_worker` instance group. Pipeline steps target them with `tags: [<value>]`; untagged steps never land on tagged workers. Scale the pool on the **Resource Config** page. For a tagged-only deployment, set the untagged `worker` group to 0 instances and the `tagged_worker` group to 1+.

The **Pipeline Secrets** form configures the credential manager backing `((var))` references in pipelines — a selector with three options, switchable at any time:

- **None** (default) — no credential manager.
- **CredHub** — server URL, UAA client ID/secret (needs `credhub.read` scope), CA cert or skip-verify, and a path prefix (default `/concourse`; secrets resolve at `<prefix>/TEAM/PIPELINE/name`, then `<prefix>/TEAM/name`).
- **Vault** — server URL, a periodic client token, optional Vault Enterprise namespace, CA cert or skip-verify, and the same path-prefix scheme.

## How the auth selector works (for tile authors)

Both selector options define `named_manifests` with the same snippet names (`ldap_auth_snippet`, `main_team_auth_snippet`). The web instance group's manifest references

```yaml
ldap_auth: (( .properties.auth_selector.selected_option.parsed_manifest(ldap_auth_snippet) ))
main_team:
  auth: (( .properties.auth_selector.selected_option.parsed_manifest(main_team_auth_snippet) ))
```

so whichever option is selected supplies the snippet — that shared naming is what makes switching modes work. The internal option's `ldap_auth_snippet` is `{}`, which the concourse BOSH job treats as "LDAP not configured". When adding a property to a selector option, touch three places: the option's `property_blueprints`, its snippet, and its `property_inputs` in `forms/settings.yml`.

See `CLAUDE.md` for further tile-authoring conventions and `.claude/skills/opsman/SKILL.md` for jump-box access patterns.
