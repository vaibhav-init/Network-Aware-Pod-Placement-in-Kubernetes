#!/bin/bash
set -euo pipefail

kubectl -n network-aware scale deploy/network-rescheduler --replicas=0
