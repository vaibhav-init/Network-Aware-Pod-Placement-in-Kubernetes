#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

PROM_NAMESPACE="${PROM_NAMESPACE:-linkerd-viz}"
PROM_SERVICE="${PROM_SERVICE:-prometheus}"
PROM_LOCAL_PORT="${PROM_LOCAL_PORT:-19090}"
PROM_REMOTE_PORT="${PROM_REMOTE_PORT:-9090}"
EXPERIMENT_NAMESPACE="${EXPERIMENT_NAMESPACE:-network-aware}"
INTERVAL_SEC="${INTERVAL_SEC:-15}"
QUERY_WINDOW="${QUERY_WINDOW:-2m}"
STOP_CONTROLLER_ON_EXIT="${STOP_CONTROLLER_ON_EXIT:-false}"

echo "=============================================="
echo " Starting experiment collection"
echo "=============================================="
echo "Namespace: ${EXPERIMENT_NAMESPACE}"
echo "Prometheus: ${PROM_NAMESPACE}/${PROM_SERVICE} -> localhost:${PROM_LOCAL_PORT}"
echo "Press Ctrl+C when you want to stop and save results."

kubectl -n "${PROM_NAMESPACE}" port-forward "svc/${PROM_SERVICE}" "${PROM_LOCAL_PORT}:${PROM_REMOTE_PORT}" >/tmp/network-aware-prometheus.log 2>&1 &
PORT_FORWARD_PID=$!

cleanup() {
  if [ "${STOP_CONTROLLER_ON_EXIT}" = "true" ]; then
    kubectl -n "${EXPERIMENT_NAMESPACE}" scale deploy/network-rescheduler --replicas=0 >/dev/null 2>&1 || true
  fi
  kill "${PORT_FORWARD_PID}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

sleep 3

python3 "${PROJECT_DIR}/scripts/G_19_collect_results.py" \
  --namespace "${EXPERIMENT_NAMESPACE}" \
  --prometheus-url "http://127.0.0.1:${PROM_LOCAL_PORT}" \
  --interval "${INTERVAL_SEC}" \
  --query-window "${QUERY_WINDOW}" \
  "$@"
