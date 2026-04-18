#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

kubectl delete -f "$PROJECT_DIR/k8s/controller.yaml" --ignore-not-found=true
kubectl delete -f "$PROJECT_DIR/k8s/apps.yaml" --ignore-not-found=true
kubectl delete -f "$PROJECT_DIR/k8s/linkerd-viz-access.yaml" --ignore-not-found=true
kubectl delete -f "$PROJECT_DIR/k8s/rbac.yaml" --ignore-not-found=true
kubectl delete -f "$PROJECT_DIR/k8s/namespace.yaml" --ignore-not-found=true
