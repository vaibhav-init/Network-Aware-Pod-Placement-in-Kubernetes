import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional

import requests
from kubernetes import client, config
from kubernetes.client.rest import ApiException


NAMESPACE = os.getenv("NAMESPACE", "network-aware")
PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL",
    "http://prometheus.linkerd-viz.svc.cluster.local:9090",
).rstrip("/")
QUERY_WINDOW = os.getenv("QUERY_WINDOW", "2m")
SYNC_INTERVAL_SEC = int(os.getenv("SYNC_INTERVAL_SEC", "30"))
MIN_RPS = float(os.getenv("MIN_RPS", "0.5"))
MIN_BENEFIT = float(os.getenv("MIN_BENEFIT", "10.0"))
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "60"))
DEFAULT_LATENCY_MS = float(os.getenv("DEFAULT_LATENCY_MS", "50.0"))
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8081"))
SESSION = requests.Session()

ANNOTATION_LAST_MOVE = "network-aware/last-move-at"
ANNOTATION_TARGET_NODE = "network-aware/target-node"
ANNOTATION_MOVABLE = "network-aware/movable"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("network-rescheduler")
controller_ready = False


class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, format_str, *args):
        return

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if self.path == "/readyz":
            self.send_response(200 if controller_ready else 503)
            self.end_headers()
            self.wfile.write(b"ready" if controller_ready else b"not-ready")
            return
        self.send_response(404)
        self.end_headers()


def start_health_server():
    server = ThreadingHTTPServer(("", HEALTH_PORT), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health server listening on :%d", HEALTH_PORT)


@dataclass
class Edge:
    src: str
    dst: str
    rps: float
    p95_ms: float

    @property
    def benefit(self) -> float:
        return self.rps * self.p95_ms


def load_kube():
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes config")
    except Exception:
        config.load_kube_config()
        logger.info("Loaded local kubeconfig")


def query_prometheus(query: str) -> List[dict]:
    response = SESSION.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={"query": query},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload}")
    return payload.get("data", {}).get("result", [])


def query_edges() -> List[Edge]:
    rps_query = (
        "sum by (deployment, dst_deployment) ("
        f'rate(response_total{{namespace="{NAMESPACE}",dst_namespace="{NAMESPACE}",'
        'direction="outbound",deployment!="",dst_deployment!=""}'
        f"[{QUERY_WINDOW}])"
        ")"
    )
    latency_query = (
        "histogram_quantile(0.95, "
        "sum by (le, deployment, dst_deployment) ("
        f'rate(response_latency_ms_bucket{{namespace="{NAMESPACE}",dst_namespace="{NAMESPACE}",'
        'direction="outbound",deployment!="",dst_deployment!=""}'
        f"[{QUERY_WINDOW}])"
        "))"
    )

    rps_results = query_prometheus(rps_query)
    latency_results = query_prometheus(latency_query)

    latency_map: Dict[tuple, float] = {}
    for item in latency_results:
        metric = item.get("metric", {})
        src = metric.get("deployment")
        dst = metric.get("dst_deployment")
        if not src or not dst:
            continue
        latency_map[(src, dst)] = float(item.get("value", [0, DEFAULT_LATENCY_MS])[1])

    edges: List[Edge] = []
    for item in rps_results:
        metric = item.get("metric", {})
        src = metric.get("deployment")
        dst = metric.get("dst_deployment")
        if not src or not dst:
            continue

        rps = float(item.get("value", [0, 0])[1])
        p95_ms = latency_map.get((src, dst), DEFAULT_LATENCY_MS)
        edges.append(Edge(src=src, dst=dst, rps=rps, p95_ms=p95_ms))

    edges.sort(key=lambda edge: edge.benefit, reverse=True)
    return edges


def list_ready_pods(v1: client.CoreV1Api) -> Dict[str, List[dict]]:
    pods = v1.list_namespaced_pod(namespace=NAMESPACE)
    grouped: Dict[str, List[dict]] = {}
    for pod in pods.items:
        if pod.metadata.deletion_timestamp:
            continue
        if pod.status.phase != "Running":
            continue
        ready = any(
            condition.type == "Ready" and condition.status == "True"
            for condition in (pod.status.conditions or [])
        )
        if not ready:
            continue
        labels = pod.metadata.labels or {}
        app = labels.get("app")
        if not app or not pod.spec.node_name:
            continue
        grouped.setdefault(app, []).append(
            {
                "name": pod.metadata.name,
                "node": pod.spec.node_name,
            }
        )
    return grouped


def list_node_allocatable(v1: client.CoreV1Api) -> Dict[str, dict]:
    result = {}
    for node in v1.list_node().items:
        conditions = {item.type: item.status for item in (node.status.conditions or [])}
        if conditions.get("Ready") != "True":
            continue
        alloc = node.status.allocatable or {}
        result[node.metadata.name] = {
            "cpu": parse_cpu(alloc.get("cpu", "0")),
            "memory_mb": parse_memory_mb(alloc.get("memory", "0")),
        }
    return result


def list_node_usage(v1: client.CoreV1Api) -> Dict[str, dict]:
    result: Dict[str, dict] = {}
    pods = v1.list_pod_for_all_namespaces()
    for pod in pods.items:
        node = pod.spec.node_name
        if not node or pod.status.phase != "Running":
            continue
        result.setdefault(node, {"cpu": 0.0, "memory_mb": 0.0})
        for container in pod.spec.containers or []:
            requests_map = (container.resources.requests or {}) if container.resources else {}
            result[node]["cpu"] += parse_cpu(requests_map.get("cpu", "0"))
            result[node]["memory_mb"] += parse_memory_mb(requests_map.get("memory", "0"))
    return result


def parse_cpu(value: str) -> float:
    text = str(value)
    if text.endswith("m"):
        return float(text[:-1]) / 1000.0
    return float(text or 0)


def parse_memory_mb(value: str) -> float:
    text = str(value)
    units = {
        "Ki": 1 / 1024,
        "Mi": 1,
        "Gi": 1024,
        "Ti": 1024 * 1024,
        "K": 1 / 1000,
        "M": 1,
        "G": 1000,
        "T": 1000 * 1000,
    }
    for suffix, multiplier in units.items():
        if text.endswith(suffix):
            return float(text[: -len(suffix)]) * multiplier
    return float(text or 0) / (1024 * 1024)


def deployment_pod_request(deployment: client.V1Deployment) -> dict:
    total_cpu = 0.0
    total_memory_mb = 0.0
    for container in deployment.spec.template.spec.containers or []:
        requests_map = (container.resources.requests or {}) if container.resources else {}
        total_cpu += parse_cpu(requests_map.get("cpu", "0"))
        total_memory_mb += parse_memory_mb(requests_map.get("memory", "0"))
    return {"cpu": total_cpu, "memory_mb": total_memory_mb}


def target_has_capacity(
    request_totals: dict,
    node_name: str,
    node_allocatable: Dict[str, dict],
    node_usage: Dict[str, dict],
) -> bool:
    alloc = node_allocatable.get(node_name)
    if not alloc:
        return False
    usage = node_usage.get(node_name, {"cpu": 0.0, "memory_mb": 0.0})
    return (
        usage["cpu"] + request_totals["cpu"] <= alloc["cpu"]
        and usage["memory_mb"] + request_totals["memory_mb"] <= alloc["memory_mb"]
    )


def is_movable(deployment: client.V1Deployment) -> bool:
    annotations = deployment.metadata.annotations or {}
    return annotations.get(ANNOTATION_MOVABLE, "false").lower() == "true"


def cooldown_elapsed(deployment: client.V1Deployment) -> bool:
    annotations = deployment.metadata.annotations or {}
    last_move = annotations.get(ANNOTATION_LAST_MOVE)
    if not last_move:
        return True
    try:
        previous = datetime.fromisoformat(last_move.replace("Z", "+00:00"))
    except ValueError:
        return True
    return datetime.now(timezone.utc) - previous >= timedelta(seconds=COOLDOWN_SEC)


def current_target(deployment: client.V1Deployment) -> Optional[str]:
    annotations = deployment.metadata.annotations or {}
    return annotations.get(ANNOTATION_TARGET_NODE)


def patch_deployment_target(apps_api: client.AppsV1Api, deployment_name: str, node_name: str):
    now = datetime.now(timezone.utc).isoformat()
    body = {
        "metadata": {
            "annotations": {
                ANNOTATION_LAST_MOVE: now,
                ANNOTATION_TARGET_NODE: node_name,
            }
        },
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "network-aware/rollout-at": now,
                    }
                },
                "spec": {
                    "affinity": {
                        "nodeAffinity": {
                            "requiredDuringSchedulingIgnoredDuringExecution": {
                                "nodeSelectorTerms": [
                                    {
                                        "matchExpressions": [
                                            {
                                                "key": "kubernetes.io/hostname",
                                                "operator": "In",
                                                "values": [node_name],
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                },
            }
        },
    }
    apps_api.patch_namespaced_deployment(
        name=deployment_name,
        namespace=NAMESPACE,
        body=body,
    )



def main():
    global controller_ready
    load_kube()
    start_health_server()
    apps_api = client.AppsV1Api()
    v1 = client.CoreV1Api()
    logger.info("Network rescheduler started for namespace %s", NAMESPACE)

    while True:
        try:
            deployments = {
                item.metadata.name: item
                for item in apps_api.list_namespaced_deployment(namespace=NAMESPACE).items
            }
            ready_pods = list_ready_pods(v1)
            node_allocatable = list_node_allocatable(v1)
            node_usage = list_node_usage(v1)
            edges = query_edges()
            controller_ready = True

            candidate: Optional[Edge] = None
            candidate_target: Optional[str] = None

            for edge in edges:
                if edge.rps < MIN_RPS or edge.benefit < MIN_BENEFIT:
                    continue

                src_deployment = deployments.get(edge.src)
                dst_deployment = deployments.get(edge.dst)
                src_pods = ready_pods.get(edge.src, [])
                dst_pods = ready_pods.get(edge.dst, [])
                if not src_deployment or not dst_deployment or not src_pods or not dst_pods:
                    continue
                if not is_movable(src_deployment):
                    continue
                if not cooldown_elapsed(src_deployment):
                    continue

                # Anti-oscillation: skip deployments already moved once
                if current_target(src_deployment) is not None:
                    continue

                src_node = src_pods[0]["node"]
                dst_node = dst_pods[0]["node"]
                if src_node == dst_node:
                    continue

                request_totals = deployment_pod_request(src_deployment)
                if not target_has_capacity(request_totals, dst_node, node_allocatable, node_usage):
                    continue

                candidate = edge
                candidate_target = dst_node
                break

            if candidate and candidate_target:
                logger.info(
                    "Moving %s toward %s on node %s (rps=%.3f p95=%.2fms benefit=%.2f)",
                    candidate.src,
                    candidate.dst,
                    candidate_target,
                    candidate.rps,
                    candidate.p95_ms,
                    candidate.benefit,
                )
                patch_deployment_target(apps_api, candidate.src, candidate_target)
            else:
                logger.info("No rollout needed in this cycle")

        except requests.RequestException as exc:
            controller_ready = False
            logger.warning("Prometheus query failed: %s", exc)
        except ApiException as exc:
            controller_ready = False
            logger.warning("Kubernetes API failed: %s", exc)
        except Exception as exc:
            controller_ready = False
            logger.exception("Unexpected controller error: %s", exc)

        time.sleep(SYNC_INTERVAL_SEC)


if __name__ == "__main__":
    main()
