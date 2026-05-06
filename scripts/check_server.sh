#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

echo "Checking GET /health"
curl -fsS "$BASE_URL/health"
echo

echo "Checking GET /alerts/recent"
curl -fsS "$BASE_URL/alerts/recent"
echo

echo "Checking POST /jobs/collect-once"
curl -fsS -X POST "$BASE_URL/jobs/collect-once"
echo

echo "Server checks completed"
