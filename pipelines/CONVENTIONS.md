# Pipeline conventions

All Ops Manager automation pipelines in this foundation follow the pattern
established by `deploy-tkgi` (platform-automation style). New pipelines MUST
be built this way.

## Standard resources

```yaml
resources:
- name: platform-automation-tasks        # task scripts (git, jump box)
  type: git
  source:
    uri: ubuntu@192.168.2.85:/home/ubuntu/git/platform-automation-tasks.git
    branch: main
    private_key: ((git-ssh-key.private_key))
- name: <product>-config                 # env.yml + product config (git, jump box)
  type: git
  source:
    uri: ubuntu@192.168.2.85:/home/ubuntu/git/<product>-config.git
    branch: main
    private_key: ((git-ssh-key.private_key))
- name: om-cli                           # om binary, pinned by release glob
  type: github-release
  check_every: 24h
  source: {owner: pivotal-cf, repository: om}
- name: task-image
  type: registry-image
  check_every: 24h
  source: {repository: ubuntu, tag: noble}
```

## Task shape

Every task runs a platform-automation task script with the om binary
extracted first, on `task-image`:

```yaml
- task: <name>
  image: task-image
  config:
    platform: linux
    inputs: [{name: platform-automation-tasks}, {name: env}, {name: om-cli}]
    params: {ENV_FILE: env.yml}
    run:
      path: bash
      args:
      - -c
      - |
        set -eu
        tar -xzf om-cli/om-linux-amd64-*.tar.gz -C /usr/local/bin om
        exec platform-automation-tasks/tasks/<task>.sh
  input_mapping: {env: <product>-config}
```

## Job structure for product deploy/upgrade

Full lifecycle, in this order — a job must be able to converge from an empty
Ops Manager (never assume the product is already uploaded or staged):

1. `download-product` (SOURCE: pivnet, cached `downloaded-product`/`downloaded-stemcell`)
2. `upload-stemcell` (FLOATING_STEMCELL: "true")
3. `upload-and-stage-product`
4. `configure-product`
5. `pre-deploy-check`
6. `apply-changes` (SELECTIVE_DEPLOY_PRODUCTS: <product-name>)

## Rules

- **Serialize Ops Manager access**: every job that touches Ops Manager gets
  `serial: true` and `serial_groups: [opsman]` — Ops Manager rejects
  concurrent staging/apply operations.
- **Destructive jobs never auto-trigger**: no `trigger: true` on jobs that
  delete products, clusters, or deployments (see `delete-tkgi-tile.yml`).
  Deploy/configure jobs may trigger on config-repo commits.
- **Secrets come from CredHub** (`((var))` via the tile's Colocated CredHub
  option), seeded at the team level (`/concourse/main/<name>`) so all
  pipelines share them. Never hardcode tokens/passwords in pipeline YAML —
  anyone with fly access can read them. (Known debt: the Pivnet API token in
  deploy-tkgi/upgrade-tkgi predates this rule; rotate and move it when the
  CredHub selector is enabled.)
- **Timeouts**: apply-changes tasks get `timeout: 3h` (cluster operations are
  slow).
- Keep pipeline definitions in git (this directory or the config repos), not
  only in Concourse — `fly get-pipeline` is a recovery tool, not a source of
  truth.
