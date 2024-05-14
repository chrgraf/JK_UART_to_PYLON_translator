#!/usr/bin/python

import subprocess
import shlex
import multiprocessing


def run_cmd(cmd):
   cmd_split=shlex.split(cmd)
   encode = "utf-8"
   result=subprocess.run(cmd_split,capture_output=True)
   status=result.returncode
   stdout_str=result.stdout.decode(encoding=encode)
   stderr_str=result.stderr.decode(encoding=encode)
   #print("exit Status: ",status)
   #print("std out    : ",stdout_str)
   #print("std err    : ",stderr_str)
   return(status, stdout_str)

def run_cmd_queue(cmd,q):
   cmd_split=shlex.split(cmd)
   encode = "utf-8"
   result=subprocess.run(cmd_split,capture_output=True)
   status=result.returncode
   stdout_str=result.stdout.decode(encoding=encode)
   stderr_str=result.stderr.decode(encoding=encode)
   #print("exit Status: ",status)
   #print("std out    : ",stdout_str)
   #print("std err    : ",stderr_str)
   r=[status, stdout_str, stderr_str]
   q.put(r)
   return(status, stdout_str)


def main():
   cmd="echo hallo"
   status,stdout_str=run_cmd(cmd)
   print("NONE multiprocessing")
   print("--------------------")
   print("Status:", status)
   print("Stdout:", stdout_str)
   if True: 
      print("multiprocessing")
      print("---------------")
      q_sub = multiprocessing.Queue()
      mp = multiprocessing.Process(target=run_cmd_queue,args=(cmd,q_sub))
      mp.start()
      mp.join()
      while (not q_sub.empty()):
       q=q_sub.get()
       print ("status: ",q[0])
       print ("stdout: ",q[1])
       print ("stderr: ",q[2])
       



if __name__ == "__main__":
    main()

