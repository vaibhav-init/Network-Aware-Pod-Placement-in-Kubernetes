# Network-Aware Pod Re-Placement in Kubernetes

Team:
- Vaibhav Lakhera (MT25049)
- Anshul Chittora (MT25062)
- Vishal (MT25053)


This project demonstrates a simple final-project architecture for runtime network-aware workload placement:

- Kubernetes performs the initial placement with the default scheduler.
- A lightweight service mesh such as Linkerd observes live service-to-service traffic.
- A custom rescheduler controller reads Prometheus metrics, finds heavy cross-node communication, and rolls a movable Deployment toward its heaviest partner.
- The rollout uses normal Deployment rolling updates plus readiness probes, so the old pod is only removed after the replacement is ready.

## Project Layout

```text
apps/
  loadgen/        Traffic generator that keeps calling the gateway
  service/        Generic Python HTTP microservice image reused by all apps
controller/       Runtime rescheduler controller
docs/             Short architecture and setup notes
k8s/              Namespace, RBAC, workloads, and controller manifests
scripts/          Build, deploy, and teardown helpers
```

## Demo Topology

```text
loadgen -> gateway -> auth-service -> db-service
                  \-> user-service -> db-service
                  \-> logger-service
```

- `db-service` is the anchor and is not moved.
- `gateway`, `auth-service`, `user-service`, and `logger-service` are movable.

## How Re-Placement Works

1. Deploy the app with the default Kubernetes scheduler.
2. Linkerd injects proxies into the app pods and exports metrics to Prometheus.
3. The controller queries outbound traffic rates and latency histograms from Prometheus.
4. If a movable service is talking heavily to another service on a different node, the controller patches the source Deployment with a node-affinity target pointing to the partner's node.
5. Kubernetes rolls out a replacement pod on the target node. Once the new pod becomes ready, the old pod is terminated by the Deployment controller.

## Reproducible Demo Setup

Before deployment, label two different nodes:

```bash
kubectl label node <db-node-name> network-aware/role=anchor --overwrite
kubectl label node <app-node-name> network-aware/role=initial-app --overwrite
```

That creates a deterministic bad initial placement:

- `db-service` starts on the `anchor` node
- the app tier starts on the `initial-app` node
- the controller can then visibly repair the placement during the demo

## Prerequisites

- A working Kubernetes cluster
- Linkerd and Linkerd Viz installed manually by you
- Docker
- Access to each worker node's `containerd` if you want to copy images without a registry

## Build

```bash
WORKER_NODES="user@worker-a user@worker-b" ./scripts/19_build-images.sh

# If Docker build networking is restricted on your machine:
DOCKER_BUILD_FLAGS="--network=host" WORKER_NODES="user@worker-a user@worker-b" ./scripts/19_build-images.sh
```

## Deploy

```bash
./scripts/19_deploy.sh
```

## Observe

```bash
kubectl -n network-aware get pods -o wide
kubectl -n network-aware logs -f deploy/network-rescheduler
kubectl -n network-aware rollout status deploy/auth-service
```

## Collect Results

Run the experiment collector after deployment:

```bash
./scripts/19_run-experiment.sh
```

What it does:

- opens a local port-forward to Linkerd Viz Prometheus
- polls pod placement and service-to-service metrics
- stores CSV, JSON, logs, and SVG plots under `results/<timestamp>/`
- finalizes the session when you press `Ctrl+C`

If you also want the controller to stop automatically when the collection session ends:

```bash
STOP_CONTROLLER_ON_EXIT=true ./scripts/19_run-experiment.sh
```

You can also stop it manually later:

```bash
./scripts/19_stop-controller.sh
```

Generated outputs include:

- `19_placements.csv`
- `19_service_edges.csv`
- `19_deployments.csv`
- `19_loadgen_metrics.csv`
- `19_move_events.csv`
- `19_summary.json`
- `plots/19_edge_p95_comparison.svg`
- `plots/19_loadgen_latency.svg`

## Tear Down

```bash
./scripts/19_teardown.sh
```
