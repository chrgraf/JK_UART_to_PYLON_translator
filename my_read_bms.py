import serial
import time
import multiprocessing

import sys, os, io
import struct

from print_debug import print_debug as print_debug
from print_debug import log_setup as log_setup

from my_basic_ringbuf import myRingBuffer

sleepTime=2


def sendBMSCommand(bms,cmd_string):
    # The hex string composing the command, including CRC check etc.
    # See also:
    # - https://github.com/syssi/esphome-jk-bms
    # - https://github.com/NEEY-electronic/JK/tree/JK-BMS
    # - https://github.com/Louisvdw/dbus-serialbattery
    cmd_bytes = bytearray.fromhex(cmd_string)
    for cmd_byte in cmd_bytes:
        hex_byte = ("{0:02x}".format(cmd_byte))
        bms.write(bytearray.fromhex(hex_byte))
    return


# This could be much better, but it works.
def readBMS(bms,q):
    capacity=0.0
    voltage = 0.0
    current=0.0
    temp=0.0
    min_monomer=0.0
    max_monomer=0.0
    current=0.0
    volt_array = myRingBuffer(16)
    success=True

    try:
        # Read all command
        sendBMSCommand(bms,'4E 57 00 13 00 00 00 00 06 03 00 00 00 00 00 00 68 00 00 01 29')

        time.sleep(.1)

        if bms.inWaiting() >= 4 :
            if bms.read(1).hex() == '4e' : # header byte 1
                if bms.read(1).hex() == '57' : # header byte 2
                    # next two bytes is the length of the data package, including the two length bytes
                    length = int.from_bytes(bms.read(2),byteorder='big')
                    length -= 2 # Remaining after length bytes

                    # Lets wait until all the data that should be there, really is present.
                    # If not, something went wrong. Flush and exit
                    available = bms.inWaiting()
                    if available != length :
                        time.sleep(0.1)
                        available = bms.inWaiting()
                        # if it's not here by now, exit
                        if available != length :
                            bms.reset_input_buffer()
                            raise Exception("Something went wrong reading the data...")

                    # Reconstruct the header and length field
                    b = bytearray.fromhex("4e57")
                    b += (length+2).to_bytes(2, byteorder='big')

                    # Read all the data
                    data = bytearray(bms.read(available))
                    # And re-attach the header (needed for CRC calculation)
                    data = b + data

                    # Calculate the CRC sum
                    crc_calc = sum(data[0:-4])
                    # Extract the CRC value from the data
                    crc_lo = struct.unpack_from('>H', data[-2:])[0]

                    # Exit if CRC doesn't match
                    if crc_calc != crc_lo :
                        bms.reset_input_buffer()
                        raise Exception("CRC Wrong")

                    # The actual data we need
                    data = data[11:length-19] # at location 0 we have 0x79


                    # The byte at location 1 is the length count for the cell data bytes
                    # Each cell has 3 bytes representing the voltage per cell in mV
                    bytecount = data[1]

                    # We can use this number to determine the total amount of cells we have
                    cellcount = int(bytecount/3)
                    print_debug("cellcount",cellcount)

                    # Voltages start at index 2, in groups of 3
                    volt_array = myRingBuffer(cellcount)
                    for i in range(cellcount) :
                        voltage = struct.unpack_from('>xH', data, i * 3 + 2)[0]/1000
                        volt_array.append(voltage)
                        valName  = "mode=\"cell"+str(i+1)+"_BMS\""
                        valName  = "{" + valName + "}"
                        dataStr  = f"JK_BMS{valName} {voltage}"
                        #print(dataStr, file=fileObj)
                        # print(dataStr)
                    print_debug (str(volt_array.get()),"")
                    max_monomer=volt_array.max()
                    min_monomer=volt_array.min()
                    print_debug("Min Monomer", min_monomer)
                    print_debug("Max Monomer", max_monomer)

                    # Temperatures are in the next nine bytes (MOSFET, Probe 1 and Probe 2), register id + two bytes each for data
                    # Anything over 100 is negative, so 110 == -10
                    temp_fet = struct.unpack_from('>H', data, bytecount + 3)[0]
                    if temp_fet > 100 :
                        temp_fet = -(temp_fet - 100)
                    temp_1 = struct.unpack_from('>H', data, bytecount + 6)[0]
                    if temp_1 > 100 :
                        temp_1 = -(temp_1 - 100)
                    temp_2 = struct.unpack_from('>H', data, bytecount + 9)[0]
                    if temp_2 > 100 :
                        temp_2 = -(temp_2 - 100)
                    temp=(temp_1+temp_2)/2
                    print_debug("temp",temp)

                    # For now we just show the average between the two probes in Grafana
                    valName  = "mode=\"temp_BMS\""
                    valName  = "{" + valName + "}"
                    dataStr  = f"JK_BMS{valName} {(temp_1+temp_2)/2}"
                    #print(dataStr, file=fileObj)
                    #print(dataStr)

                    # Battery voltage
                    voltage = struct.unpack_from('>H', data, bytecount + 12)[0]/100
                    print_debug ("Battery Voltage",voltage)

                    #c1=int(100*current)        # multiply by 100 to get rid of floating-point
                    #current=twos_comp(c1,16)/100   # create the twos complement and divide by 100 again
                    #print("current=",current)

                    #current = struct.unpack_from('>h', data, bytecount + 15)[0]/100
                    #print("current=",current)


                    current_msb = struct.unpack_from('>B', data, bytecount + 15)[0]
                    #print("current15B=",current_msb,hex(current_msb))
                    current_lsb = struct.unpack_from('>B', data, bytecount + 16)[0]
                    #print("current16B=",current_lsb,hex(current_lsb))
                    if (current_msb >= 128):
                       current=(current_msb-128)*256+current_lsb
                    else:
                       current=current_msb*(-256)+current_lsb
                    current=current/100
                    print_debug("corrected current: ",current)



                    # SOC/ Remaining capacity, %
                    unmodified_capacity = struct.unpack_from('>B', data, bytecount + 18)[0]
                    print_debug("Debug unmodified capacity", unmodified_capacity)
                    allow_larger_100_percent_soc = True
                    #allow_larger_100_percent_soc = False
                    if (unmodified_capacity >=99 and allow_larger_100_percent_soc):
                       capacity=unmodified_capacity-1
                    else:
                       capacity=unmodified_capacity
                    print_debug("final SOC", capacity)


        else:
           success=False

        bms.reset_input_buffer()

    except Exception as e :
        print(e)
        success=False
    #print("Success reading the BMS",success)
    r=[capacity,voltage,current,temp,min_monomer, max_monomer, current, success]
    q.put(r)
    return capacity,voltage,current,temp,min_monomer, max_monomer, current, success



if __name__ == "__main__":

   # JK BMS UART INIT
   ##################
   try:
      bms = serial.Serial('/dev/ttyUSB0')
      bms.baudrate = 115200
      bms.timeout  = 0.2
   except:
      print("BMS not found.")

   # query the BMS
   print("query the BMS")
   print ("USB Serial Adpater Setting: ",bms)
   q = multiprocessing.Queue()
   x = multiprocessing.Process(target=readBMS,args=(bms,q,))
   x.start()
   x.join()
   result=q.get()
   success=result[7]
   print ("Status reading the BMS: ",success)
   print ("return values:", result)


   #my_soc,my_volt,my_ampere,my_temp,min_volt, max_volt, current=readBMS()



