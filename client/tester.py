# -*- coding: utf-8 -*-

import subprocess
import logging
import threading
import time
import json
from kuraconnector import parse_line


PY_INTERPRETER = "python3"

def write_and_flush(stdin, string):
    stdin.write((string+"\n").encode())
    stdin.flush()

def send_commands(stdin, num_gets, get_interval_s, params, interrupt, complete):
    try:
        logging.info("Sending START")
        write_and_flush(stdin, "START\tGETINT={:f}\tPARAMS=\"{:s}\"".format(get_interval_s, params))
        for i in range(num_gets):
            logging.info(f"Sending GET #{i}")   
            write_and_flush(stdin, "GET\tCOUNT={:d}".format(i))
            if interrupt.wait(get_interval_s):
                logging.info("Thread received interrupt")
                break
        logging.info("Sending STOP")
        write_and_flush(stdin, "STOP")
        complete[0] = True
    except OSError:
        # Process probably died
        pass
    
def receive_data(stdout):
    while True:
        if stdout.closed:
            break
        line = stdout.readline().decode()
        if not line:
            break
        (keyword, payload) = parse_line(line)
        if keyword == "DATA":
            logging.info("Received: {:s}".format(str(payload)))
        else:
            logging.warning("Received invalid message {:s}".format(line))
        
def run(app_fn, get_interval_s, num_gets, params=None):
    logging.basicConfig(format="[%(asctime)s] %(levelname)s: %(message)s", level=logging.DEBUG)

    runtime_s = get_interval_s * num_gets
    
    if params is None:
        params = ""
    else:
        params = json.dumps(params)
    
    logging.info(f"Starting application {app_fn}.")
    logging.info(f"Requesting {num_gets} values at an interval of {get_interval_s}s. Total estimated runtime: {runtime_s}s")
    
    process = subprocess.Popen([PY_INTERPRETER, app_fn],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    
    
    interrupt = threading.Event()
    send_complete = [False]
    
    send_thread = threading.Thread(target=send_commands, args=[process.stdin, num_gets, get_interval_s, params, interrupt, send_complete])
    receive_thread = threading.Thread(target=receive_data, args=[process.stdout])
    
    send_thread.start()
    
    receive_thread.start()
    
    try:
        for i in range(int(runtime_s + 10)):
            send_thread.join(1)
    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        interrupt.set()
        send_thread.join(10)
        
    if not send_complete[0]:
        logging.warning("Not all commands could be sent")
    
    if send_thread.is_alive():
        logging.error("Command sending thread did not terminate on time")
    try:
        rc = process.wait(30)
    except subprocess.TimeoutExpired:
        logging.warn("Process has not terminated within 30s after STOP command. Terminating.")
        process.terminate()
        try:
            rc = process.wait(5)
        except subprocess.TimeoutExpired:
            logging.warn("Process has still not terminated. Killing.")
            process.kill()
            try:
                rc = process.wait(5)
            except subprocess.TimeoutExpired:
                logging.warn("Process has still not terminated. Whatever. We're off.")
                
    receive_thread.join(1)
    if receive_thread.is_alive():
        logging.error("The receive thread shoule be done by now, but somehow it's not.")
    
    if rc:
        logging.warning(f"The application process exited with code {rc}.")
    else:
        logging.info(f"The application process exited normally")
        

#TODO: Report exceptions in application
    