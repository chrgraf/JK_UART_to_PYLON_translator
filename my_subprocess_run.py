#!/usr/bin/python

import subprocess
import shlex
import multiprocessing


#def run_cmd(cmd,q):
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
   #r=[status, stdout_str, stderr_str]
   #q.put(r)
   return(status, stdout_str)


def main():
   q_sub = multiprocessing.Queue()
   cmd="echo hallo"
   status,stdout_str=run_cmd(cmd)
   print("Status:", status)
   print("Stdout:", stdout_str)
   if False: 
      mp = multiprocessing.Process(target=run_cmd,args=(cmd,q_sub))
      mp.start()
      mp.join()
      while (not q_sub.empty()):
       q=q_sub.get()
       print ("status: ",q[0])
       print ("stdout: ",q[1])
       print ("stderr: ",q[2])
       



if __name__ == "__main__":
    main()

