#!/bin/bash
python ~/PROD/ha/scripts/rpi.py --send_config --send_data >> ~/PROD/ha/scripts/log_rpi.txt 2>&1
