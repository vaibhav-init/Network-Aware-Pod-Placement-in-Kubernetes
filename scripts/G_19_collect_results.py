#!/usr/bin/env python3
import argparse
import csv
import json
import math
import re
import signal
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib import parse, request


LOADGEN_PATTERN = re.compile(r"status=(?P<status>\d+)\s+latency_ms=(?P<latency>[0-9.]+)")
MOVE_PATTERN = re.compile(
    r"Moving (?P<src>[a-z0-9-]+) toward (?P<dst>[a-z0-9-]+) on node (?P<node>[a-zA-Z0-9._-]+)"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        try:
            return datetime.fromisoformat(candidate.split(" ", 1)[0])
        except ValueError:
            return None


def run_command(cmd: List[str]) -> str:
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def try_command(cmd: List[str], default: str = "") -> str:
    try:
        return run_command(cmd)
    except Exception:
        return default


def kubectl_json(namespace: str, kind: str) -> dict:
    output = run_command(["kubectl", "-n", namespace, "get", kind, "-o", "json"])
    return json.loads(output)


def kubectl_logs(namespace: str, target: str, container: str = "") -> str:
    cmd = ["kubectl", "-n", namespace, "logs", "--timestamps", target]
    if container:
        cmd.extend(["-c", container])
    return try_command(cmd)


def kubectl_events(namespace: str) -> str:
    return try_command(["kubectl", "-n", namespace, "get", "events", "--sort-by=.lastTimestamp"])


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(math.ceil(len(ordered) * pct / 100.0)) - 1, len(ordered) - 1)
    return ordered[max(index, 0)]


def query_prometheus(base_url: str, promql: str) -> List[dict]:
    query = parse.urlencode({"query": promql})
    with request.urlopen(f"{base_url}/api/v1/query?{query}", timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload}")
    return payload.get("data", {}).get("result", [])


class ExperimentCollector:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        session_name = args.session_name or datetime.now().strftime("%Y%m%d-%H%M%S")
        self.session_dir = Path(args.results_dir) / session_name
        self.plots_dir = self.session_dir / "plots"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.plots_dir.mkdir(parents=True, exist_ok=True)

        self.metadata = {
            "namespace": args.namespace,
            "prometheus_url": args.prometheus_url,
            "started_at": utc_now(),
            "poll_interval_sec": args.interval,
        }
        self.samples = 0
        self.edge_samples: Dict[str, List[dict]] = defaultdict(list)
        self.placement_samples: List[dict] = []

        self.placements_csv = self.session_dir / "G_19_placements.csv"
        self.edges_csv = self.session_dir / "G_19_service_edges.csv"
        self.deployments_csv = self.session_dir / "G_19_deployments.csv"
        self.write_csv_headers()
        self.write_metadata()

    def write_csv_headers(self):
        with self.placements_csv.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["timestamp", "pod", "app", "node", "phase", "ready", "pod_ip"]
            )
        with self.edges_csv.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["timestamp", "src", "dst", "rps", "p95_latency_ms", "benefit"]
            )
        with self.deployments_csv.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "timestamp",
                    "deployment",
                    "movable",
                    "target_node",
                    "replicas",
                    "ready_replicas",
                    "available_replicas",
                ]
            )

    def write_metadata(self):
        with (self.session_dir / "G_19_metadata.json").open("w") as handle:
            json.dump(self.metadata, handle, indent=2)

    def sample(self):
        timestamp = utc_now()
        pods = kubectl_json(self.args.namespace, "pods")
        deployments = kubectl_json(self.args.namespace, "deploy")
        edges = self.collect_edge_metrics()

        placement_rows = []
        with self.placements_csv.open("a", newline="") as handle:
            writer = csv.writer(handle)
            for item in pods.get("items", []):
                labels = item.get("metadata", {}).get("labels", {}) or {}
                ready = any(
                    condition.get("type") == "Ready" and condition.get("status") == "True"
                    for condition in item.get("status", {}).get("conditions", []) or []
                )
                row = {
                    "timestamp": timestamp,
                    "pod": item.get("metadata", {}).get("name", ""),
                    "app": labels.get("app", ""),
                    "node": item.get("spec", {}).get("nodeName", ""),
                    "phase": item.get("status", {}).get("phase", ""),
                    "ready": ready,
                    "pod_ip": item.get("status", {}).get("podIP", ""),
                }
                placement_rows.append(row)
                writer.writerow(
                    [
                        row["timestamp"],
                        row["pod"],
                        row["app"],
                        row["node"],
                        row["phase"],
                        "true" if row["ready"] else "false",
                        row["pod_ip"],
                    ]
                )

        with self.deployments_csv.open("a", newline="") as handle:
            writer = csv.writer(handle)
            for item in deployments.get("items", []):
                annotations = item.get("metadata", {}).get("annotations", {}) or {}
                writer.writerow(
                    [
                        timestamp,
                        item.get("metadata", {}).get("name", ""),
                        annotations.get("network-aware/movable", "false"),
                        annotations.get("network-aware/target-node", ""),
                        item.get("spec", {}).get("replicas", 0),
                        item.get("status", {}).get("readyReplicas", 0),
                        item.get("status", {}).get("availableReplicas", 0),
                    ]
                )

        with self.edges_csv.open("a", newline="") as handle:
            writer = csv.writer(handle)
            for edge in edges:
                writer.writerow(
                    [
                        timestamp,
                        edge["src"],
                        edge["dst"],
                        f"{edge['rps']:.6f}",
                        f"{edge['p95_ms']:.3f}",
                        f"{edge['benefit']:.3f}",
                    ]
                )
                key = f"{edge['src']}->{edge['dst']}"
                self.edge_samples[key].append({"timestamp": timestamp, **edge})

        self.placement_samples.extend(placement_rows)
        self.samples += 1
        print(
            f"[{timestamp}] collected sample #{self.samples}: "
            f"{len(placement_rows)} pods, {len(edges)} traffic edges",
            flush=True,
        )

    def collect_edge_metrics(self) -> List[dict]:
        namespace = self.args.namespace
        window = self.args.query_window
        rps_query = (
            "sum by (deployment, dst_deployment) ("
            f'rate(response_total{{namespace="{namespace}",dst_namespace="{namespace}",'
            'direction="outbound",deployment!="",dst_deployment!=""}'
            f"[{window}])"
            ")"
        )
        latency_query = (
            "histogram_quantile(0.95, "
            "sum by (le, deployment, dst_deployment) ("
            f'rate(response_latency_ms_bucket{{namespace="{namespace}",dst_namespace="{namespace}",'
            'direction="outbound",deployment!="",dst_deployment!=""}'
            f"[{window}])"
            "))"
        )

        try:
            rps_results = query_prometheus(self.args.prometheus_url, rps_query)
            latency_results = query_prometheus(self.args.prometheus_url, latency_query)
        except Exception as exc:
            print(f"Prometheus query failed for this sample: {exc}", file=sys.stderr, flush=True)
            return []

        latency_map = {}
        for item in latency_results:
            metric = item.get("metric", {})
            src = metric.get("deployment")
            dst = metric.get("dst_deployment")
            if src and dst:
                latency_map[(src, dst)] = float(item.get("value", [0, 0])[1])

        edges = []
        for item in rps_results:
            metric = item.get("metric", {})
            src = metric.get("deployment")
            dst = metric.get("dst_deployment")
            if not src or not dst:
                continue
            rps = float(item.get("value", [0, 0])[1])
            p95_ms = latency_map.get((src, dst), 0.0)
            edges.append(
                {
                    "src": src,
                    "dst": dst,
                    "rps": rps,
                    "p95_ms": p95_ms,
                    "benefit": rps * p95_ms,
                }
            )
        edges.sort(key=lambda item: item["benefit"], reverse=True)
        return edges

    def finalize(self):
        self.metadata["finished_at"] = utc_now()
        self.metadata["samples"] = self.samples
        self.write_metadata()

        try:
            pods_json = kubectl_json(self.args.namespace, "pods")
        except Exception:
            pods_json = {"items": []}
        try:
            deployments_json = kubectl_json(self.args.namespace, "deploy")
        except Exception:
            deployments_json = {"items": []}

        (self.session_dir / "G_19_pods-final.json").write_text(json.dumps(pods_json, indent=2))
        (self.session_dir / "G_19_deployments-final.json").write_text(
            json.dumps(deployments_json, indent=2)
        )
        (self.session_dir / "G_19_controller.log").write_text(
            kubectl_logs(self.args.namespace, "deploy/network-rescheduler", "controller")
        )
        (self.session_dir / "G_19_loadgen.log").write_text(
            kubectl_logs(self.args.namespace, "deploy/loadgen", "loadgen")
        )
        (self.session_dir / "G_19_events.txt").write_text(kubectl_events(self.args.namespace))

        loadgen_samples = self.parse_loadgen_log(self.session_dir / "G_19_loadgen.log")
        move_events = self.parse_controller_log(self.session_dir / "G_19_controller.log")
        self.write_loadgen_csv(loadgen_samples)
        self.write_move_csv(move_events)

        summary = self.build_summary(loadgen_samples, move_events)
        with (self.session_dir / "G_19_summary.json").open("w") as handle:
            json.dump(summary, handle, indent=2)

        self.write_edge_comparison_svg(summary.get("edge_comparison", []))
        self.write_loadgen_latency_svg(loadgen_samples, move_events)

        print(f"Results saved to {self.session_dir}", flush=True)

    def parse_loadgen_log(self, log_path: Path) -> List[dict]:
        results = []
        for line in log_path.read_text().splitlines():
            if "status=" not in line:
                continue
            timestamp, _, rest = line.partition(" ")
            match = LOADGEN_PATTERN.search(rest)
            if not match:
                continue
            results.append(
                {
                    "timestamp": timestamp,
                    "status": int(match.group("status")),
                    "latency_ms": float(match.group("latency")),
                }
            )
        return results

    def parse_controller_log(self, log_path: Path) -> List[dict]:
        events = []
        for line in log_path.read_text().splitlines():
            match = MOVE_PATTERN.search(line)
            if not match:
                continue
            timestamp = line.split(" ", 1)[0]
            events.append(
                {
                    "timestamp": timestamp,
                    "src": match.group("src"),
                    "dst": match.group("dst"),
                    "node": match.group("node"),
                }
            )
        return events

    def write_loadgen_csv(self, samples: List[dict]):
        with (self.session_dir / "G_19_loadgen_metrics.csv").open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "status", "latency_ms"])
            for item in samples:
                writer.writerow([item["timestamp"], item["status"], item["latency_ms"]])

    def write_move_csv(self, events: List[dict]):
        with (self.session_dir / "G_19_move_events.csv").open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "src", "dst", "node"])
            for item in events:
                writer.writerow([item["timestamp"], item["src"], item["dst"], item["node"]])

    def build_summary(self, loadgen_samples: List[dict], move_events: List[dict]) -> dict:
        summary = {
            "started_at": self.metadata["started_at"],
            "finished_at": self.metadata["finished_at"],
            "samples": self.samples,
            "move_count": len(move_events),
            "moves": move_events,
            "comparison_available": False,
        }

        move_time = None
        if move_events:
            move_time = parse_timestamp(move_events[0]["timestamp"])

        if loadgen_samples:
            summary["loadgen"] = {
                "total_requests": len(loadgen_samples),
                "success_rate_percent": round(
                    sum(1 for item in loadgen_samples if item["status"] < 500)
                    / len(loadgen_samples)
                    * 100,
                    2,
                ),
            }

        if loadgen_samples and move_time:
            before = [
                item["latency_ms"]
                for item in loadgen_samples
                if (parse_timestamp(item["timestamp"]) or move_time) < move_time
                and item["status"] < 500
            ]
            after = [
                item["latency_ms"]
                for item in loadgen_samples
                if (parse_timestamp(item["timestamp"]) or move_time) >= move_time
                and item["status"] < 500
            ]
            if before and after:
                summary["comparison_available"] = True
                summary["comparison_anchor"] = move_events[0]
                summary["comparison_note"] = "Before/after windows are split at the first controller move event."
                summary["loadgen"]["before"] = {
                    "avg_latency_ms": round(sum(before) / len(before), 2),
                    "p95_latency_ms": round(percentile(before, 95), 2),
                }
                summary["loadgen"]["after"] = {
                    "avg_latency_ms": round(sum(after) / len(after), 2),
                    "p95_latency_ms": round(percentile(after, 95), 2),
                }
            else:
                summary["loadgen"]["note"] = "A move happened, but there were not enough pre-move and post-move loadgen samples."
        elif loadgen_samples:
            summary["loadgen"]["note"] = "No controller move event was captured, so no before/after latency comparison was generated."

        edge_comparison = []
        if move_time:
            for key, samples in self.edge_samples.items():
                if not samples:
                    continue
                before_samples = [
                    sample
                    for sample in samples
                    if (parse_timestamp(sample["timestamp"]) or move_time) < move_time
                ]
                after_samples = [
                    sample
                    for sample in samples
                    if (parse_timestamp(sample["timestamp"]) or move_time) >= move_time
                ]
                if not before_samples or not after_samples:
                    continue
                first = before_samples[-1]
                last = after_samples[-1]
                edge_comparison.append(
                    {
                        "edge": key,
                        "before_p95_ms": round(first["p95_ms"], 3),
                        "after_p95_ms": round(last["p95_ms"], 3),
                        "before_rps": round(first["rps"], 6),
                        "after_rps": round(last["rps"], 6),
                        "before_benefit": round(first["benefit"], 3),
                        "after_benefit": round(last["benefit"], 3),
                    }
                )

        edge_comparison.sort(key=lambda item: item["after_benefit"], reverse=True)
        summary["edge_comparison"] = edge_comparison[:5]
        if not move_time:
            summary["edge_note"] = "No controller move event was captured, so edge before/after comparison was skipped."
        elif not summary["edge_comparison"]:
            summary["edge_note"] = "A move happened, but there were not enough pre-move and post-move edge samples."
        return summary

    def write_edge_comparison_svg(self, items: List[dict]):
        if not items:
            return
        width = 900
        height = 420
        margin_left = 70
        margin_bottom = 110
        margin_top = 30
        chart_width = width - margin_left - 30
        chart_height = height - margin_top - margin_bottom
        max_value = max(max(item["before_p95_ms"], item["after_p95_ms"]) for item in items) or 1
        slot_width = chart_width / max(len(items), 1)
        bar_width = max(12, slot_width * 0.28)

        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
            '<style>text{font-family:Arial,sans-serif;font-size:12px} .label{fill:#333} .axis{stroke:#444;stroke-width:1} .before{fill:#ef4444} .after{fill:#10b981}</style>',
            f'<text x="{width/2}" y="18" text-anchor="middle">Service Pair P95 Latency Before vs After</text>',
            f'<line class="axis" x1="{margin_left}" y1="{height-margin_bottom}" x2="{width-20}" y2="{height-margin_bottom}"/>',
            f'<line class="axis" x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height-margin_bottom}"/>',
        ]

        for index, item in enumerate(items):
            x_center = margin_left + slot_width * index + slot_width / 2
            before_height = (item["before_p95_ms"] / max_value) * chart_height
            after_height = (item["after_p95_ms"] / max_value) * chart_height
            before_x = x_center - bar_width - 4
            after_x = x_center + 4
            base_y = height - margin_bottom
            parts.append(
                f'<rect class="before" x="{before_x:.1f}" y="{base_y-before_height:.1f}" width="{bar_width:.1f}" height="{before_height:.1f}"/>'
            )
            parts.append(
                f'<rect class="after" x="{after_x:.1f}" y="{base_y-after_height:.1f}" width="{bar_width:.1f}" height="{after_height:.1f}"/>'
            )
            parts.append(
                f'<text class="label" transform="translate({x_center:.1f},{height-margin_bottom+18}) rotate(30)" text-anchor="start">{item["edge"]}</text>'
            )

        parts.extend(
            [
                f'<rect class="before" x="{width-220}" y="40" width="14" height="14"/>',
                f'<text x="{width-200}" y="52">Before</text>',
                f'<rect class="after" x="{width-130}" y="40" width="14" height="14"/>',
                f'<text x="{width-110}" y="52">After</text>',
                "</svg>",
            ]
        )
        (self.plots_dir / "G_19_edge_p95_comparison.svg").write_text("".join(parts))

    def write_loadgen_latency_svg(self, samples: List[dict], move_events: List[dict]):
        if not samples:
            return
        width = 900
        height = 420
        margin_left = 60
        margin_bottom = 45
        margin_top = 30
        chart_width = width - margin_left - 20
        chart_height = height - margin_top - margin_bottom
        max_latency = max(item["latency_ms"] for item in samples) or 1
        points = []
        for index, item in enumerate(samples):
            x = margin_left + (index / max(len(samples) - 1, 1)) * chart_width
            y = margin_top + chart_height - (item["latency_ms"] / max_latency) * chart_height
            points.append(f"{x:.1f},{y:.1f}")

        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
            '<style>text{font-family:Arial,sans-serif;font-size:12px} .axis{stroke:#444;stroke-width:1} .line{fill:none;stroke:#2563eb;stroke-width:2} .move{stroke:#f59e0b;stroke-width:1.5;stroke-dasharray:6 4}</style>',
            f'<text x="{width/2}" y="18" text-anchor="middle">Load Generator End-to-End Latency</text>',
            f'<line class="axis" x1="{margin_left}" y1="{height-margin_bottom}" x2="{width-20}" y2="{height-margin_bottom}"/>',
            f'<line class="axis" x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height-margin_bottom}"/>',
            f'<polyline class="line" points="{" ".join(points)}"/>',
        ]

        move_indexes = []
        sample_times = [item["timestamp"] for item in samples]
        for event in move_events:
            for index, sample_time in enumerate(sample_times):
                if sample_time >= event["timestamp"]:
                    move_indexes.append((index, event))
                    break

        for index, event in move_indexes:
            x = margin_left + (index / max(len(samples) - 1, 1)) * chart_width
            parts.append(
                f'<line class="move" x1="{x:.1f}" y1="{margin_top}" x2="{x:.1f}" y2="{height-margin_bottom}"/>'
            )
            parts.append(
                f'<text x="{x+4:.1f}" y="{margin_top+14}" fill="#b45309">{event["src"]} moved</text>'
            )

        parts.append("</svg>")
        (self.plots_dir / "G_19_loadgen_latency.svg").write_text("".join(parts))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect experiment results for the network-aware demo.")
    parser.add_argument("--namespace", default="network-aware")
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:19090")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--session-name", default="")
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--query-window", default="2m")
    return parser.parse_args()


def main():
    args = parse_args()
    collector = ExperimentCollector(args)
    print(f"Saving experiment data to {collector.session_dir}", flush=True)
    print("Press Ctrl+C to stop collection and finalize results.", flush=True)

    try:
        while True:
            collector.sample()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopping collection and writing final outputs...", flush=True)
    finally:
        previous_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            collector.finalize()
        finally:
            signal.signal(signal.SIGINT, previous_handler)


if __name__ == "__main__":
    main()
