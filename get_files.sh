#!/bin/bash

files=(alien_master.service basic_ringbuf.py README.md requirements.txt jk_pylon.service jk_pylon_can.py pylon_CAN_210124.dbc)

for i in "${files[@]}"
  do scp behn@192.168.178.144:jk_pylon/$i .
done


