# Release Notes

## 1.2.1 — 2026-07-07

### Removed: GoRouter route registration and the TAS dependency

The TAS (`cf`) tile was retired from the foundation, so Concourse 1.2.0's `requires_product_versions: cf` blocked deployment ("Product Concourse 7.9 depends on cf (>=1.0)"). This release removes everything that coupled the tile to TAS:

- The `requires_product_versions: cf` declaration.
- The **Routing** form and its Direct/GoRouter selector — direct access (your own DNS + the tile's TLS certificate) is again the only mode, as before 1.1.0.
- The `route_registrar` job from the web VM, its NATS-TLS wiring, and the bundled routing-release (tile shrinks ~30MB).
- A metadata migration deletes the stored `gorouter_selector` value on upgrade so no orphaned configuration is carried forward.

The colocated CredHub feature from 1.2.0 is unaffected — it is fully self-contained. All 1.2.0 upgrade notes (web VM RAM ≥ 4GB) still apply.

**Restoring GoRouter later:** the feature cannot be dormant in the tile (the route_registrar job and its `nats-tls` link are active regardless of selector choice, so the tile hard-requires TAS whenever they are present). If a TAS tile is installed again, `git revert 0141de5` restores the complete, previously-deployed implementation (added in commit `33529c9`); bump the version, `kiln fetch && kiln bake`, upload.

## 1.2.0 — 2026-07-07

### New feature: Colocated CredHub pipeline secrets backend

The **Pipeline Secrets** form gains a **Colocated CredHub** option (the selector is now None / Colocated CredHub / External CredHub / Vault, switchable at any time). Selecting it gives Concourse its own self-contained credential manager for pipeline `((vars))` with **zero configuration fields**:

- CredHub 2.12.16 and UAA 76.4.0 run colocated on the web VM — the versions pinned by `concourse-bosh-deployment` v7.9.0, the upstream-tested combination for Concourse 7.9. UAA serves only as CredHub's OAuth server; Concourse user login (local/LDAP) is unaffected.
- All credentials are auto-generated BOSH variables: an internal CA, TLS certificates for UAA and CredHub with `127.0.0.1`/`localhost` SANs, UAA's 4096-bit JWT signing key, OAuth client secrets, and CredHub's 40-character encryption password.
- UAA and CredHub state lives in new `uaa` and `credhub` databases on the tile's own postgres (db VM), discovered via implicit BOSH links — no addresses or credentials are wired by hand.
- Concourse connects over `https://127.0.0.1:8844`. This deviates deliberately from upstream (which uses `external_url:8443/8844`): localhost URLs keep the **GoRouter routing mode working**, since gorouter only fronts port 443.
- Pipeline secrets resolve from `/concourse/TEAM/PIPELINE/name`, then `/concourse/TEAM/name`. Administer secrets with the `credhub_admin` OAuth client — its generated secret is on the tile's Credentials tab.

### Upgrade notes — read before Apply Changes

- **Raise the web VM's RAM to at least 4GB in Resource Config.** The UAA and CredHub JVMs run on the web VM in *every* secrets mode (BOSH cannot conditionally colocate jobs — the selector controls whether Concourse uses them, not whether they run). New installations default to 4096MB; **existing installations keep their previously configured value** and must be raised manually.
- Two new BOSH releases are bundled (uaa 76.4.0, credhub 2.12.16); the `.pivotal` grows to ~2.2GB.
- The db VM's postgres gains `uaa` and `credhub` databases and roles automatically.

### Internal changes

- The web instance group moved to **per-template manifests** — each of its five jobs (web, bpm, route_registrar, uaa, credhub) now carries its own properties block. This was required because the concourse `web` job (CredHub *client* config) and the `credhub` server job both consume a `credhub:` property with different schemas.
- New auto-generated variables: `uaa_db_password`, `uaa_users_admin`, `uaa_admin`, `uaa_login`, `uaa_jwt`, `uaa_encryption_key`, `credhub_db_password`, `credhub_encryption_password`, `concourse_to_credhub_client_secret`, `credhub_admin_secret`, `internal_tls_ca`, `uaa_ssl`, `credhub_tls`.

---

## 1.1.1 — 2026-07-05

- Restored the original tile icon; the CIBC logo remains in the repo as `icon-cibc.png`. No functional changes from 1.1.0.

## 1.1.0 — 2026-07-04

- **Optional GoRouter route registration.** New **Routing** form with a Direct/GoRouter selector. GoRouter mode registers `<hostname>.<system-domain>` as a TLS route to the web VM's port 443 (`tls_port` + `server_cert_domain_san`). `route_registrar` (routing-release 0.385.0) is colocated on the web VM and consumes the TAS deployment's shared `nats-tls` BOSH link over NATS-TLS — no NATS addresses or credentials configured by hand.
- The tile now declares `requires_product_versions: cf` — TAS must be installed (in both routing modes, since route_registrar always runs).
- When enabling GoRouter mode: add the Concourse TLS certificate's CA to "CA certificates trusted by Router" in TAS networking settings, and set the Web VM domain to the route's FQDN.

## 1.0.1 — 2026-07-04

- Tile icon changed to the wide CIBC lockup, trimmed with no padding so the dashboard renders it at full size. Added `scripts/make-icon.py` and `scripts/make-stacked-icon.py` for regenerating icons from a logo SVG/PNG.

## 1.0.0 — 2026-07-04

- Version scheme moved to 1.x. CIBC-branded tile icon.

## 0.0.56 — 2026-07-04

- **Pipeline secrets backend.** New **Pipeline Secrets** form with a None/CredHub/Vault selector wiring the concourse web job's `credhub`/`vault` config, switchable at any time.
- **Tagged worker pool.** New `tagged_worker` instance group (default 0 instances) advertising a configurable tag; pipeline steps opt in with `tags: [<value>]`. The untagged `worker` group now allows 0 instances, so a tagged-only deployment is possible.

## 0.0.55 — 2026-07-04

- Rebuilt the tile with a working authentication selector: local users (default) or LDAP with the full Concourse `ldap_auth` property set, switchable in both directions. Local admin login always remains enabled so a bad LDAP config cannot lock the operator out.
- Removed a hardcoded LDAP configuration containing plaintext bind credentials, template leftovers referencing nonexistent properties, and unused CF-coupled boilerplate on the db job.
- Moved the tile to a [kiln](https://github.com/pivotal-cf/kiln)-built source tree (`base.yml` + parts, `Kilnfile.lock`-pinned releases). Corrected the product label to Concourse 7.9 to match the bundled release.

## 0.0.54 and earlier

- Hand-maintained single-file metadata (predates this repository's git history).
