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
import socket

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

#read SMA power-meter
import sma_em_capture_package 

import my_subprocess_run


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
  elif (my_soc > 35 and now - timestamp_discharge_limit_change > 30):
         Battery_discharge_current_limit = discharge_limit
         timestamp_discharge_limit_change = now
         print_debug("Battery_discharge_current_limit increase",Battery_discharge_current_limit)
  
  x=now - timestamp_discharge_limit_change
  print_debug("discharge timer",x)
  print_debug("result set_discharge_limit", Battery_discharge_current_limit)
  return(Battery_discharge_current_limit,timestamp_discharge_limit_change)

 
   
def set_charge_limit(max_volt,Battery_charge_current_limit_set_by_overvolt_protect,my_soc,oscillation_got_detected,timestamp_charge_limit_change_overvolt_protect):
  now = time.time()
  c_limit=Battery_charge_current_limit_set_by_overvolt_protect
  mylist=[[3.60,0],[3.55,0],[3.48,0],[3.45,00],[3.42,20],[3.2,60]]
  for i in range(len(mylist)):
     if (max_volt>=mylist[i][0]):
           c_limit=mylist[i][1]
           print_debug("charge_limit initial array",c_limit)
           break
  
  #print("c_limit,volt,soc",c_limit,max_volt,my_soc)
  # making the charge-limit smaller is always ok
  if (c_limit<Battery_charge_current_limit_set_by_overvolt_protect):
             Battery_charge_current_limit_set_by_overvolt_protect=c_limit
             #print ("Battery_charge_current_limit done smaller",Battery_charge_current_limit)
  # in case the derived charge-limit is higher then previuos, 
  #   we want to be sure:
  #   >> only increase if max_volt is save (<3.4Volt)
  #   >> only increase if SOC < 97%
  # wait at least 600secs before trying to increase back again
  elif (my_soc <=97 and max_volt < 3.4 and not oscillation_got_detected and now - timestamp_charge_limit_change_overvolt_protect> 600):
             Battery_charge_current_limit_set_by_overvolt_protect=c_limit
             timestamp_charge_limit_change_overvolt_protect= now
             #print ("Battery_charge_current_limit done larger",Battery_charge_current_limit)

  print_debug ("result set_charge_limit_", Battery_charge_current_limit_set_by_overvolt_protect)
  return(Battery_charge_current_limit_set_by_overvolt_protect, timestamp_charge_limit_change_overvolt_protect)

def populate_sma_ringbuffer_old (meter,meter_ringbuffer_W):
    # have in mind, ringbuffer is WATT, not Ampere
 
    limit_min_max=250
    limit_average=250
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
            meter_ringbuffer_W.append(value)

    
    print_debug ("meter ringbuffer average", f"{meter_ringbuffer_W.average():.0f}")
    print_debug ("meter ringbuffer min", f"{meter_ringbuffer_W.min():.0f}")
    print_debug ("meter ringbuffer max", f"{meter_ringbuffer_W.max():.0f}")
    # gt_count counts elements in buffer GreaterThen
    # lt_count counts elements in buffer LessThen

    if (meter_ringbuffer_W.gt_count(limit_min_max) > min_event_osci_true and meter_ringbuffer_W.lt_count(-limit_min_max) > min_event_osci_true):
       if (meter_ringbuffer_W.average() < limit_average and meter_ringbuffer_W.average() > -limit_average):
           oscillation_got_detected=True
    return(oscillation_got_detected,meter_ringbuffer_W)

def populate_sma_ringbuffer (meter,meter_ringbuffer_W):
    # have in mind, ringbuffer is WATT, not Ampere
 
    limit_min_max=300
    limit_average=300
    min_event_osci_true=8
    oscillation_got_detected=False
    meter_ringbuffer_W.append(meter)
    print_debug ("meter ringbuffer average", f"{meter_ringbuffer_W.average():.0f}")
    print_debug ("meter ringbuffer min", f"{meter_ringbuffer_W.min():.0f}")
    print_debug ("meter ringbuffer max", f"{meter_ringbuffer_W.max():.0f}")
    # gt_count counts elements in buffer GreaterThen
    # lt_count counts elements in buffer LessThen

    if (meter_ringbuffer_W.gt_count(limit_min_max) > min_event_osci_true and meter_ringbuffer_W.lt_count(-limit_min_max) > min_event_osci_true):
       if (meter_ringbuffer_W.average() < limit_average and meter_ringbuffer_W.average() > -limit_average):
           oscillation_got_detected=True
           # flusing the ringbuffer for a clean start
           meter_ringbuffer_W.flush()
    return(oscillation_got_detected,meter_ringbuffer_W)

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
    Battery_charge_current_limit_set_by_overvolt_protect= Battery_charge_current_limit_default
 
    Battery_discharge_current_limit = Battery_discharge_current_limit_default
    Not_to_exceed_discharge_limit=Battery_discharge_current_limit_default

    timestamp_discharge_limit_change = 0.0               # used to allow increase discharge-limit back again
    timestamp_charge_limit_change = 0.0                  # used to allow increase charge-limit back again
    timestamp_last_osci_limit_change_run = 0.0           # how ofetn do we want to check oscilattion and REDUCE the limits
    timestamp_charge_limit_change_overvolt_protect=0.0
    timestamp_sems_triggered_reduce_charge_limit=0.0

    current_max_size=12                                  # elements in ringbuffer
    current_ringbuffer=myRingBuffer(current_max_size)    # init/flush the ringbuffer
    meter_ringbuffer_W=myRingBuffer(current_max_size)    # init/flush the ringbuffer
    Battery_charge_voltage_default         = 55
    Battery_discharge_voltage_default      = 50.5
    # oscillation detection
    oscillation_got_detected=False
    oscillation_mqtt_interval=10
    oscillation_mqtt_last_run=0.0
    oscillation_last_seen = 0.0
    check_can0_up_interval = 10;
    check_can0_up_last_run = 0.0
    can_retries=0

    q_check_can = multiprocessing.Queue()
    q_my_read_bms = multiprocessing.Queue()
    q_do_auth_and_query = multiprocessing.Queue()
    q_file_check =  multiprocessing.Queue()
    q_sma=multiprocessing.Queue()


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

    # setting up SMA energy meter
    ##############################
    my_sma_socket=sma_em_capture_package.sma_socket_setup()

 
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
            check_can0_up_last_run = now
            #was_up=check_can_up.check_can_interface_up(channel)
            mp_check_can = multiprocessing.Process(target=check_can_up.check_can_interface_up,args=(channel,q_check_can))
            mp_check_can.start()
      while (not q_check_can.empty()):
               was_up = q_check_can.get()
               if (not was_up):
                  msg="Interface " + channel + "was_up status"
                  print_debug(msg, "DOWN")
                  can_retries = can_retries +1
                  if (can_retries > 5):
                        cmd="sudo reboot"
                        q_reboot=multiprocessing.Queue()
                        # now reboot the RPI to bring back the interface as last resort
                        my_subprocess_run.run_cmd(cmd,q)
      

      
                   
                  
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
      #print(bms_read_success)
      if (not bms_read_success):
          print_debug("Status reading the BMS","Fail")
          #print("Status reading the BMS","Fail")

      # query SEMS
      ###############
      if (Sems_Flag):
           # query sems -portal
           #####################
           sems_success=False
           if (now - last_sems_run > 15):
                last_sems_run=now
                mp_do_auth_and_query = multiprocessing.Process(target=sems.do_auth_and_query,args=(token,uid,timestamp,expiry,api,sems_url_oauth,q_do_auth_and_query))
                mp_do_auth_and_query.start()
           while (not q_do_auth_and_query.empty()):
                    q=q_do_auth_and_query.get()
                    token=q[0]
                    uid=q[1]
                    timestamp=q[2]
                    expiry=q[3]
                    api=q[4]
                    bp_a=q[5]
                    bp_w=q[6]
                    sems_success=q[7]
                    sems_soc=q[8]

                #token,uid,timestamp,expiry,api,bp_a,bp_w,sems_success= sems.do_auth_and_query(token,uid,timestamp,expiry,api,sems_url_oauth)
           if (sems_success):
                   print_debug("sems_Query", "Success")
                   print_debug ("sems ampere[A] (+ charge, -discharge)",bp_a)
                   print_debug ("sems power[W] (+ charge, -discharge)",bp_w)
                   sems_current_ringbuffer_A.append(bp_a) 
                   if (global_mqtt):
                       my_mqtt.publish(mqtt_client,"sems/Ampere",str(bp_a)) 
                       my_mqtt.publish(mqtt_client,"sems/Watt",str(bp_w)) 
           else:
                   print_debug("Sems_Query", "Failure")
           print_debug("sems ringbuffer[A]",sems_current_ringbuffer_A.get())
           print_debug("sems average[A]",sems_current_ringbuffer_A.average())
           print_debug("sems min[A]",sems_current_ringbuffer_A.min())
           print_debug("sems max[A]",sems_current_ringbuffer_A.max())

      # undervolt protection
      #####################
      Not_to_exceed_discharge_limit, timestamp_discharge_limit_change=set_discharge_limit(min_volt,Not_to_exceed_discharge_limit,my_soc,timestamp_discharge_limit_change)

      if (Sems_Flag and (sems_current_ringbuffer_A.average()>0)):
         # goodwe/sems is charging
         # if goodwe charges, then solis must not discharge
         Battery_discharge_current_limit=0
         goodwe_enforced_zero_discharge=True
      else:
         goodwe_enforced_zero_discharge=False
         

      # overvolt protection
      #####################
      # first deriving the MAXIMUM of charge-limit: Battery_charge_current_limit_set_by_overvolt_protect
      # used as a safeguard - whatever below stuff does, it must not be larger then the max Battery_charge_current_limit_set_by_overvolt_protect
      Battery_charge_current_limit_set_by_overvolt_protect, timestamp_charge_limit_change_overvolt_protect=set_charge_limit(max_volt,Battery_charge_current_limit,my_soc,oscillation_got_detected,timestamp_charge_limit_change)
      print_debug("result Battery_charge_current_limit_set_by_overvolt_protect,set_charge_limit", Battery_charge_current_limit_set_by_overvolt_protect)
      
      # avoid charging if goodwe discharges
      #######################################
      # why meter_ringbuffer_W.average()< 1000:  >> if ringbuffer >1000, e.g. 3kw then there is no need to set charge-limit to zero
      # why -1 for: sems_current_ringbuffer_A.average()<-1 >>> sems sometimes disharges with -40W, but even then we want the solis allow to charge..
      #    that why we set 1A - only if goodwe discharges > 50W (1A * 50V), then we want to stop charging the solis

      if (Sems_Flag and sems_current_ringbuffer_A.average()<=-1.2 and meter_ringbuffer_W.average()< 1000):        # starting at -1 Ampere. in theory it shll be zero
         # goodwe/sems is discharging
         # if goodwe discharges, then we shall not charge the solis
         Battery_charge_current_limit=0
         print_debug("trigger charge limit 0, goodwe discharging","True")
         goodwe_enforced_zero_charge=True
         timestamp_sems_triggered_reduce_charge_limit=now
      else:
         goodwe_enforced_zero_charge=False
         

      # wait 30sec inbetween each modification
      modification_interval=30

      if (oscillation_enabled_flag):
          # oscillation detection - requires SMA enery meter
          ########################
          # Query SMA meter
          mp_sma = multiprocessing.Process(target=sma_em_capture_package.sma_socket_decode,args=(my_sma_socket,q_sma))
          mp_sma.start()
          oscillation_got_detected=False
          oscillation_last_seen=0.0
          while (not q_sma.empty()):
             meter=q_sma.get()
             # populate ringbuffer for SMA meter
             oscillation_got_detected,meter_ringbuffer_W=populate_sma_ringbuffer(meter,meter_ringbuffer_W)
          if (oscillation_got_detected):
              print_debug("oscillation_got_detected", "True")
              print("oscillation_got_detected", "True")
              #print_debug ("meter_ringbuffer_W",meter_ringbuffer_W())
              #print (meter_ringbuffer_W.get())
              oscillation_last_seen=now
          else:
              print_debug("oscillation_got_detected", "False")

          if (now - oscillation_mqtt_last_run > oscillation_mqtt_interval):
                oscillation_mqtt_last_run=now
                if oscillation_got_detected:
                  if (global_mqtt):
                    my_mqtt.publish(mqtt_client,"sems/oscillation_detected",1)
                else:
                  if (global_mqtt):
                    my_mqtt.publish(mqtt_client,"sems/oscillation_detected",0)

          # populate solis ringbuffer_ampere
          current_ringbuffer=populate_solis_current_ringbuffer(current,current_ringbuffer)
          print_debug("solis_current", current)
 
          
          # modification allowed after interval
          if(now - timestamp_last_osci_limit_change_run > modification_interval):
               #reduce the limits
               if (oscillation_got_detected):
                          Battery_charge_current_limit=Battery_charge_current_limit/2
                          Battery_discharge_current_limit=Battery_discharge_current_limit/2
                          timestamp_last_osci_limit_change_run= now
                          print_debug("charge-limit-reduced because of oscillation",Battery_charge_current_limit)

               # in case no oscillation, restore old values
               #increase the limits
               if(not oscillation_got_detected):
                    if (not goodwe_enforced_zero_charge):
                         Battery_charge_current_limit = Battery_charge_current_limit +5         # slow increase
                         if Battery_charge_current_limit > Battery_charge_current_limit_set_by_overvolt_protect:
                                Battery_charge_current_limit = Battery_charge_current_limit_set_by_overvolt_protect # never get above the limit derived by cell-protection
                         print_debug("charge-limit-increased because of NO oscillation",Battery_charge_current_limit)
                     
                    if (not goodwe_enforced_zero_discharge):
                         #Battery_discharge_current_limit = Not_to_exceed_discharge_limit       # fast increase
                         Battery_discharge_current_limit = Battery_discharge_current_limit +5   # slow increase by 5ampere each interval
                         if Battery_discharge_current_limit > Not_to_exceed_discharge_limit:    # never go abobove the limit derived by cell-protection
                                Battery_discharge_current_limit = Not_to_exceed_discharge_limit
                         print_debug("discharge-limit-increased because of NO oscillation",Battery_discharge_current_limit)
    
      # if charge_limit set to zero, slowly increase it back 
      # e.g. after 30min, 1800sec: 1800/60 = 30... 30*2 = 60A
      if (not goodwe_enforced_zero_charge and Sems_Flag):
              secs_after_last_change=now -timestamp_sems_triggered_reduce_charge_limit
              interval = 60              # allow an increase each 60sec
              step = 2
              Battery_charge_current_limit =  (int)((secs_after_last_change / interval) * step)
              #print("secs_after_last_change:", secs_after_last_change)
              #print ("Battery_charge_current_limit:", Battery_charge_current_limit)
              # safeguard
              if (Battery_charge_current_limit>Battery_charge_current_limit_set_by_overvolt_protect):
                    Battery_charge_current_limit = Battery_charge_current_limit_set_by_overvolt_protect
              #print ("1Battery_charge_current_limit:", Battery_charge_current_limit)
         
      # if average > 500, then we have enough power left over. so we shall allowing to charge
      if (meter_ringbuffer_W.average()> 500):
              Battery_charge_current_limit=Battery_charge_current_limit_set_by_overvolt_protect
              print_debug("charge-limit-reset becasue of enough exceed-power",Battery_charge_current_limit)
      
      # DEBUG ONLY - overwirtes any previus automtism derived values
      #Battery_charge_current_limit=35
      #Battery_discharge_current_limit=0
       
      ############
      # safeguard   : no further limit changes allowd after here!
      ############
      # Safeguard - the not_to_exceeds values are the cell-protection values.
      # having smaller limits is ok, but never having larger values
      if (Battery_charge_current_limit>Battery_charge_current_limit_set_by_overvolt_protect):
             Battery_charge_current_limit=Battery_charge_current_limit_set_by_overvolt_protect
             print_debug("Safeguard charge Limit kicked in","True")
             print("Safeguard charge Limit kicked in","True")
      if (Battery_discharge_current_limit>Not_to_exceed_discharge_limit):
             Battery_discharge_current_limit=Not_to_exceed_discharge_limit
             print_debug("Safeguard discharge Limit kicked in","True")
             print("Safeguard discharge Limit kicked in","True")


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
          if (global_mqtt):
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
          cmd="gzip -f " + filename
          # the run.cmd command executes the subprocess command to zip the file
          mp_gzip = multiprocessing.Process(target=my_subprocess_run.run_cmd, args=(cmd,q_file_check))
          mp_gzip.start()
          while (not q_file_check.empty()):
             q=q_file_check.get()
             #print ("status: ",q[0])
             #print ("stdout: ",q[1])
             #print ("stderr: ",q[2])
          #status, stdout_str=check_can_up.run_cmd(cmd)
          #os.remove(filename)

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
 
   print (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
   #my_now = datetime.now()
   #dt_string = my_now.strftime("%d/%m/%Y %H:%M:%S")
   #print("date and time =", dt_string)


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
   # first checking via socket if the host is available
   # if not available, then set global flog for MQQT= False, hence disable it
   s = socket.socket()
   mqtt_ip= '192.168.178.116'
   global_mqtt=False
   mqtt_port= 1883  # port number is a number, not string
   try:
       s.connect((mqtt_ip, mqtt_port))
   except Exception as e:
       print("something's wrong with %s:%d. Exception is %s" % (mqtt_ip, mqtt_port, e))
       global_mqtt=False
   else:
       mqtt_client=my_mqtt.connect_mqtt(mqtt_ip,mqtt_port)
       mqtt_client.loop_start()
       global_mqtt=True
       # subscribe not any longer required. sma-em package is part of this script
       #mqtt_client.subscribe("SMA-EM/status/1900203015")
   finally:
       s.close()
   
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
