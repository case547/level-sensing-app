# -*- coding: utf-8 -*-

from kuraconnector import publish_data, run
from time import time, sleep
from math import sin, cos

import warnings
from copy import copy
from enum import Enum

import numpy as np

import exptool as et

data_interval = 0
PEAK_MERGE_LIMIT_M = 0.005

def start(get_interval, params):
    global data_interval
    publish_data({"message": "Started with get_interval={:f}, parameters={:s}".format(get_interval, str(params))})
    data_interval = get_interval

    client = et.SocketClient(json_as_py['ip_a']) # Raspberry Pi uses socket client
    
    config = et.configs.EnvelopeServiceConfig() # picking envelope service

    sensor_config = get_sensor_config(config)
    sensor_config.sensor = [1]

    processing_config = get_processing_config()
    for k, v in json_as_py.items():
        if hasattr(processing_config, k):
            try:
                setattr(processing_config, k, eval(v))
            except:
                setattr(processing_config, k, v)

    # Set up session with created config
    session_info = client.setup_session(sensor_config) # also calls connect()
    print("Session info:\n", session_info, "\n")

    client.start_session() # call will block until sensor confirms its start

    processor = Processor(sensor_config, processing_config, session_info)

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


