---
name: opsman
description: Run om, bosh, or credhub commands against the lab Ops Manager via the jump box. Use whenever a task needs to talk to Ops Manager (upload/stage/configure/deploy tiles), BOSH, or CredHub, or to copy files (like .pivotal tiles) to the jump box.
---

# Ops Manager access via the jump box

All Ops Manager / BOSH / CredHub access goes through the Ubuntu jump box. Nothing on this Mac talks to Ops Manager directly.

- **Jump box**: `ubuntu@192.168.2.85` (passwordless SSH key auth already set up; a legal banner prints on every connection — ignore it)
- **Auth**: `~/env.sh` on the jump box exports `OM_TARGET`/`OM_USERNAME`/`OM_PASSWORD`/`OM_SKIP_SSL_VALIDATION` plus `BOSH_*` and `CREDHUB_*` variables. Source it before any CLI call.
- **CLIs available on the jump box**: `om` (at `/usr/local/bin/om`), `bosh`, `credhub`. None are installed locally.

## Running a command

```bash
ssh -o BatchMode=yes ubuntu@192.168.2.85 'source ~/env.sh && om <command>'
```

Examples:

```bash
# Ops Manager info / sanity check
ssh -o BatchMode=yes ubuntu@192.168.2.85 'source ~/env.sh && om curl -s -p /api/v0/info'

# List available and staged products
ssh -o BatchMode=yes ubuntu@192.168.2.85 'source ~/env.sh && om available-products'
ssh -o BatchMode=yes ubuntu@192.168.2.85 'source ~/env.sh && om staged-products'

# Upload a tile, then stage it
ssh -o BatchMode=yes ubuntu@192.168.2.85 'source ~/env.sh && om upload-product --product ~/concourse-<version>.pivotal'
ssh -o BatchMode=yes ubuntu@192.168.2.85 'source ~/env.sh && om stage-product --product-name concourse --product-version <version>'

# BOSH (env vars from env.sh point at the director)
ssh -o BatchMode=yes ubuntu@192.168.2.85 'source ~/env.sh && bosh deployments'
```

## Copying files to the jump box

```bash
scp <local-file> ubuntu@192.168.2.85:~/
```

Large uploads (tiles are hundreds of MB) are fine; prefer `scp` then a remote `om upload-product` rather than trying to stream.

## Notes

- Never print the contents of `env.sh` (it holds credentials); check variable names only with `grep -oE '^(export )?[A-Z_]+=' ~/env.sh` if needed.
- `om apply-changes` triggers a full deploy — confirm with the user before running it.
- For long remote operations (upload-product, apply-changes), run the ssh command in the background and poll, or use `om apply-changes` with `--reattach` if reconnecting.
