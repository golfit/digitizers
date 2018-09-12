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

WAIT_TIME=5

for k in DI4108_WRAPPER.__dict__.keys() :
    if type(DI4108_WRAPPER.__dict__[k]) is property :
        print(k)
        
pulse_duration=0.5 #Length of pulse [s]
fs=10000 #Sampling frequency [Hz]
n_samps_post=int(pulse_duration/fs)

settings={'fs':fs,'v_range':1,'chans':8,'n_samps_post':n_samps_post}

io=StringIO()

json.dump(settings,io)

print(io.getvalue())

settings_string=json.dumps(settings)

print(settings_string)

settings_loaded=json.loads(settings_string)

init_command='<init>'+settings_string+'</init>'

print(settings)
print(settings_loaded)

trig_command='<trig_pulse>'

store_command='<store>'

commands=[init_command,trig_command,store_command

#Try to instantiate object from settings through json cycle
my_di4108=DI4108_WRAPPER(**settings_loaded)

#Connect to server
host = '198.125.177.3'
port = 4220
server_addr=(host,port)

for command in commands :
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    #Send settings to server
    s.connect(server_addr)
    s.send(command.encode())
    print(command.encode())

    buffer_size=4096
    result = s.recv(buffer_size)
    all_result=[]
    while len(result) > 0 :
        result = s.recv(buffer_size)
        all_result+=result
        
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

for i in range(len(v))
    if i>3 :
        t_offset=-0.5/fs
    else :
        t_offset=0
    plt.plot(t+t_offset,v[i])

plt.show()
