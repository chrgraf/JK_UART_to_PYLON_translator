#!/usr/bin/python3
###############################################################################################
# Purpose: read JK-BMS via UART and send info via can-bus using Pylontech Protocol
##########
#credits go to:
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
import check_can_up           # cheks if can0 interface is UP. if not, its using sudo ip link to bring UP

# JK-stuff
import time
import datetime
import sys, os, io
import struct
import serial
import my_read_bms

import multiprocessing

#mqtt - for logging-purposes we send some stuff to a mqtt-broker.
# not required to operate this script successful
import my_mqtt

# self written ringbuffer
from my_basic_ringbuf import myRingBuffer 

# ringbuffer
from queue import Queue
import json

# logfile
write_to_file = True               # turn only on for debug. 
logfile_size = 30                  # size im MB, afterwards its reset to zero
log_to_console = False
#filename="./jk_python_can.log"
filename="/mnt/ramdisk/jk_pylon.log"
import logging
import logging.handlers
import os

# goodwe inverter - with two inverters we must avoid then one battery is discharging to allow charging the other one
import sems

# oscillation
oscillation_enabled_flag=True          # requires SMA smartmeter
last_monomer_run = 0.0
my_mqtt.meter=Queue()

from print_debug import print_debug as print_debug
from print_debug import log_setup as log_setup


sleepTime = 1

def byteArrayToHEX(byte_array):
    hex_string = ""
    for cmd_byte in byte_array:
        hex_byte = ("{0:02x}".format(cmd_byte))
        hex_string += hex_byte + " " 
    return hex_string



def set_discharge_limit(min_volt,Battery_discharge_current_limit,my_soc,timestamp_discharge_limit_change):
  now = time.time()
  discharge_limit=Battery_discharge_current_limit
  print_debug ("discharge_limit when entering set_discharge",Battery_discharge_current_limit)

  mylist=[[3.15,0],[3.20,20],[3.60,60]]
  for i in range(len(mylist)):
     if (min_volt<=mylist[i][0]):
           discharge_limit=mylist[i][1]
           print_debug("discharge_limit min_volt_check",discharge_limit)
           break
 
  # making the discharge-limit smaller is always ok
  if (discharge_limit<Battery_discharge_current_limit):
        Battery_discharge_current_limit=discharge_limit
        print_debug("discharge_limit<Battery_discharge_current_limit",Battery_discharge_current_limit)
   
  # allowing to increase the discharge-limit
  elif (my_soc > 40 and now - timestamp_discharge_limit_change > 30):
         Battery_discharge_current_limit = discharge_limit
         timestamp_discharge_limit_change = now
         print_debug("Battery_discharge_current_limit increase",Battery_discharge_current_limit)
  
  x=now - timestamp_discharge_limit_change
  print_debug("discharge timer",x)
  print_debug("result set_discharge_limit", Battery_discharge_current_limit)
  return(Battery_discharge_current_limit,timestamp_discharge_limit_change)

 
   
def set_charge_limit(max_volt,Battery_charge_current_limit,my_soc,oscillation_got_detected,timestamp_charge_limit_change):
  now = time.time()
  c_limit=Battery_charge_current_limit
  mylist=[[3.60,0],[3.55,0],[3.48,0],[3.45,10],[3.42,20],[3.2,60]]
  for i in range(len(mylist)):
     if (max_volt>=mylist[i][0]):
           c_limit=mylist[i][1]
           print_debug("charge_limit initial array",Battery_charge_current_limit)
           break
  
  #print("c_limit,volt,soc",c_limit,max_volt,my_soc)
  # making the charge-limit smaller is always ok
  if (c_limit<Battery_charge_current_limit):
             Battery_charge_current_limit=c_limit
             #print ("Battery_charge_current_limit done smaller",Battery_charge_current_limit)
  # in case the derived charge-limit is higher then previuos, 
  #   we want to be sure:
  #   >> onlu increase if max_volt is save (<3.4Volt)
  #   >> only increase if SOC < 97%
  # do not increase, if oscillation_got_detected
  # wait at least 600secs before trying to increase back again
  elif (my_soc <=97 and max_volt < 3.4 and not oscillation_got_detected and now - timestamp_charge_limit_change > 600):
             Battery_charge_current_limit=c_limit
             timestamp_charge_limit_change = now
             #print ("Battery_charge_current_limit done larger",Battery_charge_current_limit)

  print_debug ("result set_charge_limit_", Battery_charge_current_limit)
  return(Battery_charge_current_limit, timestamp_charge_limit_change)

def populate_sma_ringbuffer (meter,meter_ringbuffer):
    # have in mind, ringbuffer is WATT, not Ampere
 
    limit_min_max=300
    limit_average=300
    min_event_osci_true=3
    oscillation_got_detected=False
    while not meter.empty():
       my_message=meter.get()
       if my_message is None:
           continue
       y=json.loads(my_message)
       pconsume=y['pconsume']
       #print("pconsume", pconsume)
       psupply=y['psupply']
       #print("psupply", psupply)
       add=False
       if (pconsume>0):
           value=-pconsume
           add=True
       if (psupply>0):
           value=psupply
           add=True
       if (add):
            meter_ringbuffer.append(value)

    
    print_debug ("meter ringbuffer average", f"{meter_ringbuffer.average():.0f}")
    print_debug ("meter ringbuffer min", f"{meter_ringbuffer.min():.0f}")
    print_debug ("meter ringbuffer max", f"{meter_ringbuffer.max():.0f}")
    # gt_count counts elements in buffer GreaterThen
    # lt_count counts elements in buffer LessThen

    if (meter_ringbuffer.gt_count(limit_min_max) > min_event_osci_true and meter_ringbuffer.lt_count(-limit_min_max) > min_event_osci_true):
       if (meter_ringbuffer.average() < limit_average and meter_ringbuffer.average() > -limit_average):
           oscillation_got_detected=True
    return(oscillation_got_detected,meter_ringbuffer)


def populate_solis_current_ringbuffer (current,current_ringbuffer):
         # add actual ampere towards the ringbuffer
         current_ringbuffer.append(current)
         #print ("current_ringbuffer", current_ringbuffer.get())
         return(current_ringbuffer)



#####################################################
# MAIN LOOP: test_periodic_send_with_modifying_data #
#####################################################

def test_periodic_send_with_modifying_data(bus):
    global mqtt_client
    last_mqtt_run=0.0
    mqtt_sent_interval=20
    Battery_discharge_current_limit_default= 60
    Battery_charge_current_limit_default   = 60
    Battery_charge_current_limit = Battery_charge_current_limit_default
    Battery_discharge_current_limit = Battery_discharge_current_limit_default
    timestamp_discharge_limit_change = 0.0               # used to allow increase discharge-limit back again
    timestamp_charge_limit_change = 0.0                  # used to allow increase charge-limit back again
    timestamp_last_osci_run = 0.0                        # how ofetn do we want to check oscilattion and REDUCE the limits
    current_max_size=30                                  # elements in ringbuffer
    current_ringbuffer=myRingBuffer(current_max_size)    # init/flush the ringbuffer
    meter_ringbuffer=myRingBuffer(current_max_size)    # init/flush the ringbuffer
    Battery_charge_voltage_default         = 56
    Battery_discharge_voltage_default      = 51
    # oscillation detection
    oscillation_got_detected=False
    check_can0_up_interval = 10;
    check_can0_up_last_run = 0.0

    q_check_can = multiprocessing.Queue()
    q_my_read_bms = multiprocessing.Queue()

    ###############
    # SEMS  STUFF
    ###############
    Sems_Flag = True                  # set this to True if you have a Goodwe-inverter
    #Sems_Flag = False                  # set this to True if you have a Goodwe-inverter
    if (Sems_Flag):
       token=""
       uid=""
       timestamp=""
       expiry=0.0
       api="https://eu.semsportal.com/api/"  # will be overwritten as part of the get_token
       sems_url_oauth="https://www.semsportal.com/api/v2/Common/CrossLogin"
       sems_current_ringbuffer_A=myRingBuffer(1)           # init the ringbuffer of size 1
       last_sems_run=0.0
    
    # setting up periodic task to send can-bus updates
    ##################################################
    Alive_packet = 0 #counter
    #print("Starting to send a message every 1s")
    task_tx_Network_alive_msg = bus.send_periodic(msg_tx_Network_alive_msg, 1)
    task_tx_Battery_SoC_SoH = bus.send_periodic(msg_tx_Battery_SoC_SoH, 1)
    task_tx_Battery_Manufacturer = bus.send_periodic(msg_tx_Battery_Manufacturer, 1)
    task_tx_Battery_Request = bus.send_periodic(msg_tx_Battery_Request, 1)
    task_tx_Battery_actual_values_UIt = bus.send_periodic(msg_tx_Battery_actual_values_UIt, 1)
    task_tx_Battery_limits = bus.send_periodic(msg_tx_Battery_limits, 1)
    task_tx_Battery_Error_Warnings = bus.send_periodic(msg_tx_Battery_Error_Warnings, 1)
    time.sleep(0.5)
 
    ###########################################################################################
    # main - loop - query the bms, check under/over-volt, updates message for peridic can-task
    ###########################################################################################
    
    while True:
      now=time.time()

      # can-bus counter alive packet
      #########################
      Alive_packet = Alive_packet+1
      if Alive_packet >= 4611686018427387904:
        Alive_packet = 2
      print_debug ("------ new run----------------","")
      print_debug("run", Alive_packet )

      
      # check if can0 interface is up
      #####################
      print_debug("can interface used",channel)
      if (now-check_can0_up_last_run > check_can0_up_interval):
            mp1 = multiprocessing.Process(target=check_can_up.check_can_interface_up,args=(channel,q_check_can))
            mp1.start()
            while (not q_check_can.empty()):
               was_up = q_check_can.get() 
               #was_up=check_can_up.check_can_interface_up (channel)
               if (not was_up):
                  msg="Interface " + channel + "was_up status"
                  print_debug(msg, "DOWN")
               check_can0_up_last_run = now


      # query the BMS
      ###############
      #my_soc,my_volt,my_ampere,my_temp,min_volt, max_volt, current,success=readBMS()
      mp_read_bms = multiprocessing.Process(target=my_read_bms.readBMS, args=(bms,q_my_read_bms,))
      mp_read_bms.start()
      mp_read_bms.join()
      q=q_my_read_bms.get()
      my_soc=q[0]
      my_volt=q[1]
      my_ampere=q[2]
      my_temp=q[3]
      min_volt=q[4]
      max_volt=q[5]
      current=q[6]
      bms_read_success=q[7]
      if (not bms_read_success):
          print_debug("Status reading the BMS","Fail")


      sems_success=False

      if (Sems_Flag):
           # query sems -portal
           #####################
           if (now - last_sems_run > 15):
                last_sems_run=now
                token,uid,timestamp,expiry,api,bp_a,bp_w,sems_success= sems.do_auth_and_query(token,uid,timestamp,expiry,api,sems_url_oauth)
                if (sems_success):
                   print_debug("sems_Query", "Success")
                else:
                   print_debug("Sems_Query", "Failure")
                print_debug ("sems ampere[A] (+ charge, -discharge)",bp_a)
                print_debug ("sems power[W] (+ charge, -discharge)",bp_w)
                sems_current_ringbuffer_A.append(bp_a) 
                my_mqtt.publish(mqtt_client,"sems/Ampere",str(bp_a)) 
                my_mqtt.publish(mqtt_client,"sems/Watt",str(bp_w)) 
           print_debug("sems ringbuffer",sems_current_ringbuffer_A.get())
           print_debug("sems average",sems_current_ringbuffer_A.average())
           print_debug("sems min",sems_current_ringbuffer_A.min())
           print_debug("sems max",sems_current_ringbuffer_A.max())

      # undervolt protection
      #####################
      Battery_discharge_current_limit, timestamp_discharge_limit_change=set_discharge_limit(min_volt,Battery_discharge_current_limit,my_soc,timestamp_discharge_limit_change)

      if (Sems_Flag and (sems_current_ringbuffer_A.average()>0)):
         # goodwe/sems is charging
         # if goodwe charges, then solis must not discharge
         Battery_discharge_current_limit=0

      # overvolt protection
      #####################
      Battery_charge_current_limit,timestamp_charge_limit_change=set_charge_limit(max_volt,Battery_charge_current_limit,my_soc,oscillation_got_detected,timestamp_charge_limit_change)
      
      # avoid charging if goodwe discharges
      # why meter_ringbuffer.average()< 1000:  >> if ringbuffer >1000, e.g. 3kw then there is no need to set charge-limit to zero
      # why -1 for: sems_current_ringbuffer_A.average()<-1 >>> sems sometimes disharges with -40W, but even then we want the solis allow to charge..
      #    that why we set 1A - only if goodwe discharges > 50W (1A * 50V), then we want to stop charging the solis

      if (Sems_Flag and sems_current_ringbuffer_A.average()<=-1.2 and meter_ringbuffer.average()< 1000):        # starting at -1 Ampere. in theory it shll be zero
         # goodwe/sems is discharging
         # if goodwe discharges, then we shall not charge the solis
         Battery_charge_current_limit=0
         print_debug("trigger charge limit 0","sems")
         

      # oscillation detection
      ########################
      # populate both ringbuffers, SMA watt and Solis Ampere
      oscillation_got_detected,meter_ringbuffer=populate_sma_ringbuffer(my_mqtt.meter,meter_ringbuffer)
      if (oscillation_got_detected):
          print_debug("oscillation_got_detected", "True")
          #print_debug ("meter_ringbuffer",meter_ringbuffer())
          print (meter_ringbuffer.get())

      else:
          print_debug("oscillation_got_detected", "False")

      current_ringbuffer=populate_solis_current_ringbuffer(current,current_ringbuffer)
      print_debug("solis_current", current)
      # wait 30sec inbetween each modification
      if (oscillation_enabled_flag and now - timestamp_last_osci_run > 30 and oscillation_got_detected):
                 Battery_charge_current_limit=Battery_charge_current_limit/2
                 Battery_discharge_current_limit=Battery_discharge_current_limit/2
                 timestamp_last_osci_run= now
                 my_mqtt.publish(mqtt_client,"solis/oscillation_got_detected",1)

      
      # DEBUG ONLY - overwirtes any previus automtism derived values
      #Battery_charge_current_limit=10


      # update data for can-bus
      #########################
      msg_tx_Network_alive_msg.data = db.encode_message('Network_alive_msg',{'Alive_packet': Alive_packet})
      #task_tx_Network_alive_msg.modify_data(msg_tx_Network_alive_msg) # failure, produces error message
 
      msg_tx_Battery_SoC_SoH.data = db.encode_message('Battery_SoC_SoH',{'SoC': my_soc,'SoH': 100})
      task_tx_Battery_SoC_SoH.modify_data(msg_tx_Battery_SoC_SoH)     
      print_debug ("SOC sent via canbus", my_soc)
 
      msg_tx_Battery_actual_values_UIt.data = db.encode_message('Battery_actual_values_UIt',{
        'Battery_temperature' : my_temp,
        'Battery_current' : my_ampere,
        'Battery_voltage' : my_volt})
      task_tx_Battery_actual_values_UIt.modify_data(msg_tx_Battery_actual_values_UIt) 

    
      print_debug ("CANBUS: Battery_charge_current_limit", Battery_charge_current_limit)
      print_debug ("CANBUS: Battery_discharge_current_limit", Battery_discharge_current_limit)
     
      msg_tx_Battery_limits.data = db.encode_message('Battery_limits',{
         'Battery_discharge_current_limit' : Battery_discharge_current_limit,
         'Battery_charge_current_limit' : Battery_charge_current_limit,
         'Battery_charge_voltage' : Battery_charge_voltage_default,
         'Battery_discharge_voltage' : Battery_discharge_voltage_default })
      task_tx_Battery_limits.modify_data (msg_tx_Battery_limits)


      # sending some MQTT 
      print_debug("next mqtt sent in seconds",int(mqtt_sent_interval - (now - last_mqtt_run)))
      if (now - mqtt_sent_interval   > last_mqtt_run ):        #wait 20seconds before publish next mqtt
          last_mqtt_run=now
          topic="jk_pylon/Battery_charge_current_limit"
          message=str(Battery_charge_current_limit)
          my_mqtt.publish(mqtt_client,topic,message)      
        
          topic="jk_pylon/Battery_discharge_current_limit"
          message=str(Battery_discharge_current_limit)
          my_mqtt.publish(mqtt_client,topic,message)      

      # truncating the logfile is getting to large. its not a log-rotate... just deletes the old one
      if (write_to_file):
        size=os.path.getsize(filename)
        size=size/1024/1024
        size_mb=f"{size:.0f}"

        print_debug(filename+" size in MB", size_mb)
        if size> logfile_size:
          #print_debug("truncate","")
          #my_file.flush()
          #my_file.truncate(0)
          #my_file.flush()
          #new=filename+"old"
          #os.rename(filename, new)
          os.remove(filename)

      time.sleep(sleepTime)

    task.stop()


if __name__ == "__main__":

   # JK BMS UART INIT
   ##################
   try:
       bms = serial.Serial('/dev/ttyUSB0')
       bms.baudrate = 115200
       bms.timeout  = 0.2
   except:
       print("BMS not found.")

   # CAN BUS INIT
   ##############
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
   msg_data_Battery_limits = {
    'Battery_discharge_current_limit' : 60,
    'Battery_charge_current_limit' : 60,
    'Battery_charge_voltage' : 55,
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
   
   # 7 * message Elements
   Network_alive_msg = db.get_message_by_name('Network_alive_msg')
   Battery_SoC_SoH = db.get_message_by_name('Battery_SoC_SoH')
   Battery_Manufacturer = db.get_message_by_name('Battery_Manufacturer')
   Battery_Request = db.get_message_by_name('Battery_Request')
   Battery_actual_values_UIt = db.get_message_by_name('Battery_actual_values_UIt')
   Battery_limits = db.get_message_by_name('Battery_limits')
   Battery_Error_Warnings = db.get_message_by_name('Battery_Error_Warnings')
   
   # 7 * encoding Elements
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
   
   # 7 * arbitration Elements
   msg_tx_Network_alive_msg = can.Message(arbitration_id=Network_alive_msg.frame_id, data=msg_data_enc_Network_alive_msg, is_extended_id=False)
   msg_tx_Battery_SoC_SoH = can.Message(arbitration_id=Battery_SoC_SoH.frame_id, data=msg_data_enc_Battery_SoC_SoH, is_extended_id=False)
   msg_tx_Battery_Manufacturer = can.Message(arbitration_id=Battery_Manufacturer.frame_id, data=msg_data_enc_Battery_Manufacturer, is_extended_id=False)
   msg_tx_Battery_Request = can.Message(arbitration_id=Battery_Request.frame_id, data=msg_data_enc_Battery_Request, is_extended_id=False)
   msg_tx_Battery_actual_values_UIt = can.Message(arbitration_id=Battery_actual_values_UIt.frame_id, data=msg_data_enc_Battery_actual_values_UIt, is_extended_id=False)
   msg_tx_Battery_limits = can.Message(arbitration_id=Battery_limits.frame_id, data=msg_data_enc_Battery_limits, is_extended_id=False)
   msg_tx_Battery_Error_Warnings = can.Message(arbitration_id=Battery_Error_Warnings.frame_id, data=msg_data_enc_Battery_Error_Warnings, is_extended_id=False)


   # file logging
   ##############
   if (write_to_file):
        #my_file=open(filename,'w')
        print ("Logging to file:",filename)
        log_setup(filename)
   if (not log_to_console):
        print("logging to console is disabled")
        print(" -enable logging to console  by setting variable log_to_console=True")
 
   # mqtt
   #######
   mqtt_client=my_mqtt.connect_mqtt()
   mqtt_client.loop_start()
   mqtt_client.subscribe("SMA-EM/status/1900203015")

   reset_msg = can.Message(arbitration_id=0x00, data=[0, 0, 0, 0, 0, 0], is_extended_id=False)

   #selecting can-bus interface
   for interface, channel in [
         #('socketcan', 'vcan0'),
         ('socketcan', 'can0'),
         #('ixxat', 0)
     ]:
         #print("Carrying out cyclic tests with {} interface".format(interface))
         # in bash or your sytemd-script, make sure can-interface is UP and has 500k speed
         # .e.g systemd: ExecStartPre=-/usr/sbin/ip link set can0 up type can bitrate 500000
         bus = can.Bus(interface=interface, channel=channel, bitrate=500000)
         # entering the main-loop
         test_periodic_send_with_modifying_data(bus)
         bus.shutdown()

   time.sleep(sleepTime)
