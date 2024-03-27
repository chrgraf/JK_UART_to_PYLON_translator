#!/bin/bash
ip="192.168.178.181"
dir="jk_venv"

#files=(sems.py my_mqtt.py alien_master.service basic_ringbuf.py README.md requirements.txt jk_pylon.service jk_pylon_can.py pylon_CAN_210124.dbc)
files=(jk_pylon.service README.md pylon_CAN_210124.dbc)

for i in "${files[@]}"
  do scp behn@$ip:${dir}/$i .
done

scp behn@${ip}:${dir}/*py .


