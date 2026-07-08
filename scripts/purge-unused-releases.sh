#!/bin/bash
# Delete every BOSH release version the director is not actively using,
# then run `bosh clean-up --all` for orphaned blobs/disks.
#
# Used to recover the director when its persistent disk fills with stale
# release blobs (e.g. after deleting a product like TAS, or accumulating
# many tile versions). A full disk corrupts in-flight release uploads
# (symptom: "Job 'x' not found in release 'x'" from a hollow release
# record) and eventually wedges the director API entirely (bare 500s).
#
# Run from the jump box (needs bosh CLI + ~/env.sh):
#   ./purge-unused-releases.sh --dry-run   # list what would be deleted
#   ./purge-unused-releases.sh             # delete after confirmation
#
# Safety properties:
# - Only versions NOT marked in-use (no "*" in `bosh releases`) are touched.
#   Releases referenced by a deployed deployment are never candidates.
# - Releases protected by runtime configs (bosh-dns, syslog, ...) refuse
#   deletion server-side and are logged as SKIPPED.
# - Deleting a tile's bundled releases is safe: Ops Manager re-uploads any
#   missing release from the .pivotal on the next Apply Changes.
#
# If the director is so full that even deletes return 500, first free the
# old task logs on the director VM (ssh in with the bbr key from
# /api/v0/deployed/director/credentials/bbr_ssh_credentials):
#   sudo rm -rf /var/vcap/store/director/tasks/*

set -u
source ~/env.sh >/dev/null 2>&1 || { echo "cannot source ~/env.sh"; exit 1; }

list=$(bosh releases --json 2>/dev/null | python3 -c '
import json, sys
for row in json.load(sys.stdin)["Tables"][0]["Rows"]:
    v = row["version"]
    if not v.endswith("*"):
        print(row["name"] + "/" + v)')

total=$(printf "%s" "$list" | grep -c . || true)
if [ "$total" -eq 0 ]; then
  echo "No unused release versions found."
  exit 0
fi

echo "Unused release versions ($total):"
printf "%s\n" "$list"

if [ "${1:-}" = "--dry-run" ]; then
  echo "(dry run — nothing deleted)"
  exit 0
fi

printf "Delete all %s release versions? [y/N] " "$total"
read -r answer
[ "$answer" = "y" ] || { echo "aborted"; exit 1; }

i=0
printf "%s\n" "$list" | while read -r rel; do
  i=$((i + 1))
  if bosh -n delete-release "$rel" >/dev/null 2>&1; then
    echo "$i/$total deleted $rel"
  else
    echo "$i/$total SKIPPED $rel (in use or protected)"
  fi
done

echo "Running bosh clean-up --all ..."
bosh -n clean-up --all 2>&1 | tail -3
echo "PURGE_DONE"
