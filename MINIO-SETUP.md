# MinIO S3 setup (Ops Manager VM)

MinIO runs on the Ops Manager VM (`192.168.2.85`) as an S3-compatible object
store. Its purpose here is to host the **platform-automation image tarball** so
Concourse tasks can pull it via the built-in `s3` resource (see
`pipelines/CONVENTIONS.md`). Any S3 use (artifacts, caches) can share it.

## Why these choices

- **Port 9100 (API) / 9101 (console), not 9000.** `clickhouse-server` (an Ops
  Manager observability component) already owns `127.0.0.1:9000` — see
  `TROUBLESHOOTING.md`. MinIO must avoid it.
- **Bound to `:9100` (all interfaces), not loopback.** Concourse workers live
  on the `192.168.2.x` network and must reach it at `192.168.2.85:9100`. A
  loopback-only bind (the default of some setups) is unreachable from workers.
- **systemd service under a dedicated `minio-user`,** so it survives reboots
  and doesn't run as root or the `ubuntu` login user.

## Prerequisites

- sudo on the VM, outbound HTTPS to `dl.min.io`.
- A free TCP port pair (9100/9101 here). Verify first:
  ```bash
  sudo ss -ltn | grep -E ':9100|:9101'   # expect no output
  ```

## 1. Install the binaries

```bash
curl -sSL -o /tmp/minio https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x /tmp/minio && sudo mv /tmp/minio /usr/local/bin/minio
minio --version

curl -sSL -o /tmp/mc https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x /tmp/mc && sudo mv /tmp/mc /usr/local/bin/mc
```

## 2. Data dir and service account

```bash
sudo mkdir -p /opt/minio/data
sudo useradd -r -s /sbin/nologin minio-user 2>/dev/null || true
sudo chown -R minio-user:minio-user /opt/minio
```

## 3. Credentials + options (`/etc/default/minio`, root-only)

Generate a strong root password and write the env file the service reads.
`MINIO_OPTS` is where the LAN bind and console address are set.

```bash
MINIO_PW=$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)

sudo tee /etc/default/minio >/dev/null <<EOF
MINIO_ROOT_USER=pipeline
MINIO_ROOT_PASSWORD=${MINIO_PW}
MINIO_VOLUMES=/opt/minio/data
MINIO_OPTS=--address :9100 --console-address :9101
EOF
sudo chmod 600 /etc/default/minio
```

> Record `MINIO_PW` somewhere safe — it's the S3 secret key. Here it was also
> stored in CredHub at `/concourse/main/minio` (see step 6) and, for local
> `mc` use, in `~/.minio-pw` (chmod 600).

## 4. systemd unit (`/etc/systemd/system/minio.service`)

```ini
[Unit]
Description=MinIO
After=network-online.target
Wants=network-online.target

[Service]
User=minio-user
Group=minio-user
EnvironmentFile=/etc/default/minio
ExecStart=/usr/local/bin/minio server $MINIO_VOLUMES $MINIO_OPTS
Restart=always
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

## 5. Start and verify LAN reachability

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now minio
systemctl is-active minio                       # active

# must return 200 on the LAN IP, not just 127.0.0.1:
curl -s -o /dev/null -w '%{http_code}\n' http://192.168.2.85:9100/minio/health/live
```

## 6. Client alias, bucket, and upload

```bash
source ~/.minio-pw   # sets MINIO_PW
mc alias set localminio http://192.168.2.85:9100 pipeline "$MINIO_PW"

mc mb --ignore-existing localminio/platform-automation
mc cp ~/platform-automation-image-5.5.3.tgz localminio/platform-automation/
mc ls localminio/platform-automation/
```

## 7. Make credentials available to Concourse (CredHub)

The pipelines' `s3` resource reads `((minio.access_key_id))` /
`((minio.secret_access_key))`. Seed them at the team level so all pipelines
share them. The colocated CredHub only listens on the web VM's localhost, so
seed from there:

```bash
# from the Concourse web VM (bosh ssh web); credhub_admin secret is on the
# tile's Credentials tab in Ops Manager:
TOKEN=$(curl -sk https://127.0.0.1:8443/oauth/token -d grant_type=client_credentials \
  -u "credhub_admin:<secret>" | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')
curl -sk https://127.0.0.1:8844/api/v1/data -X PUT \
  -H "authorization: bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"name":"/concourse/main/minio","type":"json",
       "value":{"access_key_id":"pipeline","secret_access_key":"<MINIO_PW>"}}'
```

## Consuming it from a Concourse pipeline

```yaml
resources:
- name: platform-automation-image
  type: s3
  source:
    endpoint: http://192.168.2.85:9100
    bucket: platform-automation
    regexp: platform-automation-image-(.*).tgz
    access_key_id: ((minio.access_key_id))
    secret_access_key: ((minio.secret_access_key))
```

The `endpoint` (not AWS) makes the built-in `s3` resource talk to MinIO;
`http://` disables TLS. Verify with `fly -t lab check-resource -r <pipeline>/platform-automation-image`.

## Operations

- **Logs / status:** `journalctl -u minio -f`, `systemctl status minio`.
- **Upload a newer image:** `mc cp platform-automation-image-<v>.tgz localminio/platform-automation/`
  — the `s3` resource's `regexp` picks the newest matching version automatically.
- **Rotate the secret:** edit `MINIO_ROOT_PASSWORD` in `/etc/default/minio`,
  `sudo systemctl restart minio`, then update `~/.minio-pw`, the `mc` alias,
  and the CredHub `/concourse/main/minio` entry.
- **Disk:** objects live under `/opt/minio/data`; watch space if you store
  large/multiple images (`df -h /opt`).

## Security notes (homelab posture)

- Traffic is plain HTTP on the internal `192.168.2.x` network. For anything
  beyond a lab, front MinIO with TLS (`MINIO_OPTS` cert flags or a reverse
  proxy) and switch the resource `endpoint` to `https://`.
- The root credentials double as the S3 access/secret key here. In a hardened
  setup, create a scoped MinIO access key (`mc admin user svcacct add`) limited
  to the `platform-automation` bucket and use that in CredHub instead of root.
