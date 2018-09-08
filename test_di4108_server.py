'''
This client tries to communicate setup information to "remotely" control a DI-4108.

T. Golfinopoulos, 7 September 2018
'''

from digitizer_models import DI4108_WRAPPER
import json
from io import StringIO
import socket
import time

WAIT_TIME=5

for k in DI4108_WRAPPER.__dict__.keys() :
    if type(DI4108_WRAPPER.__dict__[k]) is property :
        print(k)

settings={'fs':10000,'v_range':1,'chans':8}

io=StringIO()

json.dump(settings,io)

print(io.getvalue())

settings_string=json.dumps(settings)

print(settings_string)

settings_loaded=json.loads(settings_string)

print(settings)
print(settings_loaded)

#Try to instantiate object from settings through json cycle
#my_di4108=DI4108_WRAPPER(**settings_loaded)

#Connect to server
host = 'localhost'
port = 4220
server_addr=(host,port)
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

#Send settings to server
s.connect(server_addr)
s.send(settings_string.encode())
print(settings_string.encode())

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
