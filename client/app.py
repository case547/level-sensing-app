# -*- coding: utf-8 -*-

from kuraconnector import publish_data, run

import numpy as np

import exptool as et

from processor import Processor, ProcessingConfiguration as get_processing_config

data_interval = 0

def start(get_interval, params):
    global data_interval
    global client
    global processor
    global nbr_average
    publish_data({"message": "Started with get_interval={:f}, parameters={:s}".format(get_interval, str(params))})
    data_interval = get_interval

    nbr_average = params["nbr_average"]

    client = et.SocketClient(params['ip_a']) # Raspberry Pi uses socket client
    
    config = et.configs.EnvelopeServiceConfig() # use envelope service

    sensor_config = get_sensor_config(config, params)
    sensor_config.sensor = [1]

    processing_config = get_processing_config()
    for k, v in params.items():
        if hasattr(processing_config, k):
            try:
                setattr(processing_config, k, eval(v))
            except:
                setattr(processing_config, k, v)

    # Set up session with created config
    session_info = client.setup_session(sensor_config) # also calls connect()

    client.start_session() # call will block until sensor confirms its start

    processor = Processor(sensor_config, processing_config, session_info)

def get(counter):
    global data_interval
    # Grab a measurement here - averaged over 5 sweeps for noise reduction
    for _ in range(nbr_average):
        info, sweep = client.get_next()
        plot_data = processor.process(sweep, info)

        if plot_data["found_peaks"]:
            peaks = np.take(processor.r, plot_data["found_peaks"]) * 100.0
            publish_data({"distance": peaks[0]})

def stop():
    publish_data({"message": "Stopped"})
    client.disconnect()


def get_sensor_config(config, params):
    """Define default sensor config."""
    for k, v in params.items():
        if hasattr(config, k):
            try:
                setattr(config, k, eval(v))
            except:
                setattr(config, k, v)

    return config


if __name__ == "__main__":    
    run(start_callback=start, get_callback=get, stop_callback=stop)


