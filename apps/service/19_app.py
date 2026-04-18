import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error, request

# env vars to Docker image serve as gateway, auth, user, db, or logger
SERVICE_NAME = os.getenv("SERVICE_NAME", "service")
PORT = int(os.getenv("PORT", "8000"))
# comma-separated list of "name=url" pairs
UPSTREAMS = [item.strip() for item in os.getenv("UPSTREAMS", "").split(",") if item.strip()]
# processing time to make latency differences visible
PROCESSING_DELAY_MS = int(os.getenv("PROCESSING_DELAY_MS", "0"))
REQUEST_TIMEOUT_SEC = float(os.getenv("REQUEST_TIMEOUT_SEC", "2.0"))


def call_upstream(target: str) -> dict:
    name, url = target.split("=", 1)
    started = time.time()
    try:
        with request.urlopen(url, timeout=REQUEST_TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8")
            latency_ms = round((time.time() - started) * 1000, 2)
            return {
                "name": name,
                "url": url,
                "status": response.status,
                "latency_ms": latency_ms,
                # truncate response body to keep response small
                "body": body[:200],
            }
    except error.HTTPError as exc:
        return {
            "name": name,
            "url": url,
            "status": exc.code,
            "latency_ms": round((time.time() - started) * 1000, 2),
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "name": name,
            "url": url,
            "status": 503,
            "latency_ms": round((time.time() - started) * 1000, 2),
            "error": str(exc),
        }


class Handler(BaseHTTPRequestHandler):
    # suppress default access logs to keep pod logs clean
    def log_message(self, format_str, *args):
        return

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # readiness and liveness probes to check if the pod is healthy
        if self.path in ("/healthz", "/readyz"):
            self._json(200, {"service": SERVICE_NAME, "status": "ok"})
            return

        # simulate real work before calling upstreams
        if PROCESSING_DELAY_MS > 0:
            time.sleep(PROCESSING_DELAY_MS / 1000.0)

        # call upstream services and collect their responses
        upstream_results = [call_upstream(item) for item in UPSTREAMS]
        # if upstream return 5xx, propagate failure
        status = 200 if all(item.get("status", 500) < 500 for item in upstream_results) else 503

        self._json(
            status,
            {
                "service": SERVICE_NAME,
                "path": self.path,
                "upstreams": upstream_results,
                "timestamp": time.time(),
            },
        )


if __name__ == "__main__":
    server = ThreadingHTTPServer(("", PORT), Handler)
    print(f"{SERVICE_NAME} listening on :{PORT}", flush=True)
    server.serve_forever()
