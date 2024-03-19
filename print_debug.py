
import logging
import logging.handlers
import datetime
import time

# source: https://stackoverflow.com/questions/9106795/python-logging-and-rotating-files
def log_setup(filename):
    log_handler = logging.handlers.WatchedFileHandler(filename)
    formatter = logging.Formatter(
        '%(asctime)s program_name [%(process)d]: %(message)s',
        '%b %d %H:%M:%S')
    formatter.converter = time.gmtime  # if you want UTC time
    log_handler.setFormatter(formatter)
    logger = logging.getLogger()
    logger.addHandler(log_handler)
    logger.setLevel(logging.DEBUG)


def print_debug (s,v):
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
  print_debug("test","hallo")




