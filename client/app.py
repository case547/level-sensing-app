import logging
import os
import subprocess
import time

import numpy as np

import acconeer.exptool as et
from kuraconnector import publish_data, publish_status, run
from processing import Processor, ProcessingConfiguration as get_processing_config

app_get_interval = 0
app_params = {}
DEVICE_NAME = None

# START event handler
#
# Performs set-up. In applications that push data rather than having it requested via the GET event,
# this handler can be used to do all the work, but kuraconnector.is_stopped() has to be called regularly
# to determine if a STOP event occured, i.e. the bundle was deactivated/restarted in the meantime. 
# STOP events must be responded to within 10s.
#
# get_interval - float: interval at which data will be requested via the get function in seconds
# params - dict: dictionary of parameters provided through kura bundle configuration

def start(get_interval, params):
    global app_get_interval, app_params
    global client, processor, nbr_avg, DEVICE_NAME
    
    logging.basicConfig(filename='sessions.log', level=logging.INFO)
    
    # Check if the streaming server has already been launched
    query = subprocess.run('ps aux | grep acc_streaming', stdout=subprocess.PIPE, shell=True)
    
    if "acconeer_rpi_xc112/utils/acc_streaming_server" not in query.stdout.decode('utf-8'):
        os.system("../streamer.sh &")
        logging.info(f"{time.ctime()[4::]}. Streaming server activated")
    else:
        logging.info(f"{time.ctime()[4::]}. Streaming server already activated")
    
    DEVICE_NAME = params.get("device_name", "unknown")

    publish_status({"message": f"Started with get_interval={get_interval:f}, parameters={str(params):s}"}, DEVICE_NAME)
    app_get_interval = get_interval
    app_params = params

    client = et.SocketClient(params["ip_a"]) # Raspberry Pi uses socket client
    
    config = et.configs.EnvelopeServiceConfig()
    sensor_config = get_sensor_config(config, params)
    sensor_config.running_average_factor = 0    # use averaging in detector instead

    processing_config = get_processing_config()
    for k, v in params.items():
        if hasattr(processing_config, k):
            try:
                setattr(processing_config, k, eval(v))
            except:
                setattr(processing_config, k, v)
    nbr_avg = processing_config.nbr_average

    # Set up session with created config
    connected = False
    tic = time.time()
    
    while not connected:
        try:
            session_info = client.setup_session(sensor_config) # also calls connect()
            connected = True
            toc = time.time()
            publish_status({"message": f"Connected afer {toc-tic:.3f}s"}, DEVICE_NAME)
        except:
            time.sleep(1)
    
    logging.info(f"{time.ctime()[4::]}. Session info: {session_info}")

    client.start_session() # call will block until sensor confirms its start

    processor = Processor(sensor_config, processing_config, session_info)

# GET event handler
#
# counter - int: a running number enumerating data sample requests.

def get(counter):
    global app_get_interval, app_params

    infos = []

    # Grab a measurement here - averaged over nbr_avg sweeps for noise reduction
    for _ in range(round(nbr_avg)):
        info, sweep = client.get_next()
        infos += [info]
        plot_data = processor.process(sweep, info)

        # found_peaks is either None or list of indexes sorted by the chosen peak sorting method
        if plot_data["found_peaks"]:
            peaks = np.take(processor.r, plot_data["found_peaks"]) * 100.0
            # processor.r is the sweep's range depths, created by
            # numpy.linspace(range_start, range_end, num_depths)
            # where num_depths = Processor.session_info["data_length"]
            
            publish_data({"distance": peaks[0]}, DEVICE_NAME)
            logging.info(f"{time.ctime()[4:-5]}. Get {counter}: {peaks[0]} cm")

    saturated = any([i.get("data_saturated", False) for i in infos])
    data_quality_warning = any([j.get("data_quality_warning", False) for j in infos])

    # Might want to reduce how large the warning values are. Maybe use a
    # binary flag rather than strings?

    if data_quality_warning:
        publish_status({"warning": "Bad data quality, restart service"}, DEVICE_NAME)
        logging.warning("Bad data quality, restart service!")
    elif saturated:
        publish_status({"warning": "Data saturated, reduce gain"}, DEVICE_NAME)
        logging.warning("Data saturated, reduce gain!")

# STOP event handler
#
# Perform clean-up. 
# STOP events must be handled within 10 s, after which the process will be terminated. 
# Note that this handler is executed in the same thread as the START and the GET handler
# and therefore the call to this handler may already be delayed.

def stop():
    client.disconnect()
    publish_status({"message": "Stopped"}, DEVICE_NAME)


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
