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
from numpy import fft, logical_and
import matplotlib.pyplot as plt
import copy
import pickle
'''
for i in range(10,0,-1):
    print(i)
    time.sleep(1)
'''
WAIT_TIME=1

props=[]

for k in DI4108_WRAPPER.__dict__.keys() :
    if type(DI4108_WRAPPER.__dict__[k]) is property :
        print(k)
        props.append(k)
        
pulse_duration=1.0 #Length of pulse [s]
fs=1000 #Sampling frequency [Hz] #Don't go above 30 kHz for now - reading fails
n_samps_post=int(pulse_duration*fs)
trigger_mode='soft'#'hard' #Can be 'soft' for soft trigger or 'hard' for hardware trigger (rising edge on D6)
settings={'fs':fs,'v_range':10,'chans':8}
#settings={'fs':fs,'v_range':10.0,'chans':1,'trig_mode':trigger_mode}
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
#host='localhost'
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

t=numpy.array(numpy.linspace(0,pulse_duration-1.0/fs,len(v[0])))

print('length of v[0] is {}'.format(len(v[0])))
print('t[0]={},t[-1]={}'.format(t[0],t[-1]))
print('min(v[0])={},max(v[0])={}'.format(numpy.min(v[0]),numpy.max(v[0])))
data_dict={'raw':all_response,'bytes':response_bytes,'v':v,'t':t}
#data_dict={'v':v,'t':t}

drive_freq=3E3

fpath='/media/golfit/share/MIT/Research/SPARC/NINT/Instrumentation/InstrumentationBoards/Calibration/'
#fname=fpath+'BR_1008_test_Vsrc0pt48VppF'+str(numpy.round(drive_freq/1E3))+'kHz_match_IDiv10Chan1'
#Ih=27.7 or 27.6 A for plus Ih
#27.4 or 27.3 A for minus Ih
#27.8 A for Plus Ih including outermost channels
#10 mA excitation on Halls
fname=fpath+'QuarterBrdMHP1_8_PlusIhShot_10V'
#27.7 A 1-6, +, 10 V
#27.5 A 1-6, +, 0.2 V
#27.2 A 1-6, -, 0.2 V
#27.1 A 1-6, -, 10 V
#26.9 A  1-8, -, 10 V
#26.8 A 1-8, -, 0.2 V
#26.6 A 1-8, +, 0.2 V
#26.5 A 1-8, +, 10 V

write_file=open(fname+'.p','wb')
pickle.dump(data_dict,write_file)

my_fig,ax=plt.subplots() #Create figure with 1 row, 1 column

t_offset=0

n_cycles_to_plot=5

t_plot=n_cycles_to_plot/drive_freq

plot_inds=t<t_plot#logical_and(t<t_plot)

print('len(v)={}'.format(len(v)))
for i in range(len(v)):
    if i>3 :
        t_offset=0#-0.25/fs
    else :
        t_offset=0
    #ax.plot(t[plot_inds]+t_offset,numpy.array(v[i])[plot_inds])
    ax.plot(t+t_offset,numpy.array(v[i]))
    print("Channel {}: Mean sig: {}".format(i,numpy.mean(v[i])))
    '''
    V=fft.rfft(v[i])
    if len(v[i])%2==0 : #Even
        F=numpy.arange(0,len(v[i])/2+1)*fs/len(v[i])
    else :
        F=numpy.arange(0,numpy.ceil(len(v[i])/2))*fs/len(v[i])
    
    print("len(v[i])={}, len(V)={}, len(F)={}".format(len(v[i]),len(V),len(F)))
    ax.plot(F,V)
    '''
    #Count zero-crossings
    n_zero_crossings=0
    for j in range(len(v[i])-1) :
        if v[i][j]<0 and v[i][j+1]>=0 :
            n_zero_crossings+=1
    print("n_zero_crossings={}".format(n_zero_crossings))
    

#Add axis labels
plt.xlabel('t [s]')
plt.ylabel('v [V]')
plt.grid(True) #Show grid

#Save figure
#fname='Btheta_QB_1008_coils_Vin1pt5Vpp'

#fname='Microphone'
my_fig.savefig('{}.eps'.format(fname),bbox_inches='tight')
my_fig.savefig('{}.png'.format(fname),bbox_inches='tight')
my_fig.savefig('{}.svg'.format(fname),bbox_inches='tight')
plt.show()

