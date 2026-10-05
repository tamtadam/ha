#!/bin/bash
"${PYTHON_BIN:-python3}" ~/PROD/ha/scripts/rpi.py --send_config >> ~/PROD/ha/scripts/log_rpi.txt 2>&1
