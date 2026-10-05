#!/bin/bash
"${PYTHON_BIN:-python3}" ~/PROD/ha/scripts/rpi.py --send_data >> ~/PROD/ha/scripts/log_rpi.txt 2>&1
