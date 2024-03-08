#!/usr/bin/python3

import random
import time

from paho.mqtt import client as mqtt_client


broker = '192.168.178.116'
port = 1883
# generate client ID with pub prefix randomly
client_id = f'python-mqtt-{random.randint(0, 1000)}'
username = ''
password = ''

def connect_mqtt():
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
        else:
            print("Failed to connect, return code %d\n", rc)

    client = mqtt_client.Client(client_id)
    client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.connect(broker, port)
    client.on_message=on_message #attach function to callback
    return client


def publish(client,topic,message):
        result = client.publish(topic, message)
        # result: [0, 1]
        status = result[0]
        #if status == 0:
        #    print(f"Send `{message}` to topic `{topic}`")
        #else:
        #    print(f"Failed to send message to topic {topic}")

def subscribe(client, topic):
    client.subscribe(client, topic)

def on_message(client, userdata, message):
    global meter
    decode=str(message.payload.decode("utf-8"))
    #print("message received " ,str(message.payload.decode("utf-8")))
    #print("message topic=",message.topic)
    #print("message qos=",message.qos)
    #print("message retain flag=",message.retain)
    meter.put(decode)

def run():
    client = connect_mqtt()
    client.loop_start()
    client.subscribe("solis/Battery_Power_W")
    #publish(client)


if __name__ == '__main__':
    run()

