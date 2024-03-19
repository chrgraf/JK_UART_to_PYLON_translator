import subprocess
import shlex

encode = "utf-8"

def run_cmd(cmd):
   cmd_split=shlex.split(cmd)
   #result=subprocess.check_output(cmd_split)
   result=subprocess.run(cmd_split,capture_output=True)
   status=result.returncode
   stdout_str=result.stdout.decode(encoding=encode)
   stderr_str=result.stderr.decode(encoding=encode)
   #print("exit Status: ",status)
   #print("std out    : ",stdout_str)
   #print("std err    : ",stderr_str)
   return(status, stdout_str)


def check_can_interface_up (channel,q):
   was_up = True
   cmd="sudo ip link show " + channel  # make sure space is after the show
   status, stdout_str=run_cmd(cmd)
   # lets check if interface is up
   if status==0:
       index=stdout_str.find('state UP ')
       if (index == -1):
           was_up = False
           print("can interface is down. Lets try to bring back")
           cmd="sudo ip link set can0 up"
           status,stdout_str=run_cmd(cmd)
           if status==0:
              print("sucessfully executed:", cmd)
           else:
              print("failed to execute:", cmd)
              
       #else:
       #    print ("doing nothing,", channel, " Interface is UP")
   q.put(was_up)
   return(was_up)
    

if __name__ == "__main__":
  channel="can0"
  check_can_interface_up (channel)


