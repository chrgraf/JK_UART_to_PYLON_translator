#!/usr/bin/python3
###############################################################################################
# Purpose: read JK-BMS via UART and send info via can-bus using Pylontech Protocol
##########
#Full credits go to:
#1) Juamiso, who developed the CAN-BUS Part
#https://github.com/juamiso/PYLON_EMU

#2) PurpleAlien, who developed the JK-UART script
#https://github.com/PurpleAlien/jk-bms_grafana

# Disclaimer
############
# The author is not taking any responsibility for any damage or issue resulting by making use of this project.
# Use at own risk


# platform tested: RPI2 with wavshare canhat
###############################################################################################

# canbus
from __future__ import print_function
import cantools
import time
from binascii import hexlify
import can

can_db="./pylon_CAN_210124.dbc"
#can_db="/home/behn/jk_pylon/pylon_CAN_210124.dbc"

# JK-stuff
import time
import sys, os, io
import struct
import serial

# other imports
import os.path

#mqtt - for logging-purposes we send some stuff to a mqtt-broker.
# not required to operate this script successful
import my_mqtt
last_mqtt_run=0

# self written ringbuffer
from basic_ringbuf import myRingBuffer 
current_max_size=20                      # elements in ringbuffer
current_ringbuffer=myRingBuffer(current_max_size)

# logfile
write_to_file = True               # turn only on for debug. no upper size limit of the logfile!
#filename="./jk_python_can.log"
filename="/mnt/ramdisk/jk_pylon.log"


sleepTime = 10



def byteArrayToHEX(byte_array):
    hex_string = ""
    for cmd_byte in byte_array:
        hex_byte = ("{0:02x}".format(cmd_byte))
        hex_string += hex_byte + " " 

    return hex_string


def control_loop (min_volt, max_volt, current,actual_time):
  global current_ringbuffer, current_max_size, mqtt_client, last_mqtt_run
  current_max_deviation_0=6                      # ampere it can overshoot without triggering the control-loop0
  current_max_deviation_1=12                     # ampere it can overshoot without triggering the control-loop0
  Battery_discharge_current_limit_default= 60
  Battery_charge_current_limit_default   = 60
  Battery_charge_voltage_default         = 56
  Battery_discharge_voltage_default      = 51
  oscillation=False
  
  current_ringbuffer.append(current)
  print ("current_ringbuffer", current_ringbuffer.get())
  current_max=current_ringbuffer.max()
  current_min=current_ringbuffer.min()
  if (current_max >= current_max_deviation_1  and current_min < -current_max_deviation_1):
      Battery_charge_current_limit=current_max_deviation_1
      oscillation=True
  elif (current_max >= current_max_deviation_0  and current_min < -current_max_deviation_0):
      Battery_charge_current_limit=current_max_deviation_0
      oscillation=True
  else:
      Battery_charge_current_limit=Battery_charge_current_limit_default
  if (write_to_file):
         print ("oscillation state              : ", oscillation,file=my_file)

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
    else:
       Battery_charge_current_limit = Battery_charge_current_limit_default
  
  print ("actual_time",actual_time)
  print ("last_last_run",last_mqtt_run)
  if (actual_time - 60 > last_mqtt_run ) :
      print (">>>>>>>>>>>>>>>>>>>>>>")
      last_mqtt_run=actual_time
      topic="jk_pylon/Battery_charge_current_limit"
      message=Battery_charge_current_limit
      my_mqtt.publish(mqtt_client,topic,message)      
    
      topic="jk_pylon/Battery_discharge_current_limit"
      message=str(Battery_discharge_current_limit)
      my_mqtt.publish(mqtt_client,topic,message)      
    
  print ("Battery_charge_current_limit   : ", Battery_charge_current_limit)
  print ("Battery_discharge_current_limit: ", Battery_discharge_current_limit)
  if (write_to_file):
    print ("min_volt, max_volt             : ", min_volt, max_volt,file=my_file)
    print ("Battery_charge_current_limit   : ", Battery_charge_current_limit,file=my_file)
    print ("Battery_discharge_current_limit: ", Battery_discharge_current_limit,file=my_file)
    #my_file.write (">h ")
    # my_file.flush()    # flush is done once in the main
  
  msg_data_Battery_limits = {
     'Battery_discharge_current_limit' : Battery_discharge_current_limit,
     'Battery_charge_current_limit' : Battery_charge_current_limit,
     'Battery_charge_voltage' : Battery_charge_voltage_default,
     'Battery_discharge_voltage' : Battery_discharge_voltage_default }

  Battery_limits = db.get_message_by_name('Battery_limits')
  msg_data_enc_Battery_limits = db.encode_message('Battery_limits', msg_data_Battery_limits)
  msg_tx_Battery_limits = can.Message(arbitration_id=Battery_limits.frame_id, data=msg_data_enc_Battery_limits, is_extended_id=False)
  task_tx_Battery_limits = bus.send_periodic(msg_tx_Battery_limits, 1)




try:
    bms = serial.Serial('/dev/ttyUSB0')
    bms.baudrate = 115200
    bms.timeout  = 0.2
except:
    print("BMS not found.")

# The hex string composing the command, including CRC check etc.
# See also: 
# - https://github.com/syssi/esphome-jk-bms
# - https://github.com/NEEY-electronic/JK/tree/JK-BMS
# - https://github.com/Louisvdw/dbus-serialbattery

def sendBMSCommand(cmd_string):
    cmd_bytes = bytearray.fromhex(cmd_string)
    for cmd_byte in cmd_bytes:
        hex_byte = ("{0:02x}".format(cmd_byte))
        bms.write(bytearray.fromhex(hex_byte))
    return

# This could be much better, but it works.
def readBMS(actual_time):
    global my_file 
    try: 
        # Read all command
        sendBMSCommand('4E 57 00 13 00 00 00 00 06 03 00 00 00 00 00 00 68 00 00 01 29')
    
        time.sleep(.1)

        if bms.inWaiting() >= 4 :
            if bms.read(1).hex() == '4e' : # header byte 1
                if bms.read(1).hex() == '57' : # header byte 2
                    # next two bytes is the length of the data package, including the two length bytes
                    length = int.from_bytes(bms.read(2),byteorder='big')
                    length -= 2 # Remaining after length bytes

                    # Lets wait until all the data that should be there, really is present.
                    # If not, something went wrong. Flush and exit
                    available = bms.inWaiting()
                    if available != length :
                        time.sleep(0.1)
                        available = bms.inWaiting()
                        # if it's not here by now, exit
                        if available != length :
                            bms.reset_input_buffer()
                            raise Exception("Something went wrong reading the data...")
               
                    # Reconstruct the header and length field
                    b = bytearray.fromhex("4e57") 
                    b += (length+2).to_bytes(2, byteorder='big')
                
                    # Read all the data
                    data = bytearray(bms.read(available))
                    # And re-attach the header (needed for CRC calculation)
                    data = b + data 
        
                    # Calculate the CRC sum
                    crc_calc = sum(data[0:-4])
                    # Extract the CRC value from the data
                    crc_lo = struct.unpack_from('>H', data[-2:])[0]
                
                    # Exit if CRC doesn't match
                    if crc_calc != crc_lo :
                        bms.reset_input_buffer()
                        raise Exception("CRC Wrong")
            
                    # The actual data we need
                    data = data[11:length-19] # at location 0 we have 0x79

                    
                
                    # The byte at location 1 is the length count for the cell data bytes
                    # Each cell has 3 bytes representing the voltage per cell in mV
                    bytecount = data[1]
                
                    # We can use this number to determine the total amount of cells we have
                    cellcount = int(bytecount/3)                
                    print("cellcount=",cellcount)

                    # Voltages start at index 2, in groups of 3
                    volt_array = myRingBuffer(cellcount)
                    for i in range(cellcount) :
                        voltage = struct.unpack_from('>xH', data, i * 3 + 2)[0]/1000
                        volt_array.append(voltage)
                        valName  = "mode=\"cell"+str(i+1)+"_BMS\""
                        valName  = "{" + valName + "}"
                        dataStr  = f"JK_BMS{valName} {voltage}"
                        #print(dataStr, file=fileObj)
                        print(dataStr)
                    print (volt_array.get())
                    max_monomer=volt_array.max()
                    min_monomer=volt_array.min()
                    print ("Min Monomer: ", min_monomer)
                    print ("Max Monomer: ", max_monomer)
                       
                    # Temperatures are in the next nine bytes (MOSFET, Probe 1 and Probe 2), register id + two bytes each for data
                    # Anything over 100 is negative, so 110 == -10
                    temp_fet = struct.unpack_from('>H', data, bytecount + 3)[0]
                    if temp_fet > 100 :
                        temp_fet = -(temp_fet - 100)
                    temp_1 = struct.unpack_from('>H', data, bytecount + 6)[0]
                    if temp_1 > 100 :
                        temp_1 = -(temp_1 - 100)
                    temp_2 = struct.unpack_from('>H', data, bytecount + 9)[0]
                    if temp_2 > 100 :
                        temp_2 = -(temp_2 - 100)
                    temp=(temp_1+temp_2)/2
                    print("temp:",temp)
        
                    # For now we just show the average between the two probes in Grafana
                    valName  = "mode=\"temp_BMS\""
                    valName  = "{" + valName + "}"
                    dataStr  = f"JK_BMS{valName} {(temp_1+temp_2)/2}"
                    #print(dataStr, file=fileObj)
                    print(dataStr)
                        
                    # Battery voltage
                    voltage = struct.unpack_from('>H', data, bytecount + 12)[0]/100
                    print ("V=",voltage)

                    #c1=int(100*current)        # multiply by 100 to get rid of floating-point
                    #current=twos_comp(c1,16)/100   # create the twos complement and divide by 100 again
                    #print("current=",current)

                    #current = struct.unpack_from('>h', data, bytecount + 15)[0]/100
                    #print("current=",current)

                    
                    current_msb = struct.unpack_from('>B', data, bytecount + 15)[0]
                    print("current15B=",current_msb,hex(current_msb))
                    current_lsb = struct.unpack_from('>B', data, bytecount + 16)[0]
                    print("current16B=",current_lsb,hex(current_lsb))
                    if (current_msb >= 128):
                       current=(current_msb-128)*256+current_lsb
                    else:
                       current=current_msb*(-256)+current_lsb
                    current=current/100
                    print("corrected current: ",current)
                    

                    # SOC/ Remaining capacity, %
                    unmodified_capacity = struct.unpack_from('>B', data, bytecount + 18)[0]
                    #allow_larger_100_percent_soc = True
                    allow_larger_100_percent_soc = False
                    if (unmodified_capacity >=100 and allow_larger_100_percent_soc):
                       capacity=unmodified_capacity-5
                    else:
                       capacity=unmodified_capacity

                    if (write_to_file):
                       print ("unmodified SOC                 : ", unmodified_capacity,file=my_file)
                       print ("final SOC                      : ", capacity,file=my_file)
                       # my_file.flush()    # do int once  
  
                    
                    control_loop (min_monomer, max_monomer, current,actual_time)
 
        bms.reset_input_buffer()    
    
    except Exception as e :
        print(e)
    return capacity,voltage,current,temp


#TO debug with no CAN physical interface use
#sudo ip link add dev vcan0 type vcan
#sudo ip link set up vcan0

db = cantools.db.load_file(can_db)
#db = cantools.db.load_file(/home/behn/jk_pylon/pylon_CAN_210124.dbc)
msg_data_Network_alive_msg = {
    'Alive_packet': 0}

msg_data_Battery_SoC_SoH = {
    'SoC': 80,
    'SoH': 100}

msg_data_Battery_Request = {
 'Full_charge_req' : 0,
 'Force_charge_req_II' : 0,
 'Force_charge_req_I' : 0,
 'Discharge_enable' : 1,
 'Charge_enable' : 1}

msg_data_Battery_actual_values_UIt = {
  'Battery_temperature' : 20,
  'Battery_current' : 0,
  'Battery_voltage' : 0}

msg_data_Battery_limits = {
 'Battery_discharge_current_limit' : 60,
 'Battery_charge_current_limit' : 59,
 'Battery_charge_voltage' : 56,
 'Battery_discharge_voltage' : 51 }

msg_data_Battery_Error_Warnings = {
 'Module_numbers' : 16,
 'Charge_current_high_WARN' : 0,
 'Internal_Error_WARN' : 0,
 'voltage_low_WARN' : 0,
 'voltage_high_WARN' : 0,
 'Temperature_high_WARN' : 0,
 'Temperature_low_WARN' : 0,
 'Discharge_current_high_WARN' : 0,
 'Charge_overcurrent_ERR' : 0,
 'System_Error' : 0,
 'Overvoltage_ERR' : 0,
 'Undervoltage_ERR' : 0,
 'Overtemperature_ERR' : 0,
 'Undertemperature_ERR' : 0,
 'Overcurrent_discharge_ERR' : 0 }

Network_alive_msg = db.get_message_by_name('Network_alive_msg')
Battery_SoC_SoH = db.get_message_by_name('Battery_SoC_SoH')
Battery_Manufacturer = db.get_message_by_name('Battery_Manufacturer')
Battery_Request = db.get_message_by_name('Battery_Request')
Battery_actual_values_UIt = db.get_message_by_name('Battery_actual_values_UIt')
Battery_limits = db.get_message_by_name('Battery_limits')
Battery_Error_Warnings = db.get_message_by_name('Battery_Error_Warnings')

msg_data_enc_Network_alive_msg = db.encode_message('Network_alive_msg', msg_data_Network_alive_msg)
msg_data_enc_Battery_SoC_SoH = db.encode_message('Battery_SoC_SoH', msg_data_Battery_SoC_SoH)
msg_data_enc_Battery_Manufacturer = b'\x50\x59\x4c\x4f\x4e\x00\x00\x00'
#hex(ord('P'))
#'0x50'
#hex(ord('Y'))
#'0x59'
#hex(ord('L'))
#'0x4c'
#hex(ord('O'))
#'0x4f'
#hex(ord('N'))
#'0x4e'

msg_data_enc_Battery_Request = db.encode_message('Battery_Request', msg_data_Battery_Request)
msg_data_enc_Battery_actual_values_UIt = db.encode_message('Battery_actual_values_UIt', msg_data_Battery_actual_values_UIt)
msg_data_enc_Battery_limits = db.encode_message('Battery_limits', msg_data_Battery_limits)
msg_data_enc_Battery_Error_Warnings = db.encode_message('Battery_Error_Warnings', msg_data_Battery_Error_Warnings)

msg_tx_Network_alive_msg = can.Message(arbitration_id=Network_alive_msg.frame_id, data=msg_data_enc_Network_alive_msg, is_extended_id=False)
msg_tx_Battery_SoC_SoH = can.Message(arbitration_id=Battery_SoC_SoH.frame_id, data=msg_data_enc_Battery_SoC_SoH, is_extended_id=False)
msg_tx_Battery_Manufacturer = can.Message(arbitration_id=Battery_Manufacturer.frame_id, data=msg_data_enc_Battery_Manufacturer, is_extended_id=False)
msg_tx_Battery_Request = can.Message(arbitration_id=Battery_Request.frame_id, data=msg_data_enc_Battery_Request, is_extended_id=False)
msg_tx_Battery_actual_values_UIt = can.Message(arbitration_id=Battery_actual_values_UIt.frame_id, data=msg_data_enc_Battery_actual_values_UIt, is_extended_id=False)
msg_tx_Battery_limits = can.Message(arbitration_id=Battery_limits.frame_id, data=msg_data_enc_Battery_limits, is_extended_id=False)
msg_tx_Battery_Error_Warnings = can.Message(arbitration_id=Battery_Error_Warnings.frame_id, data=msg_data_enc_Battery_Error_Warnings, is_extended_id=False)


def test_periodic_send_with_modifying_data(bus):
    global mqtt_client
    Alive_packet = 0 #counter
    print("Starting to send a message every 1s")
    task_tx_Network_alive_msg = bus.send_periodic(msg_tx_Network_alive_msg, 1)
    task_tx_Battery_SoC_SoH = bus.send_periodic(msg_tx_Battery_SoC_SoH, 1)
    task_tx_Battery_Manufacturer = bus.send_periodic(msg_tx_Battery_Manufacturer, 1)
    task_tx_Battery_Request = bus.send_periodic(msg_tx_Battery_Request, 1)
    task_tx_Battery_actual_values_UIt = bus.send_periodic(msg_tx_Battery_actual_values_UIt, 1)
    # done by the control loop
    #task_tx_Battery_limits = bus.send_periodic(msg_tx_Battery_limits, 1)
    task_tx_Battery_Error_Warnings = bus.send_periodic(msg_tx_Battery_Error_Warnings, 1)
    time.sleep(0.5)
#    if not isinstance(task, can.ModifiableCyclicTaskABC):
#        print("This interface doesn't seem to support modification")
#        task.stop()
#        return
    while True:
      actual_time=time.time()
      my_soc,my_volt,my_ampere,my_temp=readBMS(actual_time)
      Alive_packet = Alive_packet+1
      print("updating data ", Alive_packet )
      msg_tx_Network_alive_msg.data = db.encode_message('Network_alive_msg',{'Alive_packet': Alive_packet})
      msg_tx_Battery_SoC_SoH.data = db.encode_message('Battery_SoC_SoH',{'SoC': my_soc,
        'SoH': 100})
      if (write_to_file):
        print ("SOC sent via canbus            : ", my_soc,file=my_file)
        #my_file.flush()    # do int once  
      msg_tx_Battery_actual_values_UIt.data = db.encode_message('Battery_actual_values_UIt',{
        'Battery_temperature' : my_temp,
        'Battery_current' : my_ampere,
        'Battery_voltage' : my_volt})

      task_tx_Battery_Manufacturer = bus.send_periodic(msg_tx_Battery_Manufacturer, 1)
      task_tx_Network_alive_msg.modify_data(msg_tx_Network_alive_msg)
      task_tx_Battery_SoC_SoH.modify_data(msg_tx_Battery_SoC_SoH)
      task_tx_Battery_actual_values_UIt.modify_data(msg_tx_Battery_actual_values_UIt)

      if Alive_packet >= 4611686018427387904:
        Alive_packet = 2
      if (write_to_file):
        print ("----------", file=my_file)
        my_file.flush()
        size=os.path.getsize(filename)
        if size>1000000:
          my_file.truncate(0)
          my_file.flush()

      time.sleep(sleepTime)

      print ("----------------------")
    task.stop()
    print("done")


if __name__ == "__main__":
    if (write_to_file):
       my_file=open(filename,'w')
    mqtt_client=my_mqtt.connect_mqtt()
    mqtt_client.loop_start()

    reset_msg = can.Message(arbitration_id=0x00, data=[0, 0, 0, 0, 0, 0], is_extended_id=False)

    for interface, channel in [
        #('socketcan', 'vcan0', 'can0' ),
        ('socketcan', 'can0' ),
        #('ixxat', 0)
    ]:
        print("Carrying out cyclic tests with {} interface".format(interface))
        bus = can.Bus(interface=interface, channel=channel, bitrate=500000)
        test_periodic_send_with_modifying_data(bus)
        bus.shutdown()

    time.sleep(sleepTime)

