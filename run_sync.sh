#!/bin/bash
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

/usr/bin/python3 daily_stock_update.py --live --api >> cron.log 2>&1
