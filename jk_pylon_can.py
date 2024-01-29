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
import datetime
import sys, os, io
import struct
import serial

# other imports
import os.path

#mqtt - for logging-purposes we send some stuff to a mqtt-broker.
# not required to operate this script successful
import my_mqtt

# self written ringbuffer
from my_basic_ringbuf import myRingBuffer 

# logfile
write_to_file = True               # turn only on for debug. no upper size limit of the logfile!
#filename="./jk_python_can.log"
filename="/mnt/ramdisk/jk_pylon.log"

# oscillation
last_osci_run = 0
last_monomer_run = 0

sleepTime = 1




max_volt_last_monomer_run = 0.0

def byteArrayToHEX(byte_array):
    hex_string = ""
    for cmd_byte in byte_array:
        hex_byte = ("{0:02x}".format(cmd_byte))
        hex_string += hex_byte + " " 

    return hex_string

def print_debug (s,v):
   total=40
   l=len(s)
   for x in range (0,total - l):
      s=s+" "
   s=s+":"
   print(s,v)

def set_discharge_limit(min_volt,last_discharge_limit, timestamp_discharge_limit_change, timestamp_min_volt_last_monomer_run):
  run_interval = 5
  now=time.time()
  discharge_limit=last_discharge_limit
  # run this only for each monomer_run_interval interval
  if ( now - run_interval > timestamp_min_volt_last_monomer_run ):   #wait monomer_run_interval
        timestamp_min_volt_last_monomer_run = now
        print("entering the min_max_monomer check")
        
        # setting the discharge limit
        ##############################
        DIS=60
        # min_volt set the limit
        if (min_volt>=3.25):
             DIS = 60
        elif (min_volt>=3.15):
             DIS = 30
        elif (min_volt<=3.05):
             DIS = 0
        
        # making the discharge-limit smaller is always ok
        if (DIS<last_discharge_limit):
             discharge_limit=DIS
             timestamp_discharge_limit_change=now
        # in case the derived discharge-limit is higher then previuos, lets wait an our to allow increasing the discharge
        elif (now - 3600 > timestamp_discharge_limit_change ):
             discharge_limit=DIS
             timestamp_discharge_limit_change=now
        print ("debug set_discharge_limit: ", discharge_limit)
        
  return(discharge_limit,timestamp_discharge_limit_change, timestamp_min_volt_last_monomer_run)
    
   
def set_charge_limit(max_volt,Battery_charge_current_limit,timestamp_charge_limit_change):
  run_interval = 5
  now=time.time()
  c_limit=Battery_charge_current_limit
  # run this only for each monomer_run_interval interval
  if (True):
        # setting the charge limit
        ##############################
        # max_volt the limit
        if (max_volt>=3.60):
              c_limit= 0
        elif (max_volt>=3.55):
              c_limit= 0
        elif (max_volt>=3.48):
              c_limit= 0
        elif (max_volt>=3.45):
              c_limit= 20
        #elif (max_volt>=3.342):
        #      c_limit= 0
        #elif (max_volt>=3.33):
        #      c_limit= 20

  # making the charge-limit smaller is always ok
  if (c_limit<Battery_charge_current_limit):
             Battery_charge_current_limit=c_limit
  # in case the derived charge-limit is higher then previuos, lets wait an our to allow increasing the charge
  elif (now - 3600 > timestamp_charge_limit_change ):
             Battery_charge_current_limit=c_limit
             timestamp_charge_limit_change = now
  print_debug ("result set_charge_limit", Battery_charge_current_limit)
  return(Battery_charge_current_limit,timestamp_charge_limit_change)



def check_osciallation(max_volt,Battery_charge_current_limit,timestamp_charge_limit_change_osci, timestamp_last_osci_run, current_ringbuffer,current, Battery_charge_current_limit_default):
         volt_range_allow_osci_detect=3.4
         oscillation=False
         oscillation_run_interval=10
         now=time.time()
         current_max_deviation_list = [12, 5, 3]
         print ("Debug_oscillation1", Battery_charge_current_limit)
     
         # add actual ampere towards the ringbuffer
         current_ringbuffer.append(current)
         print ("current_ringbuffer", current_ringbuffer.get())
         average=current_ringbuffer.average()
         current_max=current_ringbuffer.max()
         current_min=current_ringbuffer.min()

         if ((max_volt<volt_range_allow_osci_detect) and (now - oscillation_run_interval > timestamp_last_osci_run)):
             timestamp_last_osci_run = now
             for i in current_max_deviation_list:
               if (current_max -average >= i and current_min + average < -i):
                 Battery_charge_current_limit=average + i
                 timestamp_charge_limit_change_osci = now
                 oscillation=True
                 break
             if ( not oscillation):
                 # no osciallation
                 # slowly increase limit to max
                 Battery_charge_current_limit=Battery_charge_current_limit+3
                 if (Battery_charge_current_limit>Battery_charge_current_limit_default):
                      Battery_charge_current_limit=Battery_charge_current_limit_default

             if (write_to_file):
                    print ("oscillation state              : ", oscillation,file=my_file)
                    print ("Charge_limit after osci_run    : ", Battery_charge_current_limit, file=my_file)
                    print (current_ringbuffer.get(), file=my_file)

             topic="jk_pylon/oscillation_state"
             if (oscillation):
                message="1"
                size=current_ringbuffer.len()
                current_ringbuffer=myRingBuffer(size)          # flush the ringbuffer
             else:
                message="0"
             my_mqtt.publish(mqtt_client,topic,message)
         print ("Debug_oscillation", Battery_charge_current_limit)
         return(Battery_charge_current_limit,timestamp_charge_limit_change_osci,timestamp_last_osci_run, current_ringbuffer)


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
def readBMS():
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
                    print_debug("cellcount=",cellcount)

                    # Voltages start at index 2, in groups of 3
                    volt_array = myRingBuffer(cellcount)
                    for i in range(cellcount) :
                        voltage = struct.unpack_from('>xH', data, i * 3 + 2)[0]/1000
                        volt_array.append(voltage)
                        valName  = "mode=\"cell"+str(i+1)+"_BMS\""
                        valName  = "{" + valName + "}"
                        dataStr  = f"JK_BMS{valName} {voltage}"
                        #print(dataStr, file=fileObj)
                        # print(dataStr)
                    print (volt_array.get())
                    max_monomer=volt_array.max()
                    min_monomer=volt_array.min()
                    print_debug("Min Monomer", min_monomer)
                    print_debug("Max Monomer", max_monomer)
                       
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
                    print_debug("temp",temp)
        
                    # For now we just show the average between the two probes in Grafana
                    valName  = "mode=\"temp_BMS\""
                    valName  = "{" + valName + "}"
                    dataStr  = f"JK_BMS{valName} {(temp_1+temp_2)/2}"
                    #print(dataStr, file=fileObj)
                    #print(dataStr)
                        
                    # Battery voltage
                    voltage = struct.unpack_from('>H', data, bytecount + 12)[0]/100
                    print_debug ("Battery Voltage",voltage)

                    #c1=int(100*current)        # multiply by 100 to get rid of floating-point
                    #current=twos_comp(c1,16)/100   # create the twos complement and divide by 100 again
                    #print("current=",current)

                    #current = struct.unpack_from('>h', data, bytecount + 15)[0]/100
                    #print("current=",current)

                    
                    current_msb = struct.unpack_from('>B', data, bytecount + 15)[0]
                    #print("current15B=",current_msb,hex(current_msb))
                    current_lsb = struct.unpack_from('>B', data, bytecount + 16)[0]
                    #print("current16B=",current_lsb,hex(current_lsb))
                    if (current_msb >= 128):
                       current=(current_msb-128)*256+current_lsb
                    else:
                       current=current_msb*(-256)+current_lsb
                    current=current/100
                    print_debug("corrected current: ",current)
                    

                    # SOC/ Remaining capacity, %
                    unmodified_capacity = struct.unpack_from('>B', data, bytecount + 18)[0]
                    print_debug("Debug unmodified capacity", unmodified_capacity)
                    #allow_larger_100_percent_soc = True
                    allow_larger_100_percent_soc = False
                    if (unmodified_capacity >=99 and allow_larger_100_percent_soc):
                       capacity=unmodified_capacity-3
                    else:
                       capacity=unmodified_capacity
                    print_debug("final SOC", capacity)

                    if (write_to_file):
                       print ("unmodified SOC                 : ", unmodified_capacity,file=my_file)
                       print ("final SOC                      : ", capacity,file=my_file)
                       # my_file.flush()    # do int once  
                    
  
 
        bms.reset_input_buffer()    
    
    except Exception as e :
        print(e)
    return capacity,voltage,current,temp,min_monomer, max_monomer, current 


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

# this gets overwritten in the oscialltion function
#msg_data_Battery_limits = {
# 'Battery_discharge_current_limit' : 60,
# 'Battery_charge_current_limit' : 59,
# 'Battery_charge_voltage' : 56,
## 'Battery_discharge_voltage' : 51 }

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
#msg_data_enc_Battery_limits = db.encode_message('Battery_limits', msg_data_Battery_limits)
msg_data_enc_Battery_Error_Warnings = db.encode_message('Battery_Error_Warnings', msg_data_Battery_Error_Warnings)

msg_tx_Network_alive_msg = can.Message(arbitration_id=Network_alive_msg.frame_id, data=msg_data_enc_Network_alive_msg, is_extended_id=False)
msg_tx_Battery_SoC_SoH = can.Message(arbitration_id=Battery_SoC_SoH.frame_id, data=msg_data_enc_Battery_SoC_SoH, is_extended_id=False)
msg_tx_Battery_Manufacturer = can.Message(arbitration_id=Battery_Manufacturer.frame_id, data=msg_data_enc_Battery_Manufacturer, is_extended_id=False)
msg_tx_Battery_Request = can.Message(arbitration_id=Battery_Request.frame_id, data=msg_data_enc_Battery_Request, is_extended_id=False)
msg_tx_Battery_actual_values_UIt = can.Message(arbitration_id=Battery_actual_values_UIt.frame_id, data=msg_data_enc_Battery_actual_values_UIt, is_extended_id=False)
#msg_tx_Battery_limits = can.Message(arbitration_id=Battery_limits.frame_id, data=msg_data_enc_Battery_limits, is_extended_id=False)
msg_tx_Battery_Error_Warnings = can.Message(arbitration_id=Battery_Error_Warnings.frame_id, data=msg_data_enc_Battery_Error_Warnings, is_extended_id=False)


def test_periodic_send_with_modifying_data(bus):
    global mqtt_client
    last_mqtt_run=0.0
    mqtt_sent_interval=20
    Battery_discharge_current_limit_default= 60
    Battery_charge_current_limit_default   = 60
    Battery_charge_current_limit = Battery_charge_current_limit_default
    Battery_discharge_current_limit = Battery_discharge_current_limit_default
    timestamp_discharge_limit_change = 0.0
    timestamp_charge_limit_change = 0.0
    timestamp_min_volt_last_monomer_run = 0.0
    timestamp_charge_limit_change_osci = 0.0
    timestamp_last_osci_run = 0.0
    current_max_size=60                                  # elements in ringbuffer
    current_ringbuffer=myRingBuffer(current_max_size)    # init/flush the ringbuffer
    Battery_charge_voltage_default         = 56
    Battery_discharge_voltage_default      = 51

    Alive_packet = 0 #counter
    print("Starting to send a message every 1s")
    task_tx_Network_alive_msg = bus.send_periodic(msg_tx_Network_alive_msg, 1)
    task_tx_Battery_SoC_SoH = bus.send_periodic(msg_tx_Battery_SoC_SoH, 1)
    task_tx_Battery_Manufacturer = bus.send_periodic(msg_tx_Battery_Manufacturer, 1)
    task_tx_Battery_Request = bus.send_periodic(msg_tx_Battery_Request, 1)
    task_tx_Battery_actual_values_UIt = bus.send_periodic(msg_tx_Battery_actual_values_UIt, 1)
    # sending init values only. modified by function test_periodic_send_with_modifying_data
    #task_tx_Battery_limits = bus.send_periodic(msg_tx_Battery_limits, 1)
    task_tx_Battery_Error_Warnings = bus.send_periodic(msg_tx_Battery_Error_Warnings, 1)
    time.sleep(0.5)
#    if not isinstance(task, can.ModifiableCyclicTaskABC):
#        print("This interface doesn't seem to support modification")
#        task.stop()
#        return
    while True:
      now=time.time()
      my_soc,my_volt,my_ampere,my_temp,min_volt, max_volt, current=readBMS()

      # undervolt protection
      #####################
      Battery_discharge_current_limit,timestamp_discharge_limit_change, timestamp_min_volt_last_monomer_run = set_discharge_limit(min_volt,Battery_discharge_current_limit,timestamp_discharge_limit_change, timestamp_min_volt_last_monomer_run)
      #print ("Debug xxxx", Battery_discharge_current_limit)

      # overvolt protection
      #####################
      Battery_charge_current_limit,timestamp_charge_limit_change= set_charge_limit(max_volt,Battery_charge_current_limit,timestamp_charge_limit_change)

      # osciallation detection
      ########################
      #Battery_charge_current_limit,timestamp_charge_limit_change_osci, timestamp_last_osci_run, current_ringbuffer = check_osciallation(max_volt,Battery_charge_current_limit,timestamp_charge_limit_change_osci, timestamp_last_osci_run, current_ringbuffer, current,Battery_charge_current_limit_default)

      Alive_packet = Alive_packet+1
      print ("")
      print_debug("updating data", Alive_packet )
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

      if (write_to_file):
         print ("Battery_charge_current_limit before manual overwrite", Battery_charge_current_limit, file=my_file)

      # only for debug - hard enforcing a limit 
      #Battery_discharge_current_limit= 10
      #Battery_charge_current_limit= 2
    
      print_debug("next mqtt sent in seconds",int(mqtt_sent_interval - (now - last_mqtt_run)))
      if (now - mqtt_sent_interval   > last_mqtt_run ):        #wait 20seconds before publish next mqtt
          print (">>>>>>>>>>>>>>>>>>>>>>")
          last_mqtt_run=now
          topic="jk_pylon/Battery_charge_current_limit"
          message=str(Battery_charge_current_limit)
          my_mqtt.publish(mqtt_client,topic,message)      
        
          topic="jk_pylon/Battery_discharge_current_limit"
          message=str(Battery_discharge_current_limit)
          my_mqtt.publish(mqtt_client,topic,message)      
        
    
      print_debug ("CANBUS: Battery_charge_current_limit", Battery_charge_current_limit)
      print_debug ("CANBUS: Battery_discharge_current_limit", Battery_discharge_current_limit)
      now_date = datetime.datetime.now()
      if (write_to_file):
        print ("min_volt, max_volt             : ", min_volt, max_volt,file=my_file)
        print ("Battery_charge_current_limit   : ", Battery_charge_current_limit,file=my_file)
        print ("Battery_discharge_current_limit: ", Battery_discharge_current_limit,file=my_file)
        print ("Date                           : ", now_date, file=my_file)
    
     
      msg_data_Battery_limits = {
         'Battery_discharge_current_limit' : Battery_discharge_current_limit,
         'Battery_charge_current_limit' : Battery_charge_current_limit,
         'Battery_charge_voltage' : Battery_charge_voltage_default,
         'Battery_discharge_voltage' : Battery_discharge_voltage_default }

      if (write_to_file):
        print (msg_data_Battery_limits,file=my_file)
      print (msg_data_Battery_limits)
    
      Battery_limits = db.get_message_by_name('Battery_limits')
      msg_data_enc_Battery_limits = db.encode_message('Battery_limits', msg_data_Battery_limits)
      msg_tx_Battery_limits = can.Message(arbitration_id=Battery_limits.frame_id, data=msg_data_enc_Battery_limits, is_extended_id=False)
      task_tx_Battery_limits = bus.send_periodic(msg_tx_Battery_limits, 1)
    

      if Alive_packet >= 4611686018427387904:
        Alive_packet = 2
      if (write_to_file):
        print ("", file=my_file)
        print ("----------", file=my_file)
        my_file.flush()
        size=os.path.getsize(filename)
        if size>30 * 1000* 1000:
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

