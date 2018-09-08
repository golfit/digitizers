'''
This module implements a server, initially intended to run on a Raspberry Pi remote processor connected to a single DATAQ DI-4108 digitizer, with extensability to larger numbers of digitizers and other processors with a Linux operating system.

T. Golfinopoulos, 7 Sept. 2018
'''

#See https://docs.python.org/3.4/library/socketserver.html

import socket
import threading
import socketserver
import time
from digitizer_models import DI4108_WRAPPER
import json

class AcqPorts:
    """server port constants
    Conventions from acq400 - d-tAcq software
    Used for general compatibility in d-tAcq environment."""
    TSTAT = 2235
    STREAM = 4210
    SITE0 = 4220
    SEGSW = 4250
    SEGSR = 4251
    GPGSTL= 4541
    GPGDUMP = 4543

    BOLO8_CAL = 45072
    DATA0 = 53000
    LIVETOP = 53998
    ONESHOT = 53999
    AWG_ONCE = 54201
    AWG_AUTOREARM = 54202
    MGTDRAM = 53990


class SF:
    """state constants
    Conventions from acq400 - d-tAcq software
    Used for general compatibility in d-tAcq environment."""
    STATE = 0
    PRE = 1
    POST = 2
    ELAPSED = 3
    DEMUX = 5

class STATE:
    """transient states
    Conventions from acq400 - d-tAcq software
    Used for general compatibility in d-tAcq environment."""
    IDLE = 0
    ARM = 1
    RUNPRE = 2
    RUNPOST = 3
    POPROCESS = 4
    CLEANUP = 5
    @staticmethod
    def str(st):
        if st==STATE.IDLE:
            return "IDLE"
        if st==STATE.ARM:
            return "ARM"
        if st==STATE.RUNPRE:
            return "RUNPRE"
        if st==STATE.RUNPOST:
            return "RUNPOST"
        if st==STATE.POPROCESS:
            return "POPROCESS"
        if st==STATE.CLEANUP:
            return "CLEANUP"
        return "UNDEF"


def debugging():
    import os
    return os.getenv("DEBUG_DEVICES")
        
class ThreadedTCPRequestHandler(socketserver.StreamRequestHandler):

    #def __init__(self,*arg,**kwargs):
    #    self.my_di4108=None #Additional 
    #    super(ThreadedTCPRequestHandler,self).__init__(*arg,**kwargs)
    #my_di4108=None
    my_di4108=DI4108_WRAPPER() #Use default settings

    def handle(self):
        #Use readline to read request until newline character is encountered
        data = str(self.request.recv(1024).strip(), 'ascii')
        #data = str(self.rfile.readline(), 'ascii')

        cur_thread = threading.current_thread()
        response = bytes("{}: {}".format(cur_thread.name, data), 'ascii')

        #data can be
        #1. a store rqeuest, "store"
        #2. a JSON-encoded dictionary of settings that can be
        #used as keyword arguments to __init__ of a DI4108_WRAPPER object
        #3. query asking for info output
        #4. a "start" command (soft trigger)
        #5. a "stop" command (soft close)
        
        
#        if data.lower()=='start' :
#            my_di4108.trig_data_pulse()
#        elif data.lower()=='stop' :
        
        #Parse, and remove any keys that are not keywords of DI4108
        all_keys=DI4108_WRAPPER.__dict__.keys()
        setting_keys=[]
        for k in all_keys :
            if type(DI4108_WRAPPER.__dict__[k]) is property :
                setting_keys.append(k)
        
        #Remove settings that are not properties of DI4108
        new_settings=json.loads(data)
        for k in new_settings.keys() :
            if not k in setting_keys :
                new_settings.pop(k)
        
        print(new_settings)
        
        try :        
            if ThreadedTCPRequestHandler.my_di4108 is None :
                #Digitizer object - to implement: multiple digitizer support, singleton
                ThreadedTCPRequestHandler.my_di4108=DI4108_WRAPPER(**new_settings)
            else : #Re-initialize device
                ThreadedTCPRequestHandler.my_di4108.__init__(**new_settings)
        except :
             print("Can't configure DI4108") 
             raise
        
        
        #Return data for debugging purposes
        self.request.sendall(response)
    
    def serve_forever(self,*argv,**kwargs):
        print("Serving")
        super().serve_forever(*argv,**kwargs)

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    def serve_forever(self,*argv,**kwargs):
        print("Serving")
        #super().serve_forever(*argv,**kwargs)
        super(ThreadedTCPServer,self).serve_forever(*argv,**kwargs)
    #pass

if __name__ == "__main__":
    # Use SITE0 Port - this appears to be the main port for the acq400 class devices for i/o
    HOST, PORT = "localhost", AcqPorts.SITE0

    server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)
    ip, port = server.server_address
    
    print("IP: {}".format(ip))
    print("PORT: {}".format(port))

    # Start a thread with the server -- that thread will then start one
    # more thread for each request
    server_thread = threading.Thread(target=server.serve_forever)
    # Exit the server thread when the main thread terminates
    #server_thread.daemon = True
    print("Ready to start")
    server_thread.start()
    print("DI4108 server loop running in thread:", server_thread.name)

    #server.shutdown()
    #server.server_close()
    #print("DI4108 server closing at {}!".format(time.asctime()))
