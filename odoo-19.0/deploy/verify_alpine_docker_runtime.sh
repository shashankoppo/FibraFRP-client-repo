#!/bin/sh
set -eu

# Alpine/LXC Docker runtime smoke test.
# This starts a tiny disposable container and does not touch Odoo databases,
# filestores, named volumes, or application modules.

IMAGE=${ALPINE_RUNTIME_TEST_IMAGE:-alpine:3.20}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

have() {
  command -v "$1" >/dev/null 2>&1
}

have docker || fail "docker CLI is not installed."
docker info >/dev/null 2>&1 || fail "docker daemon is not reachable."
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is not installed. On Alpine run: apk add docker-cli-compose"

echo "== Alpine Docker runtime smoke test =="
echo "Image: $IMAGE"

set +e
OUTPUT=$(docker run --rm "$IMAGE" true 2>&1)
STATUS=$?
set -e

if [ "$STATUS" -eq 0 ]; then
  echo "Docker can start containers on this host."
  exit 0
fi

echo "$OUTPUT" >&2

if printf '%s\n' "$OUTPUT" | grep -q "ip_unprivileged_port_start"; then
  cat >&2 <<'EOF'

Docker failed while writing net.ipv4.ip_unprivileged_port_start.

This is a host/container runtime restriction commonly seen when Docker runs
inside an Alpine Proxmox LXC container. It happens before Odoo starts and is
not caused by client data, Odoo modules, PostgreSQL, or the repo contents.

Use one of these safe paths:

1. Preferred: run the stack on an Alpine VM, Ubuntu VM, or bare-metal Docker host.
2. For Alpine Proxmox LXC: enable nested Docker support on the Proxmox host
   for this CT, then restart Docker inside Alpine.
3. If the host cannot allow Docker network namespaces, use the LXC fallback:
   docker compose -f docker-compose.alpine-lxc.yml up -d --build

The fallback uses host networking, so ports 5432, 8069, 3000, and 8071 must be
free on the Alpine LXC host before starting the stack.
EOF
fi

exit "$STATUS"
