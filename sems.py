#!/usr/bin/python3

#MIT License
# 
# Copyright (c) [2024] [christian graf, chr.graf@gmx.de]
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


# goal
# query the Sems-Portal via Python-Script
# - if token expired, aquire a new one
# - query Sems-Portal generator
# actually the script is only extracting Inverter Current and battery-Charging/Discharging Watt
# could be easily extended for get all


# https://curlconverter.com/python/
#curl --location 'https://www.semsportal.com/api/v1/Common/CrossLogin' \
#--header 'Content-Type: application/json' \
#--header 'Token: {"version":"v2.1.0","client":"ios","language":"en"}' \
#--data-raw '{"account":"<email>","pwd":"<password>"}'

#curl --location '<api>/v1/PowerStation/GetMonitorDetailByPowerstationId' \
#--header 'Content-Type: application/json' \
#--header 'Token:{"version":"v2.1.0","client":"ios","language":"en","timestamp":"<timestamp>","uid":"<uid>","token":"<token>"}' \
#--data '{"powerStationId":"<powerStationId>"}'

# sources
# https://github.com/yaleman/pygoodwe/tree/main
# https://github.com/AaronSaikovski/gogoodwe
# https://binodmx.medium.com/accessing-the-goodwe-sems-portal-api-a-comprehensive-guide-296e0431c285

import requests
from requests import Request, Session
import json
from datetime import datetime, timedelta
from urllib.parse import urljoin
import multiprocessing


# for username/credentials edit a file sems_config.py
# behn@rpi5:~/jk_venv $ cat sems_config.py
#     username = "<email-adress for sems-portal>"
#     pw = "<your password on the portal>
#     power_station_id = "<your ID>"
# you can obtain the ID this way:
#  login to sems-portal via browser and watch the URL:
#  https://www.semsportal.com/PowerStation/PowerStatusSnMin/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
# the last part in the url encoded as                       12345678-1234-1234-1234-123456789012 is your ID to enter in the power_station_id field

import sems_config

sems_url_query="v2/PowerStation/GetMonitorDetailByPowerstationId"

verbose=False
#verbose=True

def print_banner(t):
  print ("")
  print ("######################################")
  print ("# " + t);
  print ("######################################")


def get_token(base_url):
   if verbose:
     print_banner("Function: get_token")
     print ("url used:", base_url)
   headers = {
    'Content-Type': 'application/json',
    'Token': '{"version":"v2.1.0","client":"ios","language":"en"}',
   }

   json_data = {
     'account': sems_config.username,
     'pwd': sems_config.pw,
   }

   response = requests.post(base_url, headers=headers, json=json_data)

   
   y=json.loads(response.text)
   #print(json.dumps(y, indent = 4, sort_keys=True))
   y=json.loads(response.text)
   token=y["data"] ["token"]
   uid=y["data"] ["uid"]
   timestamp=y["data"] ["timestamp"]
   api=y["api"]
   if verbose:
      print("derived authentication credentials")
      print("----------------------------------")
      print("  Token    : ", token)
      print("  UID      : ", uid)
      print("  timestamp: ", timestamp)
      print("  api      : ", api)

   
   # derive expiry for the token
   currentDateAndTime = datetime.now()
   token_expiry= datetime.now() + timedelta(hours=1)
   expiry = token_expiry.strftime("%H:%M:%S")
   return(token,uid,timestamp,expiry,api)



##################################
# query power-id
##################################
def query_id(ts,api):
   if verbose:
      print_banner("query_id")
   headers = {
    'Content-Type': 'application/json',
    'Token': ts
}


   url=urljoin(api,"v2/PowerStationMonitor/QueryPowerStationMonitorForApp")
   response= requests.post(url, headers=headers)
   if verbose:
      print ("url used:", url)
      print (response)
      print (response.status_code)
   #y=json.loads(response.text)
   #print(json.dumps(y, indent = 4, sort_keys=True))
   return(y)

##################################
# query generator
##################################
def query_generator(ts,api):
   if verbose:
      print_banner("query_generator")
   headers = {
    'Content-Type': 'application/json',
    'Token': ts
   }
   json_data = {
    'powerStationId': sems_config.power_station_id
   }

   #url=urljoin(api,"v2/PowerStation/GetMonitorDetailByPowerstationId")
   url=urljoin(api,sems_url_query)
   r=Request('Post', url, headers=headers, json=json_data)
   prepped=r.prepare()
   s=Session()
   response = s.send(prepped)
   y=json.loads(response.text)
   if verbose:
      print ("url used:", url)
      print(prepped.url)
      print(prepped.headers)
      print ("response status code: ",response.status_code)
      #print(json.dumps(y, indent = 4, sort_keys=True))
   return (y,response.status_code)


##################################
# get_battery_power
##################################
def get_battery_power_from_json (y):
   if verbose:
      print_banner("get_battery_power")
   battery=(y["data"]["inverter"][0]["battery"]) 
   #print (y["data"]["inverter"][0]["d"] ["output_power"])
   x=battery.split("/")
   batt_power_a=x[1].replace("A","")    # ampere
   batt_power_w=x[2].replace("W","")    # watt
   bp_a=float(batt_power_a) * (-1)      # reversing power - + means we are charging
   bp_w=int(batt_power_w) * (-1)
   if verbose:
      print("Parsing the JSON-String to derive Battery : ", battery)
      #print ("x[1] x[2]: ", x[1], x[2])
      print (" - battery-Power[W], Battery_Power[A]",batt_power_a, batt_power_w)
      print ("Reversing the logic and multiplying the values with -1")
      print (" - battery-Power[W], Battery_Power[A]",bp_a, bp_w)
   return(bp_a, bp_w)



##################################
# create query string
##################################
def create_query_string(token, uid, timestamp):
   token_string_part='"version":"v2.1.0","client":"ios","language":"en","timestamp":"{}","uid":"{}","token":"{}"'.format(timestamp,uid,token)
   qs="{" + token_string_part + "}"
   return(qs)



##################################
# SEMS - all in one
##################################
def do_auth_and_query(token,uid,timestamp,expiry,api,sems_url_oauth,q_do_auth_and_query):
   success=False
   code = ""
   i=0
   bp_a=0
   bp_w=0
   while (code != "0" and i<=3):
      i=i+1
      # lets first create a Query String to obtain a valid token
      # crafting a valid Query-String was the difficult task of this script
      qs=create_query_string(token, uid, timestamp)
      # use the token string for authentication
      y,status=query_generator(qs,api)
      if verbose:
        print("Query-String used for generator Query: ",qs)
      # in case of initial run or expired token
      code=y["code"]
      if (code == "0"):
         success=True
         if verbose:
            print(">>>Query generator was successful")
         bp_a, bp_w=get_battery_power_from_json(y)
         r=[token,uid,timestamp,expiry,api,bp_a, bp_w,success]
         q_do_auth_and_query.put(r)
      else:
         # auth-failed, token expired,.. - lets get a fresh token
         #print("code:", code)
         if verbose:
            print(">>>Query generator failed")
            print(">>>Lets aquire a new token and retry")
         token,uid,timestamp,expiry,api=get_token(sems_url_oauth)

   return (token,uid,timestamp,expiry,api,bp_a, bp_w,success)


 
##################################
# MAIN
##################################
def main():
   token=""
   uid=""
   timestamp=""
   expiry=0.0
   sems_url_oauth="https://www.semsportal.com/api/v2/Common/CrossLogin"
   api="https://eu.semsportal.com/api/"  # will be overwritten as part of the get_token
   success=False
   q_do_auth_and_query = multiprocessing.Queue()

   # the one ond only call needed. this routine tries to re-use existing token.
   # if token not good, trying to aquire a new one and use it for subsequent call
   # fresh token is stored in variable "token"
   #token,uid,timestamp,expiry,api,bp_a,bp_w,success= do_auth_and_query(token,uid,timestamp,expiry,api,sems_url_oauth)
   
   mp_do_auth_and_query = multiprocessing.Process(target=do_auth_and_query,args=(token,uid,timestamp,expiry,api,sems_url_oauth,q_do_auth_and_query))
   mp_do_auth_and_query.start()
   mp_do_auth_and_query.join()
   while (not q_do_auth_and_query.empty()):
    q=q_do_auth_and_query.get()
    if verbose:
      print("q: ", q)
    token=q[0]
    uid=q[1]
    timestamp=q[2]
    expiry=q[3]
    api=q[4]
    bp_a=q[5]
    bp_w=q[6]
    success=q[7]
    if (success):
        print("Success")
    else:
        print("Failure")

  
if __name__ == "__main__":
    main()


