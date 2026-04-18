#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WORKER_NODES="${WORKER_NODES:-}"
DOCKER_BUILD_FLAGS="${DOCKER_BUILD_FLAGS:-}"

IMAGES=(
  "demo-service:apps/service"
  "demo-loadgen:apps/loadgen"
  "network-rescheduler:controller"
)

echo "=============================================="
echo " Building project images"
echo "=============================================="
[ -n "$WORKER_NODES" ] && echo "Workers: $WORKER_NODES" || echo "Workers: local only"
[ -n "$DOCKER_BUILD_FLAGS" ] && echo "Build flags: $DOCKER_BUILD_FLAGS"

for entry in "${IMAGES[@]}"; do
  IFS=':' read -r image path <<< "$entry"
  echo ""
  echo "Building ${image}:latest"
  build_cmd=(docker build -f "$PROJECT_DIR/$path/19_Dockerfile" -t "${image}:latest")
  if [ -n "$DOCKER_BUILD_FLAGS" ]; then
    # shellcheck disable=SC2206
    extra_build_flags=($DOCKER_BUILD_FLAGS)
    build_cmd+=("${extra_build_flags[@]}")
  fi
  build_cmd+=("$PROJECT_DIR/$path")
  "${build_cmd[@]}"

  echo "Importing ${image}:latest into local containerd"
  docker save "${image}:latest" | sudo ctr -n=k8s.io images import -

  for worker in $WORKER_NODES; do
    echo "Sending ${image}:latest to ${worker}"
    docker save "${image}:latest" | ssh "$worker" 'sudo ctr -n=k8s.io images import -'
  done
done

echo ""
echo "Images are ready. Next: ./scripts/19_deploy.sh"
