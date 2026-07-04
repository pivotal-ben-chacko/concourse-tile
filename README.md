# Concourse Ops Manager Tile

A VMware Tanzu Ops Manager tile that packages [Concourse CI](https://concourse-ci.org/) 7.9 for deployment through Ops Manager on vSphere. The tile deploys three instance groups:

| Instance group | Jobs (release) | Purpose |
|---|---|---|
| `web` | `web` (concourse), `bpm` (bpm) | Concourse ATC/web UI and TSA worker gateway, TLS on 443 |
| `worker` | `worker` (concourse) | Build workers; register with the web node's TSA via BOSH links |
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

## How the auth selector works (for tile authors)

Both selector options define `named_manifests` with the same snippet names (`ldap_auth_snippet`, `main_team_auth_snippet`). The web instance group's manifest references

```yaml
ldap_auth: (( .properties.auth_selector.selected_option.parsed_manifest(ldap_auth_snippet) ))
main_team:
  auth: (( .properties.auth_selector.selected_option.parsed_manifest(main_team_auth_snippet) ))
```

so whichever option is selected supplies the snippet — that shared naming is what makes switching modes work. The internal option's `ldap_auth_snippet` is `{}`, which the concourse BOSH job treats as "LDAP not configured". When adding a property to a selector option, touch three places: the option's `property_blueprints`, its snippet, and its `property_inputs` in `forms/settings.yml`.

See `CLAUDE.md` for further tile-authoring conventions and `.claude/skills/opsman/SKILL.md` for jump-box access patterns.
