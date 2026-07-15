# Troubleshooting

Operational runbooks for this foundation. Each entry is a real investigation,
written so the *method* is reusable, not just the answer.

---

## Identifying which application owns an unknown service (case: clickhouse-server)

**Situation.** While setting up minio I found `clickhouse-server` listening on
`127.0.0.1:9000` on the Ops Manager VM (`192.168.2.85`). Nobody remembered
installing it. Goal: find out what it is, whether it's safe, and what depends
on it — *before* touching it or claiming the port.

The general principle: a datastore is rarely interesting on its own. Find the
**process talking to it**, and that process tells you the purpose.

### Steps

**1. Confirm what owns the port** (don't assume from the port number).

```bash
sudo ss -ltnp | grep ':9000'
# users:(("clickhouse-serv",pid=1215,fd=45))
```

This proved `:9000` was clickhouse, not minio — which is also why minio had to
go on `:9100`.

**2. Establish it's a managed service, not an ad-hoc process, and how old.**

```bash
systemctl status clickhouse-server | head -6
# Active: active (running) since Sat 2026-05-30 ...  (enabled)
```

Enabled + running for weeks = part of the platform's normal state, not a stray
manual run. Note the start date — it often coincides with a setup/upgrade.

**3. Find who connects to it — this is the key step.** A backing store has
clients; the client is the real answer. Look for established connections to its
ports (clickhouse uses `:9000` native and `:8123` HTTP).

```bash
sudo ss -tnp | grep -E ':9000|:8123' | grep ESTAB
# 127.0.0.1:50336 127.0.0.1:8123 users:(("java",pid=1026,...))
```

A `java` process (pid 1026) held persistent connections to clickhouse's HTTP
port. That process is the owner of the "why".

**4. Identify the client process by its full command line.** The `-jar` path
and config flags name the application.

```bash
sudo ps -o pid,user,cmd -p 1026
# tempest-web  .../observability-store/bin/jre/bin/java -jar
#   .../ensemble-observability-store.jar --spring.config...
```

**5. Confirm via its service unit and paths.**

```bash
sudo cat /proc/1026/cgroup | grep -oE '[a-zA-Z0-9._-]+\.service'   # observability-store.service
sudo readlink /proc/1026/cwd                                        # /var/vcap/sys/log/observability-store
sudo ss -ltnp | grep pid=1026                                       # listens on :4010
```

### Conclusion

- **What it is:** clickhouse is the backing datastore for **Ops Manager's
  `observability-store`** component (`ensemble-observability-store.jar`, a
  Spring Boot app on `:4010`, running as `tempest-web`).
- **Why "jump box" == Ops Manager:** the `tempest-web` user and `/var/vcap/...`
  BOSH-managed paths mean `192.168.2.85` *is* the Ops Manager VM (tempest is
  Ops Manager's internal codename), not a separate jump host.
- **Safe?** Yes — it's a built-in Ops Manager dependency, installed when this
  Ops Manager was set up/upgraded (matches the May 30 start date). **Do not
  disable it**; that breaks Ops Manager's observability page.

### Inspecting the clickhouse database itself (optional)

The default client needs auth we didn't have, so we read the on-disk layout
instead — database and table *names* usually reveal purpose without querying:

```bash
sudo ls /var/lib/clickhouse/data/                      # one dir per database
# non-system tables hint at what's stored:
for db in $(sudo ls /var/lib/clickhouse/data/ | grep -vE '^(system|.*_schema|default)$'); do
  echo "$db -> $(sudo ls /var/lib/clickhouse/data/$db/)"
done
sudo grep -rhoE '<(tcp_port|http_port|listen_host)>[^<]*' /etc/clickhouse-server/   # its ports
```

If you do have client access: `clickhouse-client -q "SHOW DATABASES"` then
`SHOW TABLES FROM <db>` gives the same picture faster.

### Reusable checklist for any unknown listener

1. `ss -ltnp` → what process/pid owns the port (verify, don't guess).
2. `systemctl status <svc>` → managed? enabled? since when?
3. `ss -tnp | grep ESTAB` on its ports → who connects (the client is the "why").
4. `ps -o cmd -p <client-pid>` → the client's command line names the app.
5. `/proc/<pid>/cgroup`, `cwd`, service unit → confirm ownership and paths.
6. Only then decide if it's safe to touch. Platform components (`/var/vcap`,
   vendor users) are almost always load-bearing — leave them alone.
