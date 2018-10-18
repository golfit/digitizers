'''
Examine format of bytes data to try to figure out how data comes in, how to parse correctly.

T. Golfinopoulos, 18 Oct. 2018
'''
import pickle
import matplotlib.pyplot as plt
from digitizer_models import DI4108_WRAPPER

data_file=open('last_data.p','rb')
my_data=pickle.load(data_file)

t=my_data['t']
v=my_data['v']

raw=my_data['raw']

n_bits=16

parsed=DI4108_WRAPPER.convert_bytes_to_int(raw[0:])
v_new=[]
v_range=1.0
for i in range(len(parsed)):
    parsed[i]=DI4108_WRAPPER.twos_comp(parsed[i],n_bits)
    v_new.append(parsed[i]/float(pow(2,n_bits-1))*v_range)
    
print(parsed[0:50])
print(v_new[0:50])
print(v[0][0:50])


print(raw[0:20])
#plt.plot(t,v[0])
#plt.show()
