# Network-Aware Pod Placement in Kubernetes

Team:
- Vaibhav Lakhera (MT25049)
- Vishal (MT25053)
- Anshul (MT25062)

This project studies how **pod placement** affects **network latency** in Kubernetes cluster.

We deploy a **client pod** and a **server pod** and measure the communication latency between them.

Two cases were tested:
- Pods on different nodes
- Pods on the same node
and measured latency using curl response time.

Results show that **pods on the same node have slightly lower latency** compared to pods on different nodes.

Files:
- `G_19_kind-config.yaml` – cluster configuration
- `G_19_server-pod.yaml` – server pod
- `G_19_server-service.yaml` – service for server
- `G_19_client-pod.yaml` – client pod
- `G_19_results.csv` – latency measurements
- `G_19_plot_latency.py` – plotting script
- `G_19_latency_plot.png` – generated latency plot
- `G_19_report.pdf` – project report

Commands to Run:

1. Create Kubernetes Cluster using Kind:
```bash
kind create cluster --name net-scheduler --config G_19_kind-config.yaml
```

2. Deploy Server Pod:
```bash
kubectl apply -f G_19_server-pod.yaml
```

3. Create Service for Server:
```bash
kubectl apply -f G_19_server-service.yaml
```

4. Deploy Client Pod:
```bash
kubectl apply -f G_19_client-pod.yaml
```

5. Verify Pods by checking running:
```bash
kubectl get pods -o wide
```

6. Measure Latency:
```bash
kubectl exec client -- curl -w "%{time_total}\n" -o /dev/null -s server-service:8000
```

7. Generate latency Plot:
```bash
python G_19_plot_latency.py
```
This outputs the latency comparison graph plot.