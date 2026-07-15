# Pipeline conventions

All Ops Manager automation pipelines in this foundation follow the pattern
established by `deploy-tkgi` (platform-automation style). New pipelines MUST
be built this way.

## Standard resources

Tasks run on the **official platform-automation image** (om, bosh, credhub,
python, CA certs pre-baked), served from minio on the Ops Manager VM
(`http://192.168.2.85:9100`, bucket `platform-automation`). Do NOT use a bare
`ubuntu` image with per-task tool bootstrapping — that caused a long tail of
apt / CA-cert / python3 / interactive-hang failures. The image is Broadcom-
gated; the tarball lives at `~/platform-automation-image-*.tgz` on the Ops
Manager VM and is uploaded to the minio bucket (`mc cp`). minio runs as a
systemd service (`/etc/systemd/system/minio.service`, creds in
`/etc/default/minio`, also in CredHub `/concourse/main/minio`).

```yaml
resources:
- name: platform-automation-tasks        # task scripts (git, Ops Manager VM)
  type: git
  source:
    uri: ubuntu@192.168.2.85:/home/ubuntu/git/platform-automation-tasks.git
    branch: main
    private_key: ((git-ssh-key.private_key))
- name: <product>-config                 # env.yml + product config (git)
  type: git
  source:
    uri: ubuntu@192.168.2.85:/home/ubuntu/git/<product>-config.git
    branch: main
    private_key: ((git-ssh-key.private_key))
- name: platform-automation-image        # task image, from minio (S3)
  type: s3
  source:
    endpoint: http://192.168.2.85:9100
    bucket: platform-automation
    regexp: platform-automation-image-(.*).tgz
    access_key_id: ((minio.access_key_id))
    secret_access_key: ((minio.secret_access_key))
```

## Task shape

Fetch the image (`unpack: true`) once in the job's initial `in_parallel`, then
every task runs on it with **no bootstrap** — the tools are already present:

```yaml
- get: platform-automation-image
  params: {unpack: true}
...
- task: <name>
  image: platform-automation-image
  config:
    platform: linux
    inputs: [{name: platform-automation-tasks}, {name: env}]
    params: {ENV_FILE: env.yml}
    run:
      path: platform-automation-tasks/tasks/<task>.sh
  input_mapping: {env: <product>-config}
```

## Job structure for product deploy/upgrade

Full lifecycle, in this order — a job must be able to converge from an empty
Ops Manager (never assume the product is already uploaded or staged):

1. `download-product` (SOURCE: pivnet, cached `downloaded-product`/`downloaded-stemcell`)
2. `upload-stemcell` (FLOATING_STEMCELL: "false" — see stemcell rule below)
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
- **Stemcell uploads are non-floating** (`FLOATING_STEMCELL: "false"`). A
  floating upload assigns the new stemcell to *every* compatible product,
  including the BOSH Director — which forces the director VM to be recreated
  on the next apply-changes (Ops Manager has no per-product float opt-out).
  Non-floating uploads only assign to products that have no stemcell of that
  line yet, so the director and other pinned products stay put. A product
  that genuinely needs a newer stemcell gets it via an explicit
  `assign-stemcell` step, which never touches the director.
- **No per-task tool bootstrapping.** The platform-automation image already
  has om, bosh, credhub, python3, and CA certs. Do not `apt-get install`,
  download `om`/`bosh`, or add tool self-checks in tasks — that whole pattern
  (and its apt CA-cert / python3 / `DEBIAN_FRONTEND` interactive-hang failure
  modes) is why we moved off bare `ubuntu`. If a task needs a tool the image
  lacks, add it to the image, not the task.
- Keep pipeline definitions in git (this directory or the config repos), not
  only in Concourse — `fly get-pipeline` is a recovery tool, not a source of
  truth.
