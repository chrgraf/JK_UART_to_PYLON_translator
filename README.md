# JK_UART_to_PYLON_translator

Short Summary:
reads JK_BMS via UART and transmits the data via CAN-BUS emulating Pylontech protocol
Inverter sees Volt, Current, SOC and Temp.
Script  has trivial control-loop to control actual current for charging and discharging. e.g. if the highest cell goes beyond 3.5V max-charge current gets lowered, resulting that the inverter loweres the charging power.
Same holds true for the weakest cell. Depending on weakest cell voltage, allowed current-draw gets limited and finally adjusted to zero t protect the lowest cell against over-discharge.


Dear all,

project is in an very early stage.
Overall purpose is self-built solar-batterie, using JK-BMS. Older JK-BMS do not support can-bus. This project is aimed to close the gap, by reading battery-stats via UART from JK-BMS and then translating to CAN-BUS using Pylontech Protocol.
General speaking this script is massively using below repos from PurpleAlien and Juamiso, combines them into a single script and adds some more control-loop capabilities.

# Disclaimer
Initial tests shows it working. Use at own risk. The author is not taking any responsibility for any damage or issue resulting by making use of this project.

# credits
Full credits go to:
1) Juamiso, who developed the CAN-BUS Part
https://github.com/juamiso/PYLON_EMU

2) PurpleAlien, who developed the JK-UART script
https://github.com/PurpleAlien/jk-bms_grafana

Tested
=======
RPI2          : with wavshare can-hat and usb-serial converter
JK BMS        : JK Smart Active Balance BMS BD6A20S10P
Solis inverter: RAI-3K-48ES-5G



Install
========
I will add more info over time.
But its a good idea to clone https://github.com/juamiso/PYLON_EMU to get hold of the required pylon_CAN_210124.dbc file.
After having all python libs installed, just execute the script delivered via this repo

## making the script autostart as a service
If the script stops, that the inverter does not have a valid can-bus coomunication and hence all charging/discharging is stopped by the inverter. Making the script a service, even reloads the scripts in case e.g. it was killed.. 

some good reading: https://medium.com/@benmorel/creating-a-linux-service-with-systemd-611b5c8b91d6

### systemd script
```bash
behn@rpi2:~ $ cat /etc/systemd/system/alien_master.service
[Unit]
Description=Launching alien_master JK_pylon converter
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=1
User=xxx                                                     # change name according to your account used on your own RPI
ExecStart=/home/behn/PYLON_EMU-master/alien_master1.py       # change path accordingly to match your setup

[Install]
WantedBy=multi-user.target
```

### autostarting and enabling the systemd script
Once added the script execute:
```bash
$ systemctl start alien_master
```

And automatically get it to start on boot:
```bash
$ systemctl enable alien_master
```



cabling
========
Please find the connection towards JK-BMS via UART <> RPI2 via USB serial device. Make sure the USB-serial converter allows to Jumper for 3.3V!
<img width="1002" alt="image" src="https://github.com/chrgraf/JK_UART_to_PYLON_translator/assets/22005482/335aa90b-a8b1-40e6-a976-aeb044a0daa1">



Features
=========
Reads Batt_voltage, current, SOC, temperature from the JK_BMS and sends it to the Inverter with Pylon Protocol.
The original script was translating the derived Current incorrectly. This is now corrected and now correct current gets reported.
A very much simple charge-control loop got added. e.g. if either  the cell with highest voltage or the cell with lowest voltage is crossing a treshhold, the script controls the inverter to modify charge or drawn current:

Battery_charge_current_limit_default

  # min_volt set the limit
  if (min_volt>=3.3):
     Battery_discharge_current_limit = 60
  elif (min_volt>=3.1):
     Battery_discharge_current_limit = 50
  elif (min_volt>=3.0):
     Battery_discharge_current_limit = 30
  elif (min_volt>=2.9):
     Battery_discharge_current_limit = 10
  elif (min_volt<2.9):
     Battery_discharge_current_limit = 0
  else:
     Battery_discharge_current_limit = Battery_discharge_current_limit_default
 

  if (not oscillation):
    # max_volt the limit
    if (max_volt>=3.55):
       Battery_charge_current_limit = 0
    elif (max_volt>=3.50):
       Battery_charge_current_limit = 2
    elif (max_volt>=3.47):
       Battery_charge_current_limit = 15
    elif (max_volt>=3.45):
       Battery_charge_current_limit = 30
    elif (max_volt>=3.0):
       Battery_charge_current_limit = 60
    elif (max_volt>=2.7):
       Battery_charge_current_limit = 30

Another item I am looking into is related to mine solis-inverter. Sometimes its control-loop fails to adjust reasonable amount to charge battery, resulting in either charging thsat high that in addition to excesssolar-power, power from grid id taken.
This oscialltion-counteract routine is in a very early stage though..


thanks


 
