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

from html.parser import HTMLParser#For decoding commands


def debugging():
    import os
    return os.getenv("DEBUG_DEVICES")
    
# create a subclass and override the handler methods
class MyHTMLParser(HTMLParser):
    def __init__(self,*args,**kwargs):
        self.start_tags=[]
        self.attr=[]
        self.data=[]
        self.end_tags=[]
        self.abs_pos=0
        super(MyHTMLParser,self).__init__(*args,**kwargs)
    
    def feed(self,data):
        '''
        Override feed method so that tags, attributes, and data populate lists, which are then
        returned at end of close.
        
        USAGE:
            (start_tags_list,attr_list,data_list,end_tags_list)=my_parser.feed(data)
        
        Output is a tuple of lists of tuples.
        The latter grouping of tuples consists of an HTML item and its absolute position in the ordering of items,
            pair of, e.g. [(title,1),(body,3),...]
        attr_list is a list of attribute lists.
        '''
        #Empty tag lists for filling
        self.start_tags=[]
        self.attr=[]
        self.data=[]
        self.end_tags=[]
        self.abs_pos=0 #Zero position counter
        super(MyHTMLParser,self).feed(data)
        return (self.start_tags,self.attr,self.data,self.end_tags)

    def handle_starttag(self, tag, attrs):
        attr_list=[]
        if debugging():
            print("Encountered a start tag:", tag)
            for attr in attrs :
                if debugging():
                    print(attr)            
                attr_list+=attr #List of attributes
        self.attr+=(attr_list,self.abs_pos)
        self.start_tags+=[(tag,self.abs_pos)]
        self.abs_pos+=1

    def handle_endtag(self, tag):
        if debugging():
            print("Encountered an end tag :", tag)
        self.end_tags+=[(tag,self.abs_pos)]
        self.abs_pos+=1

    def handle_data(self, data):
        if debugging():
            print("Encountered some data  :", data)
        self.data+=[(data,self.abs_pos)]
        self.abs_pos+=1
    
    def get_start_tags(self):
        return self.start_tags
    
    def get_attr(self):
        return self.attr
    
    def get_end_tags(self):
        return self.end_tags
    
    def get_data(self):
        return self.data

# instantiate the parser and fed it some HTML

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
    st=-1 #Initialize state as undefined
    #Maintain a dictionary of states for multiple devices based on port
    states={AcqPorts.SITE0:-1}
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

class STORE_DATA:
    '''
    Store data globally - shrug - might also use file-based storage for non-volatility
    but take penalty on i/o
    '''
    data={AcqPorts.SITE0:None}
    elapsed_time={AcqPorts.SITE0:None}
        
class ThreadedTCPRequestHandler(socketserver.StreamRequestHandler):

    def __init__(self,*arg,**kwargs):
        if debugging():
            print("Initing ThreadedTCPRequestHandler")
        #    self.my_di4108=None #Additional 
        this_port=AcqPorts.SITE0 #For now, keep constant port - eventually, figure out how to parse
        self.parser=MyHTMLParser() #Try not to instantiate this every time....
        self._protocol_dict={'init':self.handle_init,\
                            'trig_pulse':self.handle_trig_pulse,\
                            'store':self.handle_store,\
                            'get_settings':self.handle_get_settings,\
                            'query_data_length':self.handle_query_data_length}
                            #'start_stream':None,'stop':None,'n_samps_pre':None,'n_samps_post':None,\
                            #'test':None,'get_seg':None]
        self.store_mode='pulse' #Alternative is "stream"
        self.n_samps_pre=0
        self.n_samps_post=1E4
        self.pulse_duration=1.0 #Default pulse length [s]
        #self.data=[] #Array for storing pulse data
        #self.elapsed_time=0 #Time elapsed during data pulse [s]
        self.settings_file_name='settings_{}.json'.format(this_port)
        self.data_file_name='last_data_{}.bin'.format(this_port)
        self.elapsed_time_file_name='last_pulse_elapsed_time_{}.txt'.format(this_port)

        if STATE.str(STATE.states[this_port])=='UNDEF': #If state is not defined, use default settings and put in idle
            try :
                #Put initial settings into file
                f=open(self.settings_file_name,'x')
                f.write(self.settings_to_json())
                f.close()

                STATE.states[this_port]=STATE.ARM #Armed, since ready for trigger
            except :
                if debugging():
                    print("Can't create new settings file - may exist already - try to open and use")
        
        '''
        #Settings persist in class variable, my_di4108, which is non-extensible - could become a dictionary
        #with port number as key.  Else read each time from json, whose name contains port.
        #But still rely on persistence of my_di4108 class variable to get data.
        try :
            #Try to load existing settings
            f=open(self.settings_file_name,'r')
            current_settings=f.read(ThreadedTCPRequestHandler.max_size)
            self.handle_init(current_settings)
            if debugging():
                print("Opened settings file - current settings: {}".format(current_settings))
        except :
            if debugging():
                print("Can't open settings file - may exist already, or may have permissions error, etc.")
        '''
        
        if debugging():
            print("STATE="+str(STATE.states[this_port]))
        
        #Read settings from json, since this init is run on every new request....
        self.reinitialize()
        
        #This really has to be the last thing in the __init__ method of the subclass; it seems to
        #run handle on its own.  And so any initializations have to be applied before this.
        super(ThreadedTCPRequestHandler,self).__init__(*arg,**kwargs)
        
    #my_di4108=None
    my_di4108=DI4108_WRAPPER() #Use default settings
    buffer_size=1024
    max_size=16*buffer_size
    MAX_FILE_SIZE=1024*1024*1024 #1 GB=maximum file size

    def handle(self):
        '''
        data = str(self.request.recv(1024), 'ascii')
        cur_thread = threading.current_thread()
        response = bytes("{}: {}".format(cur_thread.name, data), 'ascii')
        print(response)
        self.request.sendall(response)
        self.request.close()
    
        '''
        #Use recv - loop until transmission is complete and socket returns empty
        this_data = str(self.request.recv(ThreadedTCPRequestHandler.buffer_size), 'ascii')
        data=this_data
        #while len(this_data) > 0 and len(data)<ThreadedTCPRequestHandler.max_size :
        #    this_data = str(self.request.recv(ThreadedTCPRequestHandler.buffer_size).strip(), 'ascii')
        #    data+=this_data
        #Use readline to read request until newline character is encountered
        #data = str(self.rfile.readline(), 'ascii')

        #Get thread
        cur_thread = threading.current_thread()
        response = bytes("{}: {}".format(cur_thread.name, data), 'ascii') #Convert to bytes format first
        
        #Parse data
        #data can be
        #1. a store rqeuest, "store"
        #2. a JSON-encoded dictionary of settings that can be
        #used as keyword arguments to __init__ of a DI4108_WRAPPER object
        #3. query asking for info output
        #4. a "start" command (soft trigger)
        #5. a "stop" command (soft close)
        try :
            (start_tags,attr,content,end_tags)=self.parser.feed(data)
            
            start_tag_pos=[t[1] for t in start_tags]
            end_tag_pos=[t[1] for t in end_tags]
            content_pos=[c[1] for c in content]
            
            content_tags=[]
            
            #Traverser through start_tags.
            #If a start tag is followed by content, and a matching
            #end tag, pass this as an argument to function.
            #Else, just run without argument.
            for start_tag in start_tags :
                #Recall that tags are stored as tuples, with first element the string,
                #and second the absolute position in the transmission
                if debugging():
                    print(start_tag)
                    print(self._protocol_dict.keys())
                    print(start_tags)
                    print(content)
                    print(end_tags)
                if start_tag[0] in self._protocol_dict.keys() :
                    if (start_tag[1]+1) in content_pos and (start_tag[1]+2) in end_tag_pos :
                        if end_tags[end_tag_pos.index(start_tag[1]+2)][0]==start_tag[0] :
                            #Call with content as argument
                            self._protocol_dict[start_tag[0]](content[content_pos.index(start_tag[1]+1)][0])
                    else :
                        self._protocol_dict[start_tag[0]]()
        except:
            print("Error - can't handle "+data)
            raise
            
        #Return data for debugging purposes
        if debugging():
            print('Done - ready to send shutdown message')
        #self.request.sendall(response)
        #self.request.sendall(''.encode()) #Send empty to close
        self.request.shutdown(socket.SHUT_RDWR)
        self.request.close()
        if debugging():    
            print('Done handling request')
        
    
    def handle_trig_pulse(self):
        '''
        On a <trig_pulse> command, perform soft-trigger of digitizer
        and record data per pulse duration in settings.
        '''
        if debugging():
            print('Received trigger request - about to perform soft trigger, pulse duration={}...'.format(self.pulse_duration))
        
        this_port=AcqPorts.SITE0
        
        STATE.states[this_port]=STATE.RUNPOST
        
        #(self.data,self.elapsed_time)=ThreadedTCPRequestHandler.my_di4108.trig_data_pulse(self.pulse_duration)
        (data,elapsed_time,bytes_data)=ThreadedTCPRequestHandler.my_di4108.trig_data_pulse(self.pulse_duration)
        
        STATE.states[this_port]=STATE.POPROCESS
        #f=open(self.data_file_name,'w')
        #f.write(bytes(data)) #Write data as bytes
        #f.close()
        #f=open(self.elapsed_time_file_name,'w')
        #f.write(elapsed_time) #Write data as text
        #f.close()
        STORE_DATA.data[this_port]=bytes_data
        STORE_DATA.elapsed_time[this_port]=elapsed_time
        if debugging():
            print('Pulse completed and data recorded - elapsed time={} s, {} elements recorded'.format(elapsed_time,len(data)))
        
    
    def handle_store(self):
        '''
        Return data obtained from recent pulse.  Send through socket as bytes array.
        Except for digital input data, data are stored as twos-complement signed integers.
        Note that ordering of data - the order of the analog channels, the counter, etc. - depends
        on the setup of the device.  The best way to convert the data is via the di4108 digitizer model
        "convert_data" method.  You can synchronize device settings by using the "<get_settings>" command
        to pull the current on-board settings.
        
        T. Golfinopoulos, 12 Sept. 2018
        '''
        
        this_port=AcqPorts.SITE0
        
        if debugging():
            print("Received store request - about to send data, {} elements...".format(len(STORE_DATA.data[this_port])))
        #time.sleep(3)
        
        #self.request.sendall(bytes(self.data))
        #Read data from file
        #f=open(self.data_file_name)
        #data=f.read(ThreadedTCPRequestHandler.MAX_FILE_SIZE)
        #f.close()
        #self.request.sendall(bytes(data))
        #print(STORE_DATA.data[this_port])
        self.request.sendall(bytes(STORE_DATA.data[this_port]))
        
        if debugging():
            print("...sent stored data")
    
    def handle_query_data_length(self) :
        '''
        Send length of last data read (number of bytes) to requester.
        
        T. Golfinopoulos, 12 Sept. 2018
        '''
        this_port=AcqPorts.SITE0
        
        if debugging():
            print("Received query_data_length request...")
        data_length=len(STORE_DATA.data[this_port])
        #data_length_bytes=data_length.to_bytes((data_length.bit_length()+7)//8,'big')
        #self.request.sendall(data_length_bytes) #// = integer divide
        self.request.sendall(bytes(str(data_length),'ascii'))
        
        if debugging():
            print("...sent data length")
            
    def handle_get_settings(self):
        '''
        Send current settings as encoded json file to requester.
        
        T. Golfinopoulos, 12 Sept. 2018
        '''
        if debugging():
            print("Received get_settings request - about to send current settings as json file...")
        
        #current_settings_json_string=self.settings_to_json()
        f=open(self.settings_file_name,'r') #Read from file
        current_settings=f.read(ThreadedTCPRequestHandler.max_size)
        f.close()
        self.request.sendall(bytes(current_settings_json_string,'ascii'))
        
        if debugging():
            print("Sent settings\n{}".format(current_settings_json_string))
    
    def config_from_json_string(self,settings_json):
        '''
        my_server.config_from_json_string(my_json_string)
        
        Read json string and apply settings to instance of server.
        
        returns dictionary of new settings.
        
        T. Golfinopoulos, 23 Oct. 2018
        '''
        #Parse, and remove any keys that are not keywords of DI4108
        all_keys=DI4108_WRAPPER.__dict__.keys()
        setting_keys=[]
        for k in all_keys :
            if type(DI4108_WRAPPER.__dict__[k]) is property :
                setting_keys.append(k)
        
        if debugging():
            print("Setting keys:")
            print(setting_keys)
        #Decode transmitted setting
        new_settings=json.loads(settings_json)
        
        #These settings do not configure the DI4108 object        
        if 'store_mode' in new_settings.keys() :
            self.store_mode=new_settings['store_mode']
        
        if 'n_samps_pre' in new_settings.keys() :
            self.n_samps_pre=new_settings['n_samps_pre']
        
        if 'n_samps_post' in new_settings.keys() :
            self.n_samps_post=new_settings['n_samps_post']

        #Calculate new post-trigger pulse length based on number of samples and sampling frequency
        self.pulse_duration=self.n_samps_post/ThreadedTCPRequestHandler.my_di4108.fs
        if debugging():
            print("Pulse duration: {} s".format(self.pulse_duration))

        if debugging():
            print("New settings: {}".format(new_settings))
        
        #Remove settings that are not properties of DI4108
        #Do this with a list of tuples as an intermediate set,
        #since dictionaries are immutable in iteration
        prop_pairs=[]
        for k in new_settings.keys() :
            if k in setting_keys :
                prop_pairs.append((k,new_settings[k]))
        
        new_settings=dict(prop_pairs)
        
        if debugging():
            print("New settings:")
            print(new_settings)
        
        return new_settings

    def reinitialize(self):
        '''
        my_server.reinitialize()
        
        Read json settings file and re-apply settings - for threaded servers, this seems to be necessary.
        
        Returns dictionary of settings.
        
        T. Golfinopoulos, 23 Oct. 2018
        '''
        f=open(self.settings_file_name,'r') #Read from file
        current_settings_json=f.read(ThreadedTCPRequestHandler.max_size)
        f.close()

        return self.config_from_json_string(current_settings_json)
        
    def handle_init(self,settings_json):
        if debugging():
            print("Received init request - about to initialize device...")
        
        new_settings=self.config_from_json_string(settings_json)
        
        try :        
            if ThreadedTCPRequestHandler.my_di4108 is None :
                #Digitizer object - to implement: multiple digitizer support, singleton
                ThreadedTCPRequestHandler.my_di4108=DI4108_WRAPPER(**new_settings)
            else : #Re-initialize device
                ThreadedTCPRequestHandler.my_di4108.__init__(**new_settings)
        except :
             print("Can't configure DI4108") 
             raise
             
        #Write current settings to file
        f=open(self.settings_file_name,'w')
        f.write(self.settings_to_json())
        f.close()
        
        if debugging():
            print("Initialization complete!")
             
    def settings_to_json(self):
        #all_keys=ThreadedTCPRequestHandler.my_di4108.__dict__.keys() #DI4108_WRAPPER.__dict__.keys()
        all_keys=DI4108_WRAPPER.__dict__.keys()
        if debugging():
            print("All keys:")
            print(all_keys)
            print("Instance keys")
            print(ThreadedTCPRequestHandler.my_di4108.__dict__.keys())
        settings={}
        for k in all_keys :
            #if type(ThreadedTCPRequestHandler.my_di4108.__dict__[k]) is property :
            if type(DI4108_WRAPPER.__dict__[k]) is property :
                settings[k]=ThreadedTCPRequestHandler.my_di4108.__dict__['_'+k]
        
        #Add settings that are not part of di4108 object
        #Add these settings to di4108 object
        settings['store_mode']=self.store_mode
        settings['n_samps_pre']=self.n_samps_pre
        settings['n_samps_post']=self.n_samps_post
        
        if debugging():
            print("Settings:")
            print(settings)
        return json.dumps(settings,sort_keys=True)
        
    def serve_forever(self,*argv,**kwargs):
        print("Serving")
        #Default configuration regarding whether to store data in one complete pulse, or to stream data as it comes
        self._n_samps_pre=0
        self._n_sampes_post=10000
        self._store_mode='pulse'
        self.parser = MyHTMLParser()
        super().serve_forever(*argv,**kwargs)
    
    @property
    def  n_samps_pre(self):
        return self._n_samps_pre
    
    @n_samps_pre.setter
    def n_samps_pre(self,n_samps_pre):
        self._n_samps_pre=n_samps_pre
    
    @property
    def  n_samps_post(self):
        return self._n_samps_post
    
    @n_samps_post.setter
    def n_samps_post(self,n_samps_post):
        self._n_samps_post=n_samps_post
    
    @property
    def store_mode(self):
        return self._store_mode
    
    @store_mode.setter
    def store_mode(self,store_mode):
        self._store_mode=store_mode

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    def serve_forever(self,*argv,**kwargs):
        print("Serving")
        #super().serve_forever(*argv,**kwargs)
        super(ThreadedTCPServer,self).serve_forever(*argv,**kwargs)
    #pass

if __name__ == "__main__":
    # Use SITE0 Port - this appears to be the main port for the acq400 class devices for i/o
    #HOST, PORT = "198.125.177.3", AcqPorts.SITE0
    HOST, PORT = "localhost", AcqPorts.SITE0
    
    host_addr=(HOST,PORT)
    ThreadedTCPServer.allow_reuse_address = True
    server = ThreadedTCPServer(host_addr, ThreadedTCPRequestHandler)
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
    
'''
            for c in content :
                try :
                    (start_tag_ind,end_tag_ind)=(start_tag_pos.index(c[1]-1),end_tag_pos.inex(c[1]+1))
                    #Content must be wrapped by same type of tag
                    assert(start_tags[start_tag_ind]==end_tags[end_tag_ind]
                    content_tags+=start_tags[start_tag_ind][0]
                    
                    if content_tags[-1].lower()=='init' :
                        #Init command received - should have gotten json-encoded setup
                        #Pass to handle_init function
                        self.handle_init(c)
                    
                except ValueError :
                    print("Possibly malformed command - can't find tags of {}".format(c[0]))
                except AssertionError :
                    print("Possibly malformed command - surrounding tags of {} don't match - they are {} and {}".format(c[0], start_tags[start_tag_ind],end_tags[end_tag_ind]))
                
'''
