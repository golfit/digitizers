#Test di4108 model
#T. Golfinopoulos, 5 Sept. 2018

import numpy
import matplotlib.pyplot as plt
from math import ceil
from digitizer_models import DI4108

my_di4108=DI4108(v_range=0.250) 

pulse_duration=1.0 #Length of pulse

#time_elapsed derives from Python time.time() measurements - there is some latency
#in this, likely due to USB reads/writes.  A better way to measure time
#is to digitize an accurately-clocked signal and evaluate accordingly
(my_data,time_elapsed)=my_di4108.trig_data_pulse(pulse_duration)

print("Number of samples={}".format(len(my_data)))
print("Elapsed time={} s".format(time_elapsed))
#By default, only analog data channels are recorded
v_data=my_di4108.convert_data(my_data)

chan_1=[v_data[i] for i in range(0,len(v_data),my_di4108.number_records)]
#chan_1=[my_data[i] for i in range(0,len(my_data),my_di4108.number_records)]

#Count number of zero crossings
n_pos_cross=0
first_ind=0
last_ind=0
for i in range(1,len(chan_1)):
    if(chan_1[i-1]<0 and chan_1[i]>0) :
        n_pos_cross+=1
        if(n_pos_cross==1) :
            first_ind=i
        else :
            last_ind=i

wave_freq=1E3 #Frequency of test waveform input into Channel 1

real_time_elapsed=(n_pos_cross-1)/wave_freq #Count time intervals, which is n_pos_cross less one
print("n_pos_cross={}, f_wave={} Hz, real_time_elapsed={} s".format(n_pos_cross,wave_freq,real_time_elapsed))

fs_real=(last_ind-first_ind)/real_time_elapsed
print("Real sampling frequency=(last zero crossing ind-first zero crossing ind)/real_time_elapsed={} Hz".format(fs_real))

#print("Length of v_data={}".format(len(v_data)))
#print("v_data/{}={}".format(my_di4108.number_records,len(v_data)/my_di4108.number_records))

#t=numpy.linspace(0,time_elapsed,len(chan_1))

#Nominal timebase - this seems to be more accurate than the timebase inferred from time_elapsed
t=numpy.linspace(0,(len(chan_1)-1)/my_di4108.fs,len(chan_1))

print("Max. raw data={}, min. raw data={}".format(max(my_data),min(my_data)))
print("Max. v_data={}, min. v_data={}".format(max(v_data),min(v_data)))

#for i in range(my_di4108.number_records):
#Channels 1-4 lead Channels 5-8 by one half a sample
for i in range(4):
    chan=[v_data[j] for j in range(i,len(v_data),my_di4108.number_records)]
    plt.plot(t,chan,'b-')

for i in range(4,8):
    chan=[v_data[j] for j in range(i,len(v_data),my_di4108.number_records)]
    plt.plot(t-0.5/my_di4108.fs,chan,'k-')


plt.show()
