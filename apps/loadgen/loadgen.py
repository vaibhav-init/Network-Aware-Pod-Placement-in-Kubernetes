import os
import time
from urllib import error, request


TARGET_URL = os.getenv("TARGET_URL", "http://gateway:8000/request")
INTERVAL_SEC = float(os.getenv("INTERVAL_SEC", "0.5"))
TIMEOUT_SEC = float(os.getenv("TIMEOUT_SEC", "2.0"))


def main():
    print(f"loadgen targeting {TARGET_URL}", flush=True)
    while True:
        started = time.time()
        try:
            with request.urlopen(TARGET_URL, timeout=TIMEOUT_SEC) as response:
                response.read()
                latency_ms = round((time.time() - started) * 1000, 2)
                print(f"status={response.status} latency_ms={latency_ms}", flush=True)
        except error.HTTPError as exc:
            latency_ms = round((time.time() - started) * 1000, 2)
            print(f"status={exc.code} latency_ms={latency_ms} error={exc}", flush=True)
        except Exception as exc:
            latency_ms = round((time.time() - started) * 1000, 2)
            print(f"status=503 latency_ms={latency_ms} error={exc}", flush=True)

        time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
