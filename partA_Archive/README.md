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
- `19_kind-config.yaml` – cluster configuration
- `19_server-pod.yaml` – server pod
- `19_server-service.yaml` – service for server
- `19_client-pod.yaml` – client pod
- `19_results.csv` – latency measurements
- `19_plot_latency.py` – plotting script
- `latency_plot.png` – generated latency plot
- `19_report.pdf` – project report

Commands to Run:

1. Create Kubernetes Cluster using Kind:
```bash
kind create cluster --name net-scheduler --config 19_kind-config.yaml
```

2. Deploy Server Pod:
```bash
kubectl apply -f 19_server-pod.yaml
```

3. Create Service for Server:
```bash
kubectl apply -f 19_server-service.yaml
```

4. Deploy Client Pod:
```bash
kubectl apply -f 19_client-pod.yaml
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
python 19_plot_latency.py
```
This outputs the latency comparison graph plot.