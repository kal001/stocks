#!/usr/bin/env bash
kill $(ps aux | grep '[s]tock_telegrambot.py' | awk '{print $2}')
cd /home/fernando/bolsa
python stock_telegrambot.py &
