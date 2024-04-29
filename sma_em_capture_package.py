#!/usr/bin/env python3
# coding=utf-8
"""
 *
 * by Wenger Florian 2020-01-04
 * wenger@unifox.at
 *
 *
 *  this software is released under GNU General Public License, version 2.
 *  This program is free software;
 *  you can redistribute it and/or modify it under the terms of the GNU General Public License
 *  as published by the Free Software Foundation; version 2 of the License.
 *  This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
 *  without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 *  See the GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License along with this program;
 *  if not, write to the Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
 *
 * 2018-12-22 Tommi2Day small enhancements
 * 2019-08-13 datenschuft run without config
 *
 */
"""

import signal
import sys
import socket
import struct
import binascii
import os
from configparser import ConfigParser
from speedwiredecoder import *
import multiprocessing


#verbose=True
verbose=False

# clean exit
def abortprogram(signal,frame):
    # Housekeeping -> nothing to cleanup
    print('STRG + C = end program')
    sys.exit(0)

# abort-signal
signal.signal(signal.SIGINT, abortprogram)

def sma_socket_decode(sock,q):
   # print("module name:",__name__, "parent_process:",os.getppid(), "process_id",os.getpid())

   # processing received messages
   smainfo=sock.recv(1024)
   smainfoasci=binascii.b2a_hex(smainfo)
   emparts=decode_speedwire(smainfo)
   
   #print ('----raw-output---')
   #print (smainfo)
   #print ('----asci-output---')
   #print (smainfoasci)
   
   if (verbose):
     print ('----all-found-values---')
     for val in emparts:
       print ('{}: value:{}'.format(val,emparts[val]))
   
   pconsume=emparts["pconsume"]
   psupply=emparts["psupply"]
   #print(pconsume,psupply)
   if (pconsume>0):
       value=-pconsume
   if (psupply>0):
      value=psupply
   if (pconsume==psupply):
      value=0

   q.put(value)
   return (value)


def sma_socket_setup():
   smaemserials=1900203015
   ipbind = '0.0.0.0'
   MCAST_GRP = '239.12.255.254'
   MCAST_PORT = 9522

   sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
   sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
   sock.bind(('', MCAST_PORT))
   try:
       mreq = struct.pack("4s4s", socket.inet_aton(MCAST_GRP), socket.inet_aton(ipbind))
       sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
   except BaseException:
       print('could not connect to mulicast group or bind to given interface')
       sys.exit(1)

   return(sock)

   #sma_socket_decode(sock,q_sma)



   
def main():
   q_sma=multiprocessing.Queue()                  # queue for IPC
   my_sma_socket=sma_socket_setup()               # init the socket
   mp_sma = multiprocessing.Process(target=sma_socket_decode,args=(my_sma_socket,q_sma))
   mp_sma.start()
   mp_sma.join()
   while (not q_sma.empty()):
     value=q_sma.get()
     if (value > 0):
        print ("Einspeisen:",value, "W")
     if (value < 0):
        print ("Bezug von Grid:",value, "W")
     if (value==0):
        print ("Nulleinseisung:", value, "W") 
   


if __name__ == "__main__":
    main()


