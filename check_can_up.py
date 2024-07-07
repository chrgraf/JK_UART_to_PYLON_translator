#!/usr/bin/python

import subprocess
import shlex
import multiprocessing
encode = "utf-8"
import my_subprocess_run
import time



def check_can_interface_up (channel,can_fail_counter):
   was_up = True
   cmd="sudo ip link show " + channel  # make sure space is after the show
   status, stdout_str=my_subprocess_run.run_cmd(cmd)
   #print("status: ",status)
   #print("stdout: ",stdout_str)
   # lets check if interface is up
   if status==0:
       index=stdout_str.find('state UP ')
       if (index == -1):
           was_up = False
           can_fail_counter=can_fail_counter+1
           print("can interface is down. Lets try to bring back")
           cmd="sudo ip link set " + channel + " down"
           status,stdout_str=my_subprocess_run.run_cmd(cmd)
           time.sleep(1)
           cmd="sudo ip link set " + channel + " type can bitrate 500000"
           status,stdout_str=my_subprocess_run.run_cmd(cmd)
           time.sleep(1)
           cmd="sudo ifconfig "+ channel + " txqueuelen 65536"
           status,stdout_str=my_subprocess_run.run_cmd(cmd)
           time.sleep(1)
           cmd="sudo ip link set " + channel + " up"
           status,stdout_str=my_subprocess_run.run_cmd(cmd)
           time.sleep(1)
           print("status: ",status)
           print("stdout: ",stdout_str)
           if status==0:
              print("sucessfully executed:", cmd)
              #check_can_interface_up (channel,can_fail_counter) 
              was_up = True
           else:
              print("failed to execute:", cmd)
              
       else:
           print ("doing nothing,", channel, " Interface is UP")
           was_up = True
   return(was_up,can_fail_counter)
    

def check_can_interface_up_mp (channel,can_fail_counter,q):
   was_up = True
   cmd="sudo ip link show " + channel  # make sure space is after the show
   status, stdout_str=my_subprocess_run.run_cmd(cmd)
   #print("status: ",status)
   #print("stdout: ",stdout_str)
   # lets check if interface is up
   if status==0:
       index=stdout_str.find('state UP ')
       if (index == -1):
           was_up = False
           can_fail_counter=can_fail_counter+1
           print("can interface is down. Lets try to bring back")
           my_sleep = "sleep 1;"
           cmd="sudo ip link set " + channel + " down"
           status,stdout_str=my_subprocess_run.run_cmd(cmd)
           cmd="sudo ip link set " + channel + " type can bitrate 1000000"
           status,stdout_str=my_subprocess_run.run_cmd(cmd)
           cmd="sudo ifconfig "+ channel + " txqueuelen 65536"
           status,stdout_str=my_subprocess_run.run_cmd(cmd)
           cmd="sudo ip link set " + channel + " up"
           status,stdout_str=my_subprocess_run.run_cmd(cmd)
           #print("status: ",status)
           #print("stdout: ",stdout_str)
           if status==0:
              print("sucessfully executed:", cmd)
           else:
              print("failed to execute:", cmd)
              
       else:
           #print ("doing nothing,", channel, " Interface is UP")
           was_up = True
   r=[was_up,can_fail_counter]
   q.put(r,block=True,timeout=None)
   #print("function queue size: ", q.qsize())
   return(was_up,can_fail_counter)
    





if __name__ == "__main__":
  channel="can0"
  can_fail_counter=0
  was_up=False
  if False:
     q=multiprocessing.Queue()
     mp_check_can = multiprocessing.Process(target=check_can_interface_up ,args=(channel,can_fail_counter,q))
     mp_check_can.start()
     mp_check_can.join()
     while (not q.empty()):
                  result=q.get()
                  was_up=result[0]
                  can_fail_counter = result[1]
                  if (was_up):
                       print ("doing nothing,", channel, " Interface is UP")
     mp_check_can.join()

  was_up,can_fail_counter=check_can_interface_up (channel,can_fail_counter)
  print("Was_up:           ", was_up)
  print("can_fail_counter: ", can_fail_counter)

