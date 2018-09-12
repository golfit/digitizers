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

WAIT_TIME=5

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
#commands=[init_command,trig_command,store_command]
commands=[trig_command,store_command]

print(init_settings)
print(settings_loaded)

#Try to instantiate object from settings through json cycle
my_di4108=DI4108_WRAPPER(**json.loads(json.dumps(settings)))

#Connect to server
host = '198.125.177.3'
port = 4220
server_addr=(host,port)

for command in commands :
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    #Send settings to server
    s.connect(server_addr)
    s.send(command.encode())
    s.send(''.encode())
    print('data sent')
    print(command.encode())
    s.close()
    
    #Send settings to server
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(server_addr)
    buffer_size=4096
    result = s.recv(buffer_size)
    all_result=[]
    print('result length={}'.format(len(result)))
    while len(result) > 0 :
        print('result length={}'.format(len(result)))
        result = s.recv(buffer_size)
        all_result+=result
    print('data received')
    print(result)

    #Give enough time for device to initialize
    time.sleep(WAIT_TIME)

    #Start
    data_window=1 #Amount of time to take data

    #Close socket to server
    s.shutdown(socket.SHUT_RDWR)
    s.close()

v=my_di4108.convert_data(DI4108_WRAPPER.convert_bytes_to_int(all_result))

t=numpy.linspace(0,pulse_duration-1/fs,len(v[0]))

for i in range(len(v)):
    if i>3 :
        t_offset=-0.5/fs
    else :
        t_offset=0
    plt.plot(t+t_offset,v[i])

plt.show()
