# Network-Aware Pod Placement in Kubernetes

Team:
- Vaibhav Lakhera (MT25049)
- Vishal (MT25053)
- Anshul (MT25062)

This project studies how pod placement affects network latency in Kubernetes.

We deploy a **client pod** and a **server pod** and measure the communication latency between them.

Two cases were tested:
- Pods on different nodes
- Pods on the same node

Results show that **pods on the same node have slightly lower latency**.

Files:
- `kind-config.yaml` – cluster configuration
- `server-pod.yaml` – server pod
- `server-service.yaml` – service for server
- `client-pod.yaml` – client pod
- `results.csv` – latency measurements
- `plot_latency.py` – plotting script
