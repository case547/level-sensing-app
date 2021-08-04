# -*- coding: utf-8 -*-
#import numpy as np
from contextlib import redirect_stderr
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import sys
import json
import traceback

    
_running = False

def publish_data(data):
    parts = []
    for (k, v) in data.items():
        if isinstance(v, str):
            f_str = "\"{:s}\""
            v = escape_string(v)
        #elif isinstance(v, (int, np.int8, np.int16, np.int32, np.int64, np.uint8, np.uint16, np.uint32, np.uint64)):
        elif isinstance(v, int):
            f_str = "{:d}"
        #elif isinstance(v, (float, np.float16, np.float32, np.float64)):
        elif isinstance(v, float):
            f_str = "{:.15e}"
        else:
            continue
        parts.append(("{:s}="+f_str).format(k, v))
    print("DATA\t"+"\t".join(parts))
    
#TODO: Add a function to publish a status
#TODO: Sort out how exceptions from the callbacks can be shown properly.
    
def run(start_callback=None, get_callback=None, stop_callback=None):
    global _running
    with open('kuraconnector_error.log', 'w') as stderr, redirect_stderr(stderr):
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                cur_task = None
                while True:
                    if cur_task is not None and cur_task.done():
                        exception = cur_task.exception()
                        if exception is not None:
                            stderr.write("Exception: "+str(exception))
                    line = input()
                    (cmd, args) = parse_line(line)
                    
                    if cmd == "START":
                        _running = True
                        try:
                            stderr.write(args["PARAMS"])
                            params = json.loads(args["PARAMS"])
                        except (KeyError, ValueError):
                            params = {}
                        try:
                            get_interval = args["GETINT"]
                        except (KeyError, ValueError):
                            get_interval = 0
                        if cur_task is not None and cur_task.running():
                            continue
                        cur_task = executor.submit(start_callback, get_interval=get_interval, params=params)
                    elif cmd == "GET":
                        try:
                            counter = args["COUNT"]
                        except KeyError:
                            counter = 0
                        if cur_task is not None and cur_task.running():
                            continue
                        cur_task = executor.submit(get_callback, counter = counter)
                    elif cmd == "STOP":
                        _running = False
                        if cur_task is not None:
                            cancelled = cur_task.cancel()
                            if not cancelled:
                                try:
                                    cur_task.result(timeout=5)
                                except TimeoutError:
                                    sys.stderr.write("Ongoing task is taking too long. Shutting down anyway.")
                                    pass
                        stop_task = executor.submit(stop_callback)
                        try:
                            stop_task.result(timeout=5)
                        except TimeoutError:
                            sys.stderr.write("Shutdown task is taking too long. Shutting down anyway.")
                            pass
                        break
        except:
            traceback.print_exc()
            
                
def is_stopped():
    global _running
    return not _running

# def escape_string(s):
#     s = s.encode("unicode-escape").decode()
#     s = s.replace('"', '\\"')
#     return s
    

# def unescape_string(s):
#     s = s.replace('\\"', '"')
#     s = s.encode().decode("unicode-escape")
#     return s

def escape_string(s):
	return s.replace("\\", "\\\\") \
		.replace("\t", "\\t") \
		.replace("\b", "\\b") \
		.replace("\n", "\\n") \
		.replace("\r", "\\r") \
		.replace("\f", "\\f") \
		.replace("\'", "\\'") \
		.replace("\"", "\\\"")
	
	
def unescape_string(s):
	return s.replace("\\\"", "\"") \
		.replace("\\'", "\'") \
		.replace("\\t", "\t") \
		.replace("\\b", "\b") \
		.replace("\\n", "\n") \
        .replace("\\r", "\r") \
        .replace("\\f", "\f") \
        .replace("\\\\", "\\")

def parse_line(line):
    parts = line.split("\t")
    cmd = parts[0]
    args = {}
    for arg in parts[1:]:
        try:
            (key, value) = arg.split("=", 1)
            if value.startswith('"') and value.endswith('"'):
                value = unescape_string(value[1:-1])
            else:
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        continue
        except ValueError:
            continue
        args[key]=value
    return (cmd, args)
        
#TODO: log warnings, if incoming commands are malformed.