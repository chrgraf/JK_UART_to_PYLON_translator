import serial
import binascii
import time

ser = serial.Serial()

def initSerial():
    global ser
    ser.baudrate = 115200
    ser.port = '/dev/ttyUSB1'
    #ser.timeout =0
    ser.stopbits = serial.STOPBITS_ONE
    ser.bytesize = 8
    ser.parity = serial.PARITY_NONE
    ser.rtscts = 0

def main():
    initSerial()
    global ser
    ser.open()
    while True:
        mHex = ser.read()
        if len(mHex)!= 0:
            print("get",binascii.hexlify(bytearray(mHex)))
        time.sleep(0.1)


if __name__ == "__main__":
    main()

