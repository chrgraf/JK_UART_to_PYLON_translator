# JK_UART_to_PYLON_translator
reads JK BMS info via UART and transmits the data via CAN-BUS emulating Pylontech protocol


Dear all,

project is in an very early stage.
Overall purpose is self-built solar-batterie, using JK-BMS. Older JK-BMS do not support can-bus. This project is aimed to close the gap, by reading battery-stats via UART from JK-BMS and then translating to CAN-BUS using Pylontech Protocol.

Initial tests shows it working. Use at own risk. The author is not taking any responsibility for any damage or issue resulting by making use of this project.

Full credits go to:
1) Juamiso, who developed the CAN-BUS Part
https://github.com/juamiso/PYLON_EMU

2) PurpleAlien, who developed the JK-UART script
https://github.com/PurpleAlien/jk-bms_grafana

Tested
=======
RPI2 with wavshare can-hat and usb-serial converter


Install
========
I will add much mire info over time.
But its a good idea to clone https://github.com/juamiso/PYLON_EMU to get hold of the required pylon_CAN_210124.dbc file.
After having all python libs installed, just execute the script delivered vua this repo


cabling
========
todo

thanks


 
