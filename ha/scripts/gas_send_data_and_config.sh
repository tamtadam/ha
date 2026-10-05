#!/bin/bash
"${PYTHON_BIN:-python3}" ~/PROD/ha/scripts/gas.py --send_config --send_data >> ~/PROD/ha/scripts/log_gas.txt 2>&1
