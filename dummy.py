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

#hmc5883l sensor to read ampere of Goodwe
import smbus
import my_hmc5883l

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
#oscillation_enabled_flag=True          # requires SMA smartmeter
oscillation_enabled_flag=True
last_monomer_run = 0.0
my_mqtt.meter=Queue()

import print_debug

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



def set_discharge_limit(min_volt,Battery_discharge_current_limit,my_soc):
  now = time.time()
  discharge_limit=Battery_discharge_current_limit
  print_debug.my_debug ("discharge_limit when entering set_discharge",Battery_discharge_current_limit)

  #mylist=[[3.15,0],[3.20,20],[3.60,60]]
  mylist=[[3.15,0],[3.60,60]]
  for i in range(len(mylist)):
     try:
       if (min_volt<=mylist[i][0]):
           discharge_limit=mylist[i][1]
           print_debug.my_debug("discharge_limit min_volt_check",discharge_limit)
           break
     except:
           discharge_limit=0
          
  print_debug.my_debug("set_discharge_limit_1",discharge_limit)
 
  # making the discharge-limit smaller is always ok
  if (discharge_limit<Battery_discharge_current_limit):
        Battery_discharge_current_limit=discharge_limit
        print_debug.my_debug("set_discharge_limit_2",Battery_discharge_current_limit)
   
  # allowing to increase the discharge-limit
  elif (my_soc > 45):  
        Battery_discharge_current_limit = discharge_limit
        print_debug.my_debug("set_discharge_limit_3",discharge_limit)
  
  print_debug.my_debug("set_discharge_limit_4",Battery_discharge_current_limit)
  return(Battery_discharge_current_limit)

 
   
def set_charge_limit_by_max_monomer(max_volt,Battery_charge_current_limit_set_by_overvolt_protect,my_soc,oscillation_got_detected,timestamp_charge_limit_change_overvolt_protect):
  now = time.time()
  dbg="set_charge_limit_by_max_monomer"
  c_limit=Battery_charge_current_limit_set_by_overvolt_protect
  print_debug.my_debug(dbg+"c_limit_0_overvolt_protect_begin",c_limit)
  print_debug.my_debug(dbg+"charge_limit_0",Battery_charge_current_limit_set_by_overvolt_protect)
  mylist=[[3.60,0],[3.55,0],[3.47,0],[3.44,0],[3.42,30],[3.39,60],[3.2,60]]
  for i in range(len(mylist)):
     try:
       if (max_volt>=mylist[i][0]):
           c_limit=mylist[i][1]
           print_debug.my_debug(dbg+"c_limit_1",c_limit)
           break
     except:
         c_limit=0
  
  print_debug.my_debug(dbg+"c_limit_2",c_limit)
  # making the charge-limit smaller is always ok
  if (c_limit<Battery_charge_current_limit_set_by_overvolt_protect):
             timestamp_charge_limit_change_overvolt_protect= now
             Battery_charge_current_limit_set_by_overvolt_protect=c_limit
             print_debug.my_debug(dbg+"c_limit_3",c_limit)
             print_debug.my_debug(dbg+"charge_limit_3",Battery_charge_current_limit_set_by_overvolt_protect)
  # in case the derived charge-limit is higher then previuos, 
  #   we want to be sure:
  #   >> only increase if max_volt is save (<3.4Volt)
  #   >> only increase if SOC < 97%
  # wait at least 45min = 2700sec before trying to increase back again
  elif ((my_soc <=99) and (max_volt < 3.4 and not oscillation_got_detected) and (now - timestamp_charge_limit_change_overvolt_protect> 2700)):
             Battery_charge_current_limit_set_by_overvolt_protect=c_limit
             print_debug.my_debug(dbg+"c_limit_4",c_limit)
             print_debug.my_debug(dbg+"charge_limit_4",Battery_charge_current_limit_set_by_overvolt_protect)
  if False:
  #elif (allow_larger_100_percent_soc and max_volt < 3.4 and not oscillation_got_detected and (now - timestamp_charge_limit_change_overvolt_protect> 2700)):
             Battery_charge_current_limit_set_by_overvolt_protect=c_limit
             print_debug.my_debug(dbg+"c_limit_5",c_limit)
             print_debug.my_debug(dbg+"charge_limit_5",Battery_charge_current_limit_set_by_overvolt_protect)

  print_debug.my_debug(dbg+"c_limit_6",c_limit)
  print_debug.my_debug(dbg+"charge_limit_6",Battery_charge_current_limit_set_by_overvolt_protect)

  return(Battery_charge_current_limit_set_by_overvolt_protect, timestamp_charge_limit_change_overvolt_protect)

def populate_sma_ringbuffer_old (meter,meter_ringbuffer_W):
    # have in mind, ringbuffer is WATT, not Ampere
 
    limit_min_max=250
    limit_average=250
    osci_count=3
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

    
    print_debug.my_debug ("meter_ringbuffer_average", f"{meter_ringbuffer_W.average():.0f}")
    print_debug.my_debug ("meter_ringbuffer_min", f"{meter_ringbuffer_W.min():.0f}")
    print_debug.my_debug ("meter_ringbuffer_max", f"{meter_ringbuffer_W.max():.0f}")
    print_debug.my_debug ("meter_ringbuffer_gt_count", f"{meter_ringbuffer_W.gt_count():.0f}")
    print_debug.my_debug ("meter_ringbuffer_lt_count", f"{meter_ringbuffer_W.lt_count():.0f}")
    # gt_count counts elements in buffer GreaterThen
    # lt_count counts elements in buffer LessThen
    
    upper_value= meter_ringbuffer_W.average()+limit_min_max
    lower_value= meter_ringbuffer_W.average()-limit_min_max
    if (meter_ringbuffer_W.gt_count(upper_value) > osci_count and meter_ringbuffer_W.lt_count(lower_value) > osci_count):
           oscillation_got_detected=True
    return(oscillation_got_detected,meter_ringbuffer_W)

def populate_sma_ringbuffer (meter,meter_ringbuffer_W):
    # have in mind, ringbuffer is WATT, not Ampere
 
    limit_min_max=150
    upper_value= limit_min_max
    lower_value= -limit_min_max
    #limit_average=400
    min_event_osci_true=3
    oscillation_got_detected=False
    meter_ringbuffer_W.append(meter)
    print_debug.my_debug ("meter_ringbuffer_average[W]", f"{meter_ringbuffer_W.average():.0f}")
    print_debug.my_debug ("meter_ringbuffer_min[W]", f"{meter_ringbuffer_W.min():.0f}")
    print_debug.my_debug ("meter_ringbuffer_max[W]", f"{meter_ringbuffer_W.max():.0f}")
    print_debug.my_debug ("meter_actual[W]", f"{meter:.0f}")
    print_debug.my_debug ("meter_ringbuffer_gt_count", f"{meter_ringbuffer_W.gt_count(upper_value):.0f}")
    print_debug.my_debug ("meter_ringbuffer_lt_count", f"{meter_ringbuffer_W.lt_count(lower_value):.0f}")
    # gt_count counts elements in buffer GreaterThen
    # lt_count counts elements in buffer LessThen

    if (meter_ringbuffer_W.gt_count(upper_value) > min_event_osci_true and meter_ringbuffer_W.lt_count(lower_value) > min_event_osci_true):
       #if (meter_ringbuffer_W.average() < limit_average and meter_ringbuffer_W.average() > -limit_average):
           oscillation_got_detected=True
           print_debug.my_debug ("meter_ringbuffer_oscilation_detected", "True")
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
    Battery_charge_current_limit = 0
    Battery_charge_current_limit_set_by_overvolt_protect= 0

    floating_Battery_charge_current_limit = 0
    floating_Battery_discharge_current_limit = 0
 
    Battery_discharge_current_limit = 0
    Not_to_exceed_discharge_limit=0


    timestamp_charge_limit_change = 0.0                  # used to allow increase charge-limit back again
    timestamp_last_osci_limit_change_run = 0.0           # how ofetn do we want to check oscilattion and REDUCE the limits
    timestamp_charge_limit_change_overvolt_protect=0.0
    timestamp_sems_triggered_reduce_charge_limit=0.0

    generic_interval_5 = 5                               # used for JK_BMS_queary and can-bus checking
    timestamp_generic_interval_5=0.0

    current_max_size=10                                  # elements in ringbuffer
    current_ringbuffer=myRingBuffer(current_max_size)    # init/flush the ringbuffer
    meter_ringbuffer_W=myRingBuffer(current_max_size)    # init/flush the ringbuffer
    hmc_ringbuffer_A=myRingBuffer(current_max_size)      # init/flush the ringbuffer
    solis_ringbuffer_A=myRingBuffer(current_max_size)    # init/flush the ringbuffer
    Battery_charge_voltage_default         = 55
    Battery_discharge_voltage_default      = 50.5
    # oscillation detection
    oscillation_got_detected=False
    oscillation_mqtt_interval=10
    oscillation_mqtt_last_run=0.0
    oscillation_last_seen = 0.0
    use_hmc=True

    q_check_can         = multiprocessing.Queue()
    q_my_read_bms       = multiprocessing.Queue()
    q_do_auth_and_query = multiprocessing.Queue()
    q_sma               = multiprocessing.Queue()

    bms_read_success=False
    can_fail_counter=0
    can_up_status = False
    
    # slow start after fresh start
    running_since=time.time()
    slow_start_charge_limit=0

    ###############
    # HMC5883L - reading ampere of Goodwe
    ###############
    try:
        i2c_bus = smbus.SMBus(1)
        my_hmc5883l.setup(i2c_bus)
    except:
       s1="ERROR: HMC5883L not found"
       s2="continuing without HMC5883"
       print(s1,s2)
       print_debug.my_debug(s1,s2)
       hmc_success = False
    else:
       hmc_success = True
 

    ###############
    # SEMS  STUFF
    ###############
    Sems_Flag = True                  # set this to True if you have a Goodwe-inverter
    #Sems_Flag = False                  # set this to True if you have a Goodwe-inverter
    goodwe_enforced_zero_charge   =False
    goodwe_enforced_zero_discharge=False
    if (Sems_Flag):
       token=""
       uid=""
       timestamp=""
       expiry=0.0
       api="https://eu.semsportal.com/api/"  # will be overwritten as part of the get_token
       sems_url_oauth="https://www.semsportal.com/api/v2/Common/CrossLogin"
       sems_current_ringbuffer_A=myRingBuffer(1)           # init the ringbuffer of size 1
       last_sems_run=0.0
       sems_success=False
    
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


    # one time reading the BMS with JOIN-method to init all variables
    ##################################################################
    bms_read_success=False
    bms_count=0
    while (not bms_read_success and bms_count<=3):              # 3 * retry
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
              bms_read_success=q[6]
              allow_larger_100_percent_soc=q[7]
              #print("bms_read_success",bms_read_success)
              if (not bms_read_success):
                  print_debug.my_debug("Status reading the BMS","Fail")
                  print("Status reading the BMS","Fail")
                  time.sleep(5)            # wait 5seconds before retrying
              bms_count=bms_count+1
    if (not bms_read_success):
          msg="reading the BMS failed. exiting the prog"
          sys.exit(msg)
          print_debug.my_debug(msg,"exit")
          print(msg)
          
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
      print_debug.my_debug ("------ new run----------------","")
      print_debug.my_debug("run", Alive_packet )

      #print("Wait timer") 
      #time.sleep(100) 
 
      # check if can0 interface is up
      #####################
      check_can_join=False
      qs=0
      if False:
          while (not q_check_can.empty()):
               result=q_check_can.get(block=True, timeout=1)
               print("CAN Interface: ", result)
               can_up_status=result[0]
               can_fail_counter = result[1]
               #print("content can_up_status: ", can_up_status)
               #print("content can-fail-counter: ", can_fail_counter)
               #print("")
               #print("type can_fail-counter:",type(can_fail_counter))
               msg="can_fail_counter"
               print_debug.my_debug(msg, str(can_fail_counter))

      if (now-timestamp_generic_interval_5> generic_interval_5):
            check_can_join=True
            #mp_check_can = multiprocessing.Process(target=check_can_up.check_can_interface_up_mp,args=(channel,can_fail_counter,q_check_can))
            #mp_check_can.start()
            can_up_status,can_fail_counter=check_can_up.check_can_interface_up (channel,can_fail_counter)

               
      if (not can_up_status):
                  msg="Interface " + channel + " can_up_status"
                  print_debug.my_debug(msg, "DOWN")
                  time.sleep(1)
                  if (can_fail_counter > 30):
                        msg="REBOOTING now becasue can_fail_counter value"
                        print_debug.my_debug(msg, str(can_fail_counter))
                        cmd="sudo reboot"
                        #q_reboot=multiprocessing.Queue()
                        #my_subprocess_run.run_cmd(cmd,q_reboot)
                        my_subprocess_run.run_cmd(cmd)
      print_debug.my_debug("can "+channel + " can_up_status", can_up_status)
      print_debug.my_debug("can_fail_counter", str(can_fail_counter))
      
                  
      # query the BMS
      ###############
      read_bms_join=False             # multiprocessing_flag
      if (now-timestamp_generic_interval_5> generic_interval_5):
          mp_read_bms = multiprocessing.Process(target=my_read_bms.readBMS, args=(bms,q_my_read_bms,))
          mp_read_bms.start()
          read_bms_join=True          # triggers to set join later on
      while (not q_my_read_bms.empty()):
           bms_read_success=False
           q=q_my_read_bms.get()
           my_soc=q[0]
           my_volt=q[1]
           my_ampere=q[2]
           my_temp=q[3]
           min_volt=q[4]
           max_volt=q[5]
           bms_read_success=q[6]
           allow_larger_100_percent_soc=q[7]
           #print("bms_read_success",bms_read_success)
           if (not bms_read_success):
                print_debug.my_debug("Status reading the BMS","Fail")
                print("Status reading the BMS","Fail")
           else:
               # populate solis ringbuffer_ampere
               current_ringbuffer=populate_solis_current_ringbuffer(my_ampere,current_ringbuffer)
               print_debug.my_debug("solis_current", my_ampere)



      # query SMA meter
      #################
      mp_sma = multiprocessing.Process(target=sma_em_capture_package.sma_socket_decode,args=(my_sma_socket,q_sma))
      mp_sma.start()
      oscillation_got_detected=False
      oscillation_last_seen=0.0
      while (not q_sma.empty()):
             meter=q_sma.get()
             # populate ringbuffer for SMA meter
             oscillation_got_detected,meter_ringbuffer_W=populate_sma_ringbuffer(meter,meter_ringbuffer_W)
      
      print_debug.my_debug(str(meter_ringbuffer_W.get()),"meter_ringbuffer")
      
      # query SEMS
      ###############
      if (Sems_Flag):
           # query sems -portal
           #####################
           sems_join=False
           if (now - last_sems_run > 15):
                sems_join=True
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
                    #print("sems_success",sems_success)

                    if (sems_success):
                            print_debug.my_debug("sems_query", "Success")
                            print_debug.my_debug ("sems ampere[A] (+ charge, -discharge)",bp_a)
                            print_debug.my_debug ("sems power[W] (+ charge, -discharge)",bp_w)
                            print_debug.my_debug("sems soc[%]",sems_soc)
                            sems_current_ringbuffer_A.append(bp_a) 
                            if (global_mqtt):
                                my_mqtt.publish(mqtt_client,"sems/Ampere",str(bp_a)) 
                                my_mqtt.publish(mqtt_client,"sems/Watt",str(bp_w)) 
                                my_mqtt.publish(mqtt_client,"sems/soc",str(sems_soc)) 
                    else:
                            print_debug.my_debug("sems_query", "Failure")
           print_debug.my_debug("sems ringbuffer[A]",sems_current_ringbuffer_A.get())
           print_debug.my_debug("sems average[A]",sems_current_ringbuffer_A.average())
           print_debug.my_debug("sems min[A]",sems_current_ringbuffer_A.min())
           print_debug.my_debug("sems max[A]",sems_current_ringbuffer_A.max())

      ###########################
      # query SEMS via HMC5883l
      ###########################
      if (Sems_Flag and hmc_success):
            hmc_read_x= my_hmc5883l.read_raw_data(my_hmc5883l.X_MSB,i2c_bus)
            hmc_read_y= my_hmc5883l.read_raw_data(my_hmc5883l.Y_MSB,i2c_bus)
            hmc_read_z= my_hmc5883l.read_raw_data(my_hmc5883l.Z_MSB,i2c_bus)
            
            if (hmc_read_y > -300):
              if (hmc_read_z > 0):
                 hmc_ampere=48
              else:
                 hmc_ampere=-48
            else:
              hmc_ampere=40/669*hmc_read_y+40
            hmc_ringbuffer_A.append(round(hmc_ampere,2))
            print_debug.my_debug("hmc_x",hmc_read_x)
            print_debug.my_debug("hmc_y",hmc_read_y)
            print_debug.my_debug("hmc_z",hmc_read_z)
            print_debug.my_debug("hmc_ringbuffer[A]",hmc_ringbuffer_A.get())
            print_debug.my_debug("hmc_average_ringbuffer[A]",hmc_ringbuffer_A.average())

      #############################
      # Setting the discharge limit
      #############################
      # undervolt protection
      #####################
      Not_to_exceed_discharge_limit=set_discharge_limit(min_volt,Not_to_exceed_discharge_limit,my_soc)
      if (Sems_Flag):
         
         if (not use_hmc):
             if (sems_current_ringbuffer_A.average()> 400/50):       # we allow it to charge for approx 400W
               # goodwe charges, then solis must not discharge
               l=-1* current_ringbuffer.average()   # assuming we discharge, lets make a postiv value
               l=l-bp_a                             # subtract goodwe ampaere
               if (l>0 and meter_ringbuffer_W.average() > -40):        #only reduce if resulting limit >0 and if average > -20
                                                                       # e.g. it does not make sense to lower doscharge, if we are at -1000W
                  Battery_discharge_current_limit=(int)(l)
               else:
                  Battery_discharge_current_limit=0
                  goodwe_enforced_zero_discharge=True
             else:
               goodwe_enforced_zero_discharge=False

         # using HMC
         else:
              if(hmc_ringbuffer_A.average() > 5):
                  goodwe_enforced_zero_discharge=True
                  if Battery_discharge_current_limit >=1:
                       Battery_discharge_current_limit=Battery_discharge_current_limit-1
              else:
                  goodwe_enforced_zero_discharge=False
                  if Battery_discharge_current_limit < Not_to_exceed_discharge_limit:
                       Battery_discharge_current_limit=Battery_discharge_current_limit+1
                 



        

         print_debug.my_debug("goodwe_enforced_zero_discharge",goodwe_enforced_zero_discharge)


         # discharge-limit slow increase back again
         ###########################################
         if (now-timestamp_generic_interval_5> generic_interval_5 and not goodwe_enforced_zero_discharge):
            if (Battery_discharge_current_limit<Not_to_exceed_discharge_limit):
               Battery_discharge_current_limit=Battery_discharge_current_limit+2
               print_debug.my_debug("slow discharge increase","2")
            if (Battery_discharge_current_limit>Not_to_exceed_discharge_limit):
                Battery_discharge_current_limit=Not_to_exceed_discharge_limit
                print_debug.my_debug("failsafe - limit discharge_limit", Not_to_exceed_discharge_limit)

         # discharge-limit fast increase back again
         ###########################################
         #if (meter_ringbuffer_W.average() < -700 and not goodwe_enforced_zero_discharge):
         if (meter_ringbuffer_W.average() < -700):
              Battery_discharge_current_limit=Not_to_exceed_discharge_limit
              print_debug.my_debug("failsafe - limit discharge_limit",Not_to_exceed_discharge_limit)
         
      print_debug.my_debug("Battery_charge_current_limit_before_charge_limit", Battery_charge_current_limit)

      #############################
      # Setting the charge limit
      #############################
      # overvolt protection - set Battery_charge_current_limit_set_by_overvolt_protect
      #####################
      # first deriving the MAXIMUM of charge-limit: Battery_charge_current_limit_set_by_overvolt_protect
      # used as a safeguard - whatever below stuff does, it must not be larger then the max Battery_charge_current_limit_set_by_overvolt_protect
      Battery_charge_current_limit_set_by_overvolt_protect, timestamp_charge_limit_change_overvolt_protect= \
                      set_charge_limit_by_max_monomer(max_volt,Battery_charge_current_limit_set_by_overvolt_protect,my_soc,oscillation_got_detected,timestamp_charge_limit_change_overvolt_protect)
      print_debug.my_debug("result Battery_charge_current_limit_set_by_overvolt_protect,set_charge_limit", 
               Battery_charge_current_limit_set_by_overvolt_protect)

      # CHARGING: enable/ disable charging based on goodwe 
      #######################################
      if (Sems_Flag):
          sma_ringbuffer_limit=100
          hmc_ringbuffer_A_limit=20
          hmc_trigger_reduce_stage1=-2
          hmc_trigger_reduce_stage2=-12

          # why: if  meter_ringbuffer_W.average()< 1000:  >> if ringbuffer >1000, e.g. 3kw then there is no need to set charge-limit to zero
          # why -1 for: sems_current_ringbuffer_A.average()<-1 >>> sems sometimes disharges with -40W, but even then we want the solis allow to charge..
          #    that why we set 1A - only if goodwe discharges > 50W (1A * 50V), then we want to stop charging the solis
          if (use_hmc):
              # hmc_allow charging
              if ((hmc_ringbuffer_A.average()>hmc_ringbuffer_A_limit) or (meter_ringbuffer_W.average()>sma_ringbuffer_limit)):
                 #goodwe charging with over 20A - so it should be safe to allow charging solis as well
                 # or sma_ringbuffer has heftover watts
                 goodwe_enforced_zero_charge=False
                 # increase back again if prevois set to 0
                 print_debug.my_debug ("hmc_allow_charge","xxxxx1")
                 if (now-timestamp_generic_interval_5> generic_interval_5) and (Battery_charge_current_limit<Battery_charge_current_limit_set_by_overvolt_protect):
                           try: 
                              fast_offset = (int) ((meter_ringbuffer_W.average() / my_volt)+0)
                           except:
                              fast_offset = 0.0
                           slow_offset=1
                           print_debug.my_debug ("hmc_allow_charge","xxxxx20")
                           if (meter_ringbuffer_W.average()>4000):
                             Battery_charge_current_limit=Battery_charge_current_limit_set_by_overvolt_protect
                             print_debug.my_debug ("hmc_allow_charge","xxxxx30")
                           elif (meter_ringbuffer_W.average()>2000):
                             Battery_charge_current_limit=Battery_charge_current_limit+slow_offset+fast_offset
                             print_debug.my_debug ("hmc_allow_charge","xxxxx40")
                           else:
                             Battery_charge_current_limit=Battery_charge_current_limit+slow_offset
                             print_debug.my_debug ("hmc_allow_charge","xxxxx50")

                           print_debug.my_debug("charge limit slow increase",Battery_charge_current_limit)
              # do nothing in case goodwe charges below 20A
              elif ((hmc_ringbuffer_A.average()<=hmc_ringbuffer_A_limit and hmc_ringbuffer_A.average()>hmc_trigger_reduce_stage1)):
                   #do not change charge-limit
                    Battery_charge_current_limit=Battery_charge_current_limit
                    print_debug.my_debug ("hmc_allow_charge","xxxxx60")
                    
              # hmc_disallow charging when goodwe discharges
 
              elif (hmc_ringbuffer_A.average()<=hmc_trigger_reduce_stage1):
                    #Battery_charge_current_limit=0
                    Battery_charge_current_limit=round(Battery_charge_current_limit*6/8)
                    print_debug.my_debug("zz trigger charge limit 0, goodwe discharging","True")
                    goodwe_enforced_zero_charge=True
                    print_debug.my_debug ("hmc_allow_charge","xxxxx70")

              elif (hmc_ringbuffer_A.average()<=hmc_trigger_reduce_stage2):
                    Battery_charge_current_limit=round(Battery_charge_current_limit*3/8)
                    print_debug.my_debug("zz trigger charge limit 0, goodwe discharging","True")
                    goodwe_enforced_zero_charge=True
                    print_debug.my_debug ("hmc_allow_charge","xxxxx80")

              #hmc_disallow charging
              else:
                    Battery_charge_current_limit=0
                    print_debug.my_debug ("hmc_allow_charge","xxxxx90")
                    print_debug.my_debug("xx60 trigger charge limit 0, goodwe discharging","True")
                    goodwe_enforced_zero_charge=True


          # do not use hmc
          else:
              # disallow charging
              if ( meter_ringbuffer_W.average()< sma_ringbuffer_limit):        
                if (sems_current_ringbuffer_A.average()<=-1.2):      # starting at -1 Ampere. in theory it shll be zero
                    # goodwe/sems is discharging
                    # if goodwe discharges, then we shall not charge the solis
                    Battery_charge_current_limit=0
                    print_debug.my_debug("yy trigger charge limit 0, goodwe discharging","True")
                    goodwe_enforced_zero_charge=True
                    timestamp_sems_triggered_reduce_charge_limit=now
                else:
                    goodwe_enforced_zero_charge=False
                    
                    
              # average > limit, so we shall allow charging
              else:
                    # avergage >limit, so enough power leftover
                    goodwe_enforced_zero_charge=False
                    if (now-timestamp_generic_interval_5> generic_interval_5):
                           # if average > limit, then we have enough power left over. so we shall allowing to charge
                           try: 
                              offset = (int) ((meter_ringbuffer_W.average() / my_volt)+0)
                           except:
                              offset = 0.0

                           Battery_charge_current_limit=Battery_charge_current_limit+offset
                           print_debug.my_debug("charge limit slow increase",Battery_charge_current_limit)
 

      # safeguard - never go beynd overvolt protect limit
      if (Battery_charge_current_limit>Battery_charge_current_limit_set_by_overvolt_protect):
                    Battery_charge_current_limit = Battery_charge_current_limit_set_by_overvolt_protect

      print_debug.my_debug("Battery_charge_current_limit_before_osicllation_detection", Battery_charge_current_limit)
      print_debug.my_debug("goodwe_enforced_zero_charge", goodwe_enforced_zero_charge)

      # oscillation detection
      #######################
      #if (oscillation_enabled_flag):
      if (True):
          # oscillation detection - requires SMA enery meter
          if (oscillation_got_detected):
              print_debug.my_debug("oscillation_got_detected", "True")
              print("oscillation_got_detected", "True")
              oscillation_last_seen=now
          else:
              print_debug.my_debug("oscillation_got_detected", "False")

          if (now - oscillation_mqtt_last_run > oscillation_mqtt_interval):
                oscillation_mqtt_last_run=now
                if oscillation_got_detected:
                  if (global_mqtt):
                    my_mqtt.publish(mqtt_client,"sems/oscillation_detected",1)
                else:
                  if (global_mqtt):
                    my_mqtt.publish(mqtt_client,"sems/oscillation_detected",0)

      if (oscillation_enabled_flag):
          # modification allowed after interval
          if(now - timestamp_last_osci_limit_change_run > 60):
               timestamp_last_osci_limit_change_run = now
               #reduce the limits
               if (oscillation_got_detected):
                          Battery_charge_current_limit=(int)(Battery_charge_current_limit/3)
                          Battery_discharge_current_limit=(int)(Battery_discharge_current_limit/3)
                          print_debug.my_debug("discharge-limit-reduced because of oscillation",Battery_discharge_current_limit)
                          print_debug.my_debug("charge-limit-reduced because of oscillation",Battery_charge_current_limit)
  
      print_debug.my_debug("XX2 Battery_charge_current_limit_set_by_overvolt_protect",Battery_charge_current_limit_set_by_overvolt_protect)
      print_debug.my_debug("XX2 Battery_discharge_current_limit after oscillation",Battery_discharge_current_limit)
      print_debug.my_debug("XX2 Battery_charge_current_limit after oscillation",Battery_charge_current_limit)



     
      #if (allow_larger_100_percent_soc and not goodwe_enforced_zero_charge):
      #   Battery_charge_current_limit = Battery_charge_current_limit_set_by_overvolt_protect 

      # quick oscilaation hack - fix load to a max
      #if Battery_charge_current_limit > 41:
      #       Battery_charge_current_limit = 20
      #if Battery_discharge_current_limit > 41:
      #       Battery_discharge_current_limit = 20

      # DEBUG ONLY - overwirtes any previus automtism derived values
      #Battery_charge_current_limit=60
      #Battery_discharge_current_limit=60
          
      ############
      # safeguard   : no further charge/discharge limit changes allowed after here!
      ############
      # Safeguard - the not_to_exceeds values are the cell-protection values.
      # having smaller limits is ok, but never having larger values
      if (Battery_charge_current_limit>Battery_charge_current_limit_set_by_overvolt_protect):
             Battery_charge_current_limit=Battery_charge_current_limit_set_by_overvolt_protect
             print_debug.my_debug("Safeguard charge Limit kicked in","True")
             print("Safeguard charge Limit kicked in","True")
      if (Battery_discharge_current_limit>Not_to_exceed_discharge_limit):
             Battery_discharge_current_limit=Not_to_exceed_discharge_limit
             print_debug.my_debug("Safeguard discharge Limit kicked in","True")
             print("Safeguard discharge Limit kicked in","True")
      if (not bms_read_success):
             Battery_discharge_current_limit=0
             Battery_charge_current_limit=0
             print("if_not_bms_read_success, BMS reading FAILED",Battery_discharge_current_limit)
             print_debug.my_debug("safeguard_reduced_discharge to zero","BMS-Reading-failed")
      

      # update data for can-bus
      #########################
      msg_tx_Network_alive_msg.data = db.encode_message('Network_alive_msg',{'Alive_packet': Alive_packet})
      task_tx_Network_alive_msg.modify_data(msg_tx_Network_alive_msg) # failure, produces error message
 
      msg_tx_Battery_SoC_SoH.data = db.encode_message('Battery_SoC_SoH',{'SoC': my_soc,'SoH': 100})
      task_tx_Battery_SoC_SoH.modify_data(msg_tx_Battery_SoC_SoH)     
      print_debug.my_debug ("SOC sent via canbus", my_soc)
 
      msg_tx_Battery_actual_values_UIt.data = db.encode_message('Battery_actual_values_UIt',{
        'Battery_temperature' : my_temp,
        'Battery_current' : my_ampere,
        'Battery_voltage' : my_volt})
      task_tx_Battery_actual_values_UIt.modify_data(msg_tx_Battery_actual_values_UIt) 

      msg_tx_Battery_limits.data = db.encode_message('Battery_limits',{
         'Battery_discharge_current_limit' : Battery_discharge_current_limit,
         'Battery_charge_current_limit' : Battery_charge_current_limit,
         'Battery_charge_voltage' : Battery_charge_voltage_default,
         'Battery_discharge_voltage' : Battery_discharge_voltage_default })
      task_tx_Battery_limits.modify_data (msg_tx_Battery_limits)

      print_debug.my_debug ("CANBUS: Battery_charge_current_limit", Battery_charge_current_limit)
      print_debug.my_debug ("CANBUS: Battery_discharge_current_limit", Battery_discharge_current_limit)

      # sending some MQTT 
      print_debug.my_debug("next mqtt sent in seconds",int(mqtt_sent_interval - (now - last_mqtt_run)))
      if (now - mqtt_sent_interval   > last_mqtt_run ):        #wait 20seconds before publish next mqtt
          last_mqtt_run=now
          if (global_mqtt):
             topic="jk_pylon/Battery_charge_current_limit"
             message=str(Battery_charge_current_limit)
             my_mqtt.publish(mqtt_client,topic,message)      
        
             topic="jk_pylon/Battery_discharge_current_limit"
             message=str(Battery_discharge_current_limit)
             my_mqtt.publish(mqtt_client,topic,message)      

             topic="jk_pylon/HMC_Sems_Average_A"
             message=str(hmc_ringbuffer_A.average())
             my_mqtt.publish(mqtt_client,topic,message)      

             topic="jk_pylon/SMA_Average_W"
             message=str(meter_ringbuffer_W.average())
             my_mqtt.publish(mqtt_client,topic,message)      


      # compress logfiles
      if (write_to_file and (now-timestamp_generic_interval_5> generic_interval_5)):
              print_debug.my_compress(filename)
			  

      # end of main loop
      if (now-timestamp_generic_interval_5> generic_interval_5):
            timestamp_generic_interval_5=now

      # sending all the joins
      #if (check_can_join):
      #     mp_check_can.join()
      if (read_bms_join):
            mp_read_bms.join()
      mp_sma.join()
      if (Sems_Flag):
         if (sems_join):
           mp_do_auth_and_query.join()
      # check all the mp-queues - shall never increase

      print("BMS status  ", bms_read_success, "  run          ", "{:5d}".format(Alive_packet))
      print("q_check_can:", "{:04d}".format(q_check_can.qsize()),"  q_my_read_bms:", "{:04d}".format(q_my_read_bms.qsize())," q_do_auth_and_query:", "{:04d}".format(q_do_auth_and_query.qsize()), "  q_sma:       ", "{:04d}".format(q_sma.qsize()))
      print ("Ampere:     ", "{:04.1f}".format(my_ampere), "  Volt:        ", "{:04.1f}".format(my_volt), "  min_volt:           ","{:1.2f}".format(min_volt),"  max_volt:    ","{:1.2f}".format(max_volt))
      print ("charge_lim:   ", "{:02d}".format(Battery_charge_current_limit), "  discharge_l:   ", "{:02d}".format(Battery_discharge_current_limit),"  sent_soc%            ","{:3d}".format(my_soc))
      print ("hmc_5883y:  ", "{:03d}".format(hmc_read_y), "  hmc_ampere   ","{:04.1f}".format(hmc_ampere))

      time.sleep(sleepTime)

    task.stop()


if __name__ == "__main__":

   # file logging
   ##############
   if (write_to_file):
        #my_file=open(filename,'w')
        print ("Logging to file:",filename)
        print_debug.log_setup(filename)
   if (not log_to_console):
        print("logging to console is disabled")
        print(" -enable logging to console  by setting variable log_to_console=True")

   # JK BMS UART INIT
   ##################
   usb_jk="/dev/ttyUSB0"
   bms = serial.Serial()
   bms.port=usb_jk
   bms.baudrate = 115200
   bms.timeout  = 0.2

   try:
      bms.open()

   except:
       s1="FATAL ERROR: BMS not found - correct ttyUSB choosen?. see file: "
       s1=s1+sys.argv[0]
       s2="check for variable usb_jk. Aborting/exiting the program"
      
       print(s1,s2)
       print_debug.my_debug(s1,s2)
       sys.exit()
      
 
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
