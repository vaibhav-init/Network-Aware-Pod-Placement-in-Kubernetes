#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=============================================="
echo " Deploying runtime re-placement demo"
echo "=============================================="

kubectl apply -f "$PROJECT_DIR/k8s/19_namespace.yaml"
kubectl apply -f "$PROJECT_DIR/k8s/19_rbac.yaml"
kubectl apply -f "$PROJECT_DIR/k8s/19_apps.yaml"
kubectl apply -f "$PROJECT_DIR/k8s/19_linkerd-viz-access.yaml"

echo ""
echo "Waiting for app workloads..."
kubectl -n network-aware wait --for=condition=available deploy --all --timeout=180s || true

echo ""
kubectl -n network-aware get pods -o wide

echo ""
echo "Apps deployed. Controller is NOT running yet."
echo ""
echo "To run the experiment properly:"
echo "  1. Start data collection:  ./scripts/19_run-experiment.sh"
echo "  2. Wait 2-3 minutes for baseline data"
echo "  3. Start the controller:   kubectl apply -f k8s/19_controller.yaml"
echo "  4. Wait 5+ minutes for moves and stabilization"
echo "  5. Press Ctrl+C in the collection terminal to finalize results"

