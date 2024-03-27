#!/usr/bin/python

import subprocess
import shlex
import multiprocessing
encode = "utf-8"
import my_subprocess_run



def check_can_interface_up (channel,q):
   was_up = True
   cmd="sudo ip link show " + channel  # make sure space is after the show
   status, stdout_str=my_subprocess_run.run_cmd(cmd,q)
   # lets check if interface is up
   if status==0:
       index=stdout_str.find('state UP ')
       if (index == -1):
           was_up = False
           print("can interface is down. Lets try to bring back")
           my_sleep = "sleep 1;"
           cmd1="sudo ip link set " + channel + " up type can bitrate 1000000;"
           cmd2="sudo ifconfig "+ channel + " txqueuelen 65536;"
           cmd3="sudo ip link set " + channel + " can0 up"
           cmd= cmd1 + my_sleep + cmd2 + my_sleep + cmd3
           status,stdout_str=my_subprocess_run.run_cmd(cmd,q)
           if status==0:
              print("sucessfully executed:", cmd)
           else:
              print("failed to execute:", cmd)
              
       else:
           #print ("doing nothing,", channel, " Interface is UP")
           was_up = True
   q.put(was_up)
   return(was_up)
    

if __name__ == "__main__":
  q=multiprocessing.Queue()
  channel="can0"
  was_up=check_can_interface_up (channel,q)
  if (was_up):
       print ("doing nothing,", channel, " Interface is UP")

