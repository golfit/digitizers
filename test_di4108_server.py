'''
This client tries to communicate setup information to "remotely" control a DI-4108.

T. Golfinopoulos, 7 September 2018
'''

from digitizer_models import DI4108_WRAPPER
import json
from io import StringIO
import socket
import time
import numpy
import matplotlib.pyplot as plt
import copy

WAIT_TIME=1

props=[]

for k in DI4108_WRAPPER.__dict__.keys() :
    if type(DI4108_WRAPPER.__dict__[k]) is property :
        print(k)
        props.append(k)
        
pulse_duration=0.5 #Length of pulse [s]
fs=10000 #Sampling frequency [Hz]
n_samps_post=int(pulse_duration/fs)

settings={'fs':fs,'v_range':1,'chans':8}
#Settings configure DI4108; init_settings contain possible additional information: n_samps_post,n_samps_pre,pulse_mode
init_settings=copy.deepcopy(settings)

init_settings['n_samps_post']=n_samps_post

io=StringIO()

json.dump(init_settings,io)

print(io.getvalue())

settings_string=json.dumps(init_settings)

print(settings_string)

settings_loaded=json.loads(settings_string)

init_command='<init>'+settings_string+'</init>'
trig_command='<trig_pulse>'
store_command='<store>'
query_length_command='<query_data_length>'
commands=[init_command,trig_command,query_length_command,store_command]
#commands=[trig_command,'<query_data_length>',store_command]
#commands=[store_command]
#commands=[trig_command]

print(init_settings)
print(settings_loaded)

#Try to instantiate object from settings through json cycle
my_di4108=DI4108_WRAPPER(**json.loads(json.dumps(settings)))
print('V_range={}'.format(my_di4108.v_range))

#Connect to server
host = '198.125.177.3' #'localhost'
port = 4220
server_addr=(host,port)

max_reads=1024

data_length=None

for command in commands :
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    #Send settings to server
    s.connect(server_addr)

    print(command.encode())
    
    try :
        s.sendall(bytes(command,'ascii')) #ASCII encoding seems important, rather than sendall('command'.encode())
        if command=='<store>' :
            #print('Intended length={}'.format(int(response)))
            response=s.recv(1024)
            s.settimeout(2)
            all_response=response
            for i in range(max_reads) :
                response=s.recv(1024)
                if len(response) == 0 :
                    break
                all_response+=response #Add response
            print("Length of response = {}".format(len(all_response)))
            if not data_length is None :
                print("Queried data length={}".format(data_length))
                assert(data_length==len(all_response))
        else :
            response = str(s.recv(1024), 'ascii')
            print("Received: {}".format(response))
        
        if command=='<query_data_length>' :
            data_length=int(response)
    finally :
        s.close()
    #s.send(''.encode())
    #s.shutdown(socket.SHUT_WR) #Stop writing

print(all_response[0:20])
response_bytes=DI4108_WRAPPER.convert_bytes_to_int(all_response)
print(response_bytes[0:10])

v=my_di4108.convert_data(DI4108_WRAPPER.convert_bytes_to_int(all_response))

t=numpy.linspace(0,pulse_duration-1/fs,len(v[0]))

for i in range(len(v)):
    if i>3 :
        t_offset=-0.25/fs
    else :
        t_offset=0
    plt.plot(t+t_offset,v[i])

plt.show()

