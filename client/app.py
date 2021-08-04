# -*- coding: utf-8 -*-

from kuraconnector import publish_data, run
from time import time, sleep
from math import sin, cos

data_interval = 0

def start(get_interval, params):
    global data_interval
    publish_data({"message": "Started with get_interval={:f}, parameters={:s}".format(get_interval, str(params))})
    data_interval = get_interval

def get(counter):
    global data_interval
    # Grab a measurement here
    t = counter*data_interval
    temperature = 20+sin(t*6.28/300)
    humidity = 50+10*cos(t*6.28/300)
    publish_data({
        "temperature": temperature,
        "humidity": humidity})

def stop():
    publish_data({"message": "Stopped"})


if __name__ == "__main__":    
    run(start_callback=start, get_callback=get, stop_callback=stop)


