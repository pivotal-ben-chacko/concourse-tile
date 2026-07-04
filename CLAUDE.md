# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

This repo contains a single file: `concourse-0.0.55.yml` (filename tracks `product_version`), a VMware Tanzu Ops Manager **tile metadata file** (metadata_version 3.0.3) that packages Concourse 7.9 as an Ops Manager product. It is not application source code — it is the declarative product definition that Ops Manager uses to render configuration forms and generate a BOSH manifest. There is no build system or test suite in this repo; the file is edited directly and would be bundled (with the release tarballs it references) into a `.pivotal` file for upload to Ops Manager.

## File structure and how sections relate

The metadata file has interdependent top-level sections:

- **`releases`**: BOSH releases the tile bundles (concourse 7.9.0, bpm, postgres). The `file:` entries reference tarballs that must exist alongside this metadata when the tile is packaged. `stemcell_criteria` pins ubuntu-jammy.
- **`variables`**: BOSH credential variables (postgres password, token signing key, TSA host key, worker SSH key) auto-generated at deploy time. Referenced in job manifests with triple-paren syntax: `(((postgres_password)))`.
- **`property_blueprints`**: Operator-configurable properties. Referenced elsewhere with double-paren accessor syntax: `(( .properties.external_url.value ))`. The `auth_selector` blueprint is a `selector` type with `internal_option` (local users, the default) and `ldap_option` branches; the LDAP branch carries nested property_blueprints for every Concourse `ldap_auth.*` setting. **Both options define `named_manifests` with the same names** (`ldap_auth_snippet`, `main_team_auth_snippet`) — that is what lets the web manifest's `parsed_manifest(...)` accessors resolve regardless of which option is selected, so operators can switch auth modes and redeploy freely. The internal option's `ldap_auth_snippet` is `{}` (renders `ldap_auth: {}`, which the BOSH job treats as unset).
- **`form_types`**: The Ops Manager UI form. Every form `property_input` must reference an existing property blueprint by its `.properties.*` path — adding a configurable property usually means touching both `property_blueprints` and `form_types`.
- **`job_types`**: Three instance groups — `web` (Concourse ATC/TSA, templates from the concourse + bpm releases), `worker` (concourse release), and `db` (postgres release). Each `manifest:` block is a YAML string that becomes that job's BOSH properties. Only properties the BOSH job's spec actually declares belong here (web: `add_local_users`, `external_url`, `ldap_auth`, `main_team.auth`, `postgresql`, `tls`, `token_signing_key`, `worker_gateway`; worker: `drain_timeout`, `worker_gateway.worker_key`; db: `databases`). The worker finds the web node's TSA via BOSH links, not manifest properties.

## Things to keep consistent when editing

- The two reference syntaxes are distinct: `(( .properties.x.value ))` (tile properties, resolved by Ops Manager) vs `(((var)))` (BOSH variables from the `variables:` section). Job manifests are YAML-in-a-string, so indentation inside `manifest: |` blocks matters.
- Selector option accessors include the option name: `.properties.auth_selector.ldap_option.host.value`. When adding a property to a selector option, add it in three places: the option's `property_blueprints`, its snippet under `named_manifests`, and the option's `property_inputs` in `form_types`.
- Local admin login is intentionally always enabled (`add_local_users` and the local user in both `main_team_auth_snippet`s) so switching to LDAP can never lock the operator out.
- Optional LDAP fields left blank render as `null` in the manifest, which the concourse release treats as unset — safe. Avoid giving group-search fields defaults, since a partially-configured group search breaks LDAP login.
- When cutting a new version, bump `product_version` and rename the file to match (`concourse-<version>.yml`).
