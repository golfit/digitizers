#Test di4108 model
#T. Golfinopoulos, 5 Sept. 2018

import numpy
import matplotlib.pyplot as plt
from math import ceil
from digitizer_models import DI4108

my_di4108=DI4108() #Use default settings

pulse_duration=1.0 #Length of pulse

(my_data,time_elapsed)=my_di4108.trig_data_pulse(pulse_duration)

print("Number of samples={}".format(len(my_data)))

#By default, only analog data channels are recorded
v_data=my_di4108.convert_data(my_data)

t=numpy.linspace(0,time_elapsed,len(my_data))

plt.plot(t,v_data)

plt.show()
