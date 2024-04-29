
import logging
import logging.handlers
import datetime
import time
from logging.handlers import RotatingFileHandler
import glob
import my_subprocess_run
import multiprocessing

def my_compress(filename):
  search=filename + "*[0-9]" 
  list=glob.glob(search)   
  elements=len(list)
  #print(list)
  #print ("len", elements)
  base="gzip -f "
  q=multiprocessing.Queue() 
  for x in list:
     cmd=base + x
     my_subprocess_run.run_cmd(cmd,q)
     #print(cmd)
 
  return(list)


# source: https://stackoverflow.com/questions/9106795/python-logging-and-rotating-files
def log_setup(filename):
    #log_handler = logging.handlers.WatchedFileHandler(filename)
    size=30 * 1024 * 1024    # 30MB
    log_handler = RotatingFileHandler(filename, maxBytes=size, backupCount=5)
    formatter = logging.Formatter(
        '%(asctime)s program_name [%(process)d]: %(message)s',
        '%b %d %H:%M:%S')
    #formatter.converter = time.gmtime  # if you want UTC time
    #formatter.converter = time.localtime()
    log_handler.setFormatter(formatter)
    logger = logging.getLogger()
    logger.addHandler(log_handler)
    logger.setLevel(logging.DEBUG)



def my_debug(s,v):
   date = datetime.datetime.now()
   total=55
   l=len(s)
   s1=s
   v1=v
   for x in range (0,total - l):
      s=s+" "
   #s=str(date)+ " " + s +":"
   s= s +": "
   logging.info(s+str(v))


if __name__ == "__main__":
  filename="testlog"
  log_setup(filename)
  print_debug("this is a sample message with Value","1234")
  # compress
  filename="/mnt/ramdisk/jk_pylon.log"
  my_compress(filename)




