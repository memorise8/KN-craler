#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
exec python3 run.py --host 0.0.0.0 --reload "$@"
