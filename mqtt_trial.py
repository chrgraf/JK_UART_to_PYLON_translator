#!/usr/bin/python3
###############################################################################################

import paho.mqtt.client as mqtt #import the client1
import time
import json
from queue import Queue

def on_message(client, userdata, message):
    global q
    decode=str(message.payload.decode("utf-8"))
    print("message received " ,decode)
    q.put(decode)
    print ("size", q.qsize())
    # print("message topic=",message.topic)
    # print("message qos=",message.qos)
    # print("message retain flag=",message.retain)
    #y=json.loads(decode)
    #print(json.dumps(y, indent = 4, sort_keys=True))

    #pconsume=y['pconsume']
    #print("pconsume", pconsume)
    #psupply=y['psupply']
    #print("psupply", psupply)
    
    
q=Queue()
broker_address="192.168.178.116"
print("creating new instance")
client = mqtt.Client("P1") #create new instance
print("connecting to broker")
client.connect(broker_address) #connect to broker
client.on_message=on_message #attach function to callback
print("Subscribing to topic","SMA-EM/status/1900203015")
client.subscribe("SMA-EM/status/1900203015")
client.loop_start() #start the loop
#client.loop_forever()



print("Publishing message to topic","house/bulbs/bulb1")
client.publish("house/bulbs/bulb1","OFF")
while (True):
 print ("new run")
 print("========")
 print ("size_main", q.qsize())
 while not q.empty():
    my_message=q.get()
    if my_message is None:
        continue
    y=json.loads(my_message)
    pconsume=y['pconsume']
    print("pconsume", pconsume)
    psupply=y['psupply']
    print("psupply", psupply)
    #time.sleep(1) # wait
    


