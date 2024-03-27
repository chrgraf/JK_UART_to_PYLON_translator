# JK_UART_to_PYLON_translator

Short Summary:
reads JK_BMS via UART and transmits the data via CAN-BUS emulating Pylontech protocol to a Solis battery Storage inverter
Inverter sees Volt, Current, SOC and Temp.
Script  has trivial control-loop to control actual current for charging and discharging. e.g. if the highest cell goes beyond 3.5V max-charge current gets lowered, resulting that the inverter loweres the charging power.
Same holds true for the weakest cell. Depending on weakest cell voltage, allowed current-draw gets limited and finally adjusted to zero t protect the lowest cell against over-discharge.

# longer story
- Most Important
    - reading JK-BMS via serial UART
	- pushing JK-BMS-data via CANBUS "Pylon" Protocol to a Solis Inverter
- sending some stuff to a MQTT-Broker
- reads a Goodwe-Inverter via HTTP/Sems-Portal
    - will be chnaged against direct IP-connection over next time
- reads directly SMA energy-meter via IP-Socket from the network
- BMS-Features 
    - reduces Charging-Power to 0 Ampere of max-cell voltage >3.5V
	- reduces Discharging-Power to 0 Ampaere if min-cell volatge drops below 3.0V
- counteracts if both inverters work against each other
    - if Goodwe charges battery, then Solis is prohibited to discharge
	- if Goodwe discharge battery, then Solis is prohibited to charge
- making good use of multiprocessing-library
- both inverters tend to produce oscialltion. ongoing work to control this via enforcing malually charge/discharge-limts on Solis	
	

# major updates
* March 2024
    - added MQTT send/receive
	- counteracting if mqtt-broker is not available on startup
	- added to read SMA entergy-meter to read via socket
* Goodwe added
    * mine very unusual setup inclides a Goodwe EM3648 as well. As I need to avoid that e.g. Goodwe discharges to allow the Solis to charge, I added major control-loops.
    * Important on the Goodwe: Goodwe can be removed from the picture by setting the variable  Sems_Flag = False
    * actyally reading the goodwe via HPPS from Sems-Portal. Not ideal. Further work done to read directly via TCP
- added a python-script to candump all messages in human readable format (can_debug.py)
  

Dear all,

project is in an very early stage.
Overall purpose is self-built solar-batterie, using JK-BMS. Older JK-BMS do not support can-bus. This project is aimed to close the gap, by reading battery-stats via UART from JK-BMS and then translating to CAN-BUS using Pylontech Protocol.
General speaking this script is massively using below repos from PurpleAlien and Juamiso, combines them into a single script and adds some more control-loop capabilities.

# Disclaimer
Initial tests shows it working. Use at own risk. The author is not taking any responsibility for any damage or issue resulting by making use of this project.
I am still elaborating if RPI2 is good enough to get the job done. Actually working on a RPI5 which for sure is very much overpowered.

# credits
credits go to:

* Juamiso, who developed the CAN-BUS Part
    * https://github.com/juamiso/PYLON_EMU
* PurpleAlien, who developed the JK-UART script
    * https://github.com/PurpleAlien/jk-bms_grafana
* Prasath Premapalan for the can-decoding script
    * https://stackoverflow.com/users/12183162/prasath-premapalan
    * https://stackoverflow.com/questions/58306438/how-to-decode-message-from-a-canbus-iptronik
* by Wenger Florian wenger@unifox.at for the SMA-energy-meter


Tested
=======
Initially I tried ti get it runnign with a RPI2. To sloppy and instable.
Actually running on a RPI5, which is overpowered. S othe truth seems in the middle...
```
RPI5          : with wavshare can-hat and usb-serial converter
can-HW        : https://www.waveshare.com/wiki/2-CH_CAN_HAT#CAN_bus:wake
JK BMS        : JK Smart Active Balance BMS BD6A20S10P
Solis inverter: RAI-3K-48ES-5G
```

# testing Basic function blocks first
As the project does include now many different aspects, its easu to break it...
Intention of below verification-steps is to test each function standalone! Shall massively help in identifying if something is non-functional

## Goodwe
- Mine setup includes both a solis and a goodwe. I need to avoid that Solis e.g. discharges to allow the goodwe charging.
- actually Goodwe gets queried via HTTP Sems-Port. Suboptimal.
- Test Sems-Portal via: sems.py script.
- details at https://github.com/chrgraf/Goodwe_Sems_Portal_Python_Query

- Note: of course the goodwe part can be fully disabled, as the purpose of this repo is Solis/JK-BMS/Pylon

```
behn@rpi5:~/jk_venv $ ./sems.py
Success
```

## checking SMA-energy Meter reading
You need to make sure to edit the correct serial-number for your enery-meter

```
behn@rpi5:~/jk_venv $ grep serial sma_em_capture_package.py
   smaemserials=1900203015

behn@rpi5:~/jk_venv $ python sma_em_capture_package.py
Bezug von Grid: -10.0 W
```


## checking UART-connection to JK-BMS
One major comoponent is to read via Serial UART from the BMS. In mine setup the serial adapaper is attached via ttyUSB0.
Change as required in the my_read_bms.py script:
```
behn@rpi5:~/jk_venv $ grep USB0 my_read_bms.py
      bms = serial.Serial('/dev/ttyUSB0')
```
Executing the script shall result in "True"
```
behn@rpi5:~/jk_venv $ python my_read_bms.py
query the BMS
USB Serial Adpater Setting:  Serial<id=0x7fff528fe3e0, open=True>(port='/dev/ttyUSB0', baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=0.2, xonxoff=False, rtscts=False, dsrdtr=False)
Status reading the BMS:  True
return values: [56, 52.28, -12.2, 23.0, 3.266, 3.27, -12.2, True]

```

## canbus
If canbus all does fine, then the canbus dump-tool shall print something like this here

```
behn@rpi5:~/jk_venv $ ./can_debug.py
[message('Network_alive_msg', 0x305, False, 8, None), message('Battery_Manufacturer', 0x35e, False, 8, None), message('Battery_Request', 0x35c, False, 2, {None: 'Bit 5 is designed for inverter allows battery to shut down, and able to wake battery up to charge it.Bit 4 is designed for inverter doesn`t want battery to shut down, able to charge battery before shut down to avoid low energy.'}), message('Battery_actual_values_UIt', 0x356, False, 6, None), message('Battery_SoC_SoH', 0x355, False, 4, None), message('Battery_limits', 0x351, False, 8, None), message('Battery_Error_Warnings', 0x359, False, 7, None)]
{'Alive_packet': 0}
{'SoC': 56, 'SoH': 100}
{'Manufaturer_string': 336337852752}
{'Full_charge_req': 0, 'Force_charge_req_II': 0, 'Force_charge_req_I': 0, 'Discharge_enable': 1, 'Charge_enable': 1}
{'Battery_voltage': 52.24, 'Battery_current': -14.8, 'Battery_temperature': 23.0}
{'Battery_charge_voltage': 56.0, 'Battery_charge_current_limit': 0.0, 'Battery_discharge_current_limit': 60.0, 'Battery_discharge_voltage': 51.0}
{'Overvoltage_ERR': 0, 'Undervoltage_ERR': 0, 'Overtemperature_ERR': 0, 'Undertemperature_ERR': 0, 'Overcurrent_discharge_ERR': 0, 'Charge_overcurrent_ERR': 0, 'System_Error': 0, 'voltage_high_WARN': 0, 'voltage_low_WARN': 0, 'Temperature_high_WARN': 0, 'Temperature_low_WARN': 0, 'Discharge_current_high_WARN': 0, 'Charge_current_high_WARN': 0, 'Internal_Error_WARN': 0, 'Module_numbers': 16}
{'Alive_packet': 0}
```

# Install

I will add more info over time.
But its a good idea to clone https://github.com/juamiso/PYLON_EMU to get hold of the required pylon_CAN_210124.dbc file.
After having all python libs installed, just execute the script delivered via this repo

```
behn@rpi5:~/jk_venv $ ./jk_pylon_can.py
Logging to file: /mnt/ramdisk/jk_pylon.log
logging to console is disabled
 -enable logging to console  by setting variable log_to_console=True
Connected to MQTT Broker!
```

## python serial library
I gave up on trying to use venv and pip-install serial.
Whenever I used venv or serial-lib via pip-install, the UART to JK-BMS failed

I solved it by making sure to install serial-library via: 
```
sudo apt-get install python3-serial
Note: For me, trying to use pip install serial resulted in UART to BMS failing!

```
## making the script autostart as a service
If the script stops, that the inverter does not have a valid can-bus coomunication and hence all charging/discharging is stopped by the inverter. Making the script a service, even reloads the scripts in case e.g. it was killed.. 

some good reading: https://medium.com/@benmorel/creating-a-linux-service-with-systemd-611b5c8b91d6


### systemd script
make sure to adopt your user-id in below script!

```bash
behn@rpi5:~/jk_venv $ cat /etc/systemd/system/jk_pylon.service

# copy this file into /etc/systemd/system
# replace all occurences of /home/behn/jk_pylon with your venv dir
# make the service starting after reboot: systemctl enable jk_pylon
# show status: systemctl show jk_pylon
# stop it: systemctl stop jk_pylon
# if you change this script, reload systemctl: systemctl daemon-reload



[Unit]
Description=Launching JK_pylon converter
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=1
User=<>                                                       # <<<< enter your user-idf here!
WorkingDirectory=/home/behn//jk_venv
PermissionsStartOnly=true
#Environment=PYTHONPATH=/home/behn/jk_pylon_venv
#ExecStartPre=+/bin/bash -c 'ip link set can0 up type can bitrate 500000'
ExecStartPre=-/usr/sbin/ip link set can0 up type can bitrate 500000
ExecStart=/home/behn/jk_venv/jk_pylon_can.py

[Install]
WantedBy=multi-user.target
```


### autostarting and enabling the systemd script
Once added the script execute:
```bash
$ systemctl start jk_pylon
```

And automatically get it to start on boot:
```bash
$ systemctl enable jk_pylon
```

stopping the script
```bash
$ systemctl stop jk_pylon
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


# BELOW IS NOT WORKING
# trying to use VENV with systemd fails to open the ttyUSB port
 
## running the script in python venv
I am using numpy lib in mine script, which does not have a native ubuntu repo. I decided to go via python venv to run the script.

### preparing python venv
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip -y
sudo apt install build-essential libssl-dev libffi-dev python3-dev
sudo apt install python3-venv -y
```

as a next create the venv
This creates a directory jk_pylon
```bash
python -m venv jk_pylon_venv
```

This article says itsa bad idea to put your project-files into same directory which holds your venv. So lets keep the venv-directory jk_pylon_venv and the project-dir jk_pylon seperated.

now copy all required files into this directory
```bash
cp alien_master1.py pylon_CAN_210124.dbc requirements.txt ./jk_pylon/
```

# activating the venv
prompt shall look like this after executing the activate : (jk_pylon)..:~/jk_pylon $
```bash
$ source jk_pylon_venv/bin/activate
```

# install all dependencis
```bash
(jk_pylon_venv) behn@rpi2:~ $ pwd
/home/behn
(jk_pylon_venv) behn@rpi2:~ $ pip3 install -r ./jk_pylon/requirements.txt
```

# finally run the script
above source "source jk_pylon_venv/bin/activate" should have chnaged your prompt, indicating (jk_pylon_venv)

```bash
# change into the projct directory, required to find the pylon_CAN_210124.dbc file
(jk_pylon_venv) behn@rpi2:~ $ cd jk_pylon
# launch the script
(jk_pylon_venv) behn@rpi2:~/jk_pylon $ ./jk_pylon_can.py
Carrying out cyclic tests with socketcan interface
Starting to send a message every 1s
cellcount= 16
[]
```

## systemd script  - not this fails to open the ttyUSB, so do not use..

```bash
root@rpi2:/etc/systemd/system# cat jk_pylon.service
# copy this file into /etc/systemd/system
# replace all occurences of /home/behn/jk_pylon with your venv dir
# make the service starting after reboot: systemctl enable jk_pylon
# show status: systemctl show jk_pylon
# stop it: systemctl stop jk_pylon
# id you chnage this scrip[t, reload systemctl: systemctl daemon-reload



[Unit]
Description=Launching JK_pylon converter
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=1
#User=root
User=behn
Group=dialout
WorkingDirectory=/home/behn/jk_pylon
#ExecStart=/home/behn/jk_pylon_venv/bin/python jk_pylon_can.py
ExecStart=/home/behn/jk_pylon_venv/bin/python -m jk_pylon_can
StandardOutput=tty
TTYPath=/dev/pts/1

[Install]
WantedBy=multi-user.target
```

