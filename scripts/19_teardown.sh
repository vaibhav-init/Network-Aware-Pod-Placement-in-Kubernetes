#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

kubectl delete -f "$PROJECT_DIR/k8s/19_controller.yaml" --ignore-not-found=true
kubectl delete -f "$PROJECT_DIR/k8s/19_apps.yaml" --ignore-not-found=true
kubectl delete -f "$PROJECT_DIR/k8s/19_linkerd-viz-access.yaml" --ignore-not-found=true
kubectl delete -f "$PROJECT_DIR/k8s/19_rbac.yaml" --ignore-not-found=true
kubectl delete -f "$PROJECT_DIR/k8s/19_namespace.yaml" --ignore-not-found=true
