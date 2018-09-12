'''
This module contains models for digitizers.

Should be used in Python 3

T. Golfinopoulos
Begun on 24 August, 2018
'''
import usb.core
import usb.util
import time
import array
from math import floor, ceil, log2
#import numpy

#

class DI4108_WRAPPER :
    _FS_MIN=915.5413
    _FS_MAX=160E3
    
    def __init__(self,fs=10000,v_range=None,chans=None,dig_in=False, \
     rate_in=False, rate_range=None, ffl=None, counter_in=False,dec=1,filt_settings=None,\
     packet_size=None,packet_buffer_size=5,packet_time=0.005):
        '''
        Initialize instance of DI4108_WRAPPER object.  Attributes:
        def __init__(self,fs=10000,v_range=10,chans=8,dig_in=False,  \
         rate_in=False, rate_range=1,counter_in=False,dec=1,filt_settings=None,\
         packet_size=None, packet_buffer_size=5,packet_time=0.005)
     
        fs=sampling frequency in Hz.  Must be <=160000 Hz
        
        v_range=voltage range [units=V].  Scalar input, default=10.  Can either be 0.2, 0.5, 1, 2, 5, or 10.  Numeric inputs will be rounded to closest of these values.
        
        chans=can be either empty, or a list of channel numbers between 0 and 7 (inclusive), or an integer between 0 and 8 (inclusive).  If an integer, channels 0 to chans-1 are recorded.  Default=8.

        dig_in=Boolean flag indicating whether or not to store digital inputs
        
        rate_in=Boolean flag indicating whether to store rate input on Digital Input 2
        
        rate_range=scale for rate (frequency) measurement on Digital Input 2
        
        ffl=Setting for moving average filter applied to rate measurement on Digital Input 2.  Default=None.
         Can be an integer between 1 and 64, inclusive.
        
        dec=decimation factor.  Default=1 (i.e. no decimation).  Can be between 1 and 512 (inclusive).
        
        filt_settings=filter controls for analog inputs.  Default is to select the last point
         in the decimation window.  Allowable values are 0 (select last point), 1 (apply
         cascaded integrator-comb filter), 2 (take maximum point in decimation window),
         and 3 (take minimum point in decimation window).  Input may also be a list of these
         allowed values, corresponding to the list input in chans, with each filter mode
         applied to the channel with the same index in chans.  Otherwise, the same filter mode
         is applied to all analog channels.
        
        counter_in=Boolean flag indicating whether to store counter input on Digital Input 3
        
        packet_size=size of packets transferred in each sample.  Units=bytes.  Default=None - this
            causes a calculated value of packet_size=fs*poll_time*nchans*2 (# bytes/poll time)

        packet_buffer_size=number of packets between data polls (i.e. number of packets in on-device buffer).  Default=5

        packet_time=time between data reads (units=seconds).  Default=0.005 s.  Poll time=packet_time*packet_buffer_size.
        
        T. Golfinopoulos, 24 August 2018
        '''
        self.debug=False #Debug flag
        
        self.fs=fs #Sampling frequency
        
        if v_range is None :
            self.v_range=10
             #+-10 V corresponds to voltage programming code of 0b0000
             #(four least-significant bits of channel slist program)
            if self.debugging():
                print(self._v_code) #Debug
            #self.v_code=0
        else :
            try :
                self.v_range=v_range #v_code is automatically set accordingly
            except :
                raise ValueError("Possibly invalid v_range input - must be numeric")
        
        if rate_range is None :
            self.rate_range=50E3 #Default - maximum rate scale
        else :
            try :
                self.rate_range=rate_range #rate_code is automatically set accordingly
            except :
                raise ValueError("Possibly invalid rate range input - must be numeric")
        
        #Set ffl
        self.ffl=ffl
        
        #Assign filter and decimation settings
        self.filt_settings=filt_settings
        self.dec=dec
        
        self.chans=chans
        
        self.dig_in=dig_in #Boolean flag indicating whether or not to store digital inputs
        self.counter_in=counter_in #Boolean flag indicating whether to store counter input
        self.rate_in=rate_in #Boolean flag indicating whether to store rate input

        #Add additional data entries to nchans to account for data size per sample.
        #Each channel corresponds to 2 bytes (16 bits) of data.
        self.number_records=self.nchans+self.dig_in+self.counter_in+self.rate_in

        #self.poll_time=poll_time
        
        self.packet_buffer_size=packet_buffer_size #Store this many packets between reads

        self.poll_time=self.packet_buffer_size*packet_time
        self.packet_size=packet_size #Size of packets transferred in each sample.

        if self.debugging():
            print("Packet size={}".format(self.packet_size))
            print("Poll time={} (adjusted to better fit packet size, and scaled by buffer size={})".format(self.poll_time,self.packet_buffer_size))
            print("Ready to connect to a USB device")
        
        try :
            #Establish connection to device
            #Make sure device is plugged into USB port ;)
            #Find the device - the DATAQ DI-4108 has idVendor of 0683 and idProduct of 4108.  If there are multiple devices, you can use address and bus as unique identifiers
            self.dev=usb.core.find(idVendor=0x0683,idProduct=0x4108)

            if self.dev is None :
                raise ValueError('Device not found')

            # set the active configuration. With no arguments, the first
            # configuration will be the active one
            self.dev.set_configuration()

            # get an endpoint instance
            self.cfg = self.dev.get_active_configuration()
            self.intf = self.cfg[(0,0)]

            #Timeout for I/O operations - give up beyond this time [milliseconds]
            self.timeout=1000
            
            self.ep_out = usb.util.find_descriptor(
                self.intf,
                # match the first OUT endpoint
                custom_match = \
                lambda e: \
                    usb.util.endpoint_direction(e.bEndpointAddress) == \
                    usb.util.ENDPOINT_OUT)

            self.ep_in = usb.util.find_descriptor(
                self.intf,
                # match the first OUT endpoint
                custom_match = \
                lambda e: \
                    usb.util.endpoint_direction(e.bEndpointAddress) == \
                    usb.util.ENDPOINT_IN)

            assert not self.ep_out is None
            assert not self.ep_in is None
            
            #Test that all devices respond correctly to basic requests for information
            def test_dev(ep_o,ep_i):
                '''
                This method makes sure device responds to basic information test.
                '''
                pass_test=False
                num_tries=3
                for i in range(num_tries) :
                    ep_o.write('info 0')
                    my_output=ep_i.read(self.packet_size*5)
                    #Join my_output into string.
                    my_output=''.join([chr(x) for x in my_output])
                    if my_output == 'info 0 DATAQ\r' :
                        pass_test=True

                if not pass_test :
                    raise IOError("Device does not respond to info 0 with info 0 DATAQ\\r - responds with {}".format(my_output))
            
            if hasattr(self.ep_out,'__iter__') :
                assert(len(self.ep_out)==len(self.ep_in))
                for i in range(len(self.ep_out)) :
                    test_dev(self.ep_out[i],self.ep_in[i])
            else :
                test_dev(self.ep_out,self.ep_in)
        
        except :
            print("Can't create a new USB connection may exist already")
        
        if self.debugging() :
            print("Ready to set up device")
        
        #Configure device
        try :
            self.setup_device()
        except:
            print("Can't setup device - may not be connected")
        
        if self.debugging() :
            print("Done initializing device")
    
    def setup_device(self) :
        '''
        Communicate with DATAQ DI-4108 device(s) to activate specified channels, set sampling rate and voltage range and filtering and decimation, etc.
        '''
        record_counter=0
        
        record_config_number=[]
        
        #Set channel order.  Channels are added in this order:
        #First, channels in chans, in the order specified in that list
        #Then, digital inputs
        #Then, the rate (frequency measurement) input on Channel D2
        #Finally, the counter input on Channel D3
        #Channels that are not active are skipped in that ordering.
        for i in range(len(self.chans)) :
            #The analog channel configuration code is constructed such that
            #the 4 least-significant bits encode the analog channel
            #number, and bits 8-11 encode the voltage range, where
            #0=>+-10 V, 1=>+-5 V, 2=>+-2 V, 3=>+-1 V, 4=>+-0.5 V, and
            #5=>+-0.2 V.  See protocol.
            #Bit-shift code number by eight bits to put between bits 
            #8-11 for voltage range.
            record_config_number.append(self.chans[i]+(self._v_code<<8))
        

        #If digital inputs are requested, add to list.
        #This input set is activated with the number, 8 (i.e. 0b0000000000001000)
        if self.dig_in :
            record_config_number.append(8)
        
        #If rate input is requested, add to list.
        #Note that rate range must be specified according to
        #[50E3, 20E3,10E3,5E3,2E3,1E3,500,200,100,50,20,10] Hz,
        #with code corresponding to index in this list,
        #but starting at 1!
        if self.rate_in :
            record_config_number.append( (self.rate_range<<8)+9 )
        
        #If counter input is requested, add to list with activation
        #code, 10
        if self.counter_in :
            record_config_number.append(10)

        #Make sure number of records matches configured number of records
        assert(len(record_config_number)==self.number_records)
        
        #Invoke slist commands to configure device
        for record_counter in range(len(record_config_number)) :
            self.ep_out.write('slist {} {}'.format(record_counter,record_config_number[i]))
        
        #Next, set sampling frequency
        #Calculate srate parameter from desired sampling frequency, self.fs
        #and decimation factor.  Enforce range for srate.  See protocol
        self.srate=max(375,min(int(60E6/(self.fs*self.dec)),65535))

        #Calculate real sampling frequency given integer-ized srate
        self.fs_actual=60.0E6/(self.srate*self.dec)
        
        self.ep_out.write('srate {}'.format(self.srate))
        
        #Apply filtering
        if type(self.filt_settings) is list :
            for i in range(len(self.filt_settings)) :
                #Apply filter setting for each channel
                self.ep_out.write('filter {} {}'.format(self.chans[i],self.filt_settings[i]))
        elif type(self.filt_settings) is int :
            #filt_settings is a scalar => same for all analog channels
            #Asterisk * wildcard is allowed to refer to all channels (see protocol)
            self.ep_out.write('filter * {}'.format(self.filt_settings))
        #Don't set filter if not specified - leave default.
        
        #Apply decimation window
        self.ep_out.write('dec {}'.format(self.dec))
        
        #Apply moving average filter setting for rate measurement on Digital Input DI2, if specified.
        if not self.ffl is None :
            self.ep_out.write('ffl {}'.format(self.ffl))

        #Set packet size on device
        self.ep_out.write('ps {}'.format(self._packet_size_ind))

        #Read device once to clear out buffer
        self.ep_in.read(self.packet_size*5,self.timeout)

    def read(self):
        '''
        Read packet(s) - this will return data according to the listed channel set.
        Each active channel returns two bytes, concatenated.  To unpack, see chans
        list attribute, which shows the order of the channels.

        USAGE:
            this_data=my_di4108.read()
        
        T. Golfinopoulos, 5 Sept. 2018
        '''
        #Scale packet size by a buffer length (default=5) - not sure what sets the buffering
        #but seems to be larger than a single packet
        return self.ep_in.read(self.packet_size*self.packet_buffer_size,self.timeout)

    def trig_data_pulse(self,pulse_duration):
        '''
        Start data pulse and run for pulse_duration.  Poll data every poll_time seconds.
        Return data array.

        USAGE:
            (my_data,elapsed_time,raw_data)=my_di4108.trig_data_pulse(pulse_duration)

        INPUTS:
            pulse_duration=duration of data pulse in seconds

        OUTPUTS:
            my_data=array of raw integer data.  Each element corresponds to
                two bytes of data from a single channel.
            elapsed_time=difference between start and stop times of digitizers.  Evaluated with
                Python time library, so may not be very accurate.
            raw_data=array of raw bytes data.  Each pair of elements, (0,1), (2,3), etc. comprise one
                2-byte (16-bit) integer.  Length is twice that of my_data

        T. Golfinopoulos, 5 September 2018, 12 September 2018.
        '''
        self.ep_out.write('info 0')
        
        num_polls=ceil(pulse_duration/self.poll_time)
        raw_data=[None]*num_polls #Preallocate list

        self.ep_out.write('start 0') #Start collecting data.
        t0=time.time()
        temp=self.read() #Read data to clear buffer
        for i in range(num_polls) :
            raw_data[i]=self.read() #Read data
            tb=time.time()
            #Correct by removing transmission time
            wait_time=(i+1)*self.poll_time-(tb-t0)
            if wait_time>0:
                time.sleep(wait_time) #Wait until next poll time, if there is time left to wait

        tf=time.time()
        self.ep_out.write('stop') #Stop data pulse

        #Collapse data into one-dimensional array
        if self.debugging():
            print("Number of packets={}".format(len(raw_data)))
        data=[]
        #first_data_pt=''.join([chr(x) for x in raw_data[0]])
        #print(first_data_pt)
        for elem in raw_data[0:] : #Skip first sample - from ps
            data+=elem

        my_data=DI4108_WRAPPER.convert_bytes_to_int(data)
        
        return (my_data,tf-t0,data)

    def twos_comp(val, bits):
        """compute the 2's complement of int value val"""
        if (val & (1 << (bits - 1))) != 0: # if sign bit is set e.g., 8bit: 128-255
            val = val - (1 << bits)        # compute negative value
        return val

    @staticmethod
    def convert_bytes_to_int(bytes_data):
        '''
        Convert array consists of list of single-byte elements,
        where pairs of elements - (0,1), (2,3), etc. - form 2-byte (16-bit) integers,
        into array of integers.
        
        USAGE:
            DI4108_WRAPPER.convert_bytes_to_int(bytes_data_array)

        INPUT:
            raw_data_array=array of bytes data, each element of which is a byte

        OUTPUT:
            array with half length of raw_data, but converted to integers.
            
        T. Golfinopoulos, 12 Sept. 2018
        '''
        #Combine separated two-bytes into one number
        my_data=[None]*int(len(bytes_data)/2)

        for i in range(len(my_data)) :
            my_data[i]=bytes_data[2*i]+(bytes_data[2*i+1]<<8)
            
        return my_data
        
    def convert_data(self,raw_data_array):
        '''
        Convert data to floating point values (where appropriate) according to ranges.

        USAGE:
            my_di4108.convert_data(raw_data_array)

        INPUT:
            raw_data_array=array of data, each element of which is an integer

        OUTPUT:
            array with same length of raw_data, but converted to floating point for
            analog channels, according to voltage range.
        '''
        output_data_array=[None]*len(raw_data_array)
        
        for i in range(int(len(raw_data_array)/self.number_records)):
            ptr=0
            #Convert analog channels first - there are self.nchans of them
            #Note: data are in two's complement.
            for j in range(self.nchans) :
                ptr=i*self.number_records+j
                try :
                    output_data_array[ptr]=DI4108_WRAPPER.twos_comp(raw_data_array[ptr],16)/32768.0*self.v_range
                except :
                    if self.debugging():
                        print(raw_data_array[ptr])
                    raise 
            
            #After analog channels, data comes in as digital input, rate, and counter
            if self.dig_in :
                ptr+=1
                #Get bits 8-16
                output_data_array[ptr]=raw_data_array[ptr]>>8

            #See protocol documentation, Pages 15-16
            #Note: data are in two's complement.
            if self.rate_in :
                ptr+=1
                output_data_array[ptr]=(raw_data_array[ptr]+32768)/65536.0*self.rate_range

            #Note: data are in two's complement.
            if self.counter_in :
                ptr+=1
                output_data_array[ptr]=raw_data_array[ptr]+32768
                
        return output_data_array   

    def process_range(range_arg,allowed_range_vals) :
        '''
        USAGE:
            process_range(range_arg,allowed_range_vals)
        INPUT:
            range_arg=attempted range input
            allowed_range_vals=list of allowed values for the range
        OUTPUT:
            (allowed_range,range_ind)=Value in allowed_range_vals that is nearest (i.e. smallest absolute
            difference) to range_arg, and index of allowed_range in allowed_range_vals
        
        T. Golfinopoulos, 24 August 2018
        See also process_v_range, process_rate_range
        '''
        diffs=[abs(range_arg-x) for x in allowed_range_vals]
        #Find closest allowed range in list
        range_ind=diffs.index(min(diffs))
        allowed_range=allowed_range_vals[range_ind]
        return (allowed_range,range_ind)

    
    def process_v_range(v_range) :
        '''
        USAGE:
            process_v_range(v_range)
        INPUT:
            v_range=voltage range value to test
            
        OUTPUT:
            (allowed_v_range,v_code) - two-element tuple, the first collapsing v_range onto the nearest value in [10,5,2,1,0.5,0.2], and the second, the corresponding binary code for this range, [0,1,2,3,4,5].  v_code corresponds to the index of the nearest voltage value in the allowed v_range list.
        
        T. Golfinopoulos, 24 August 2018
        See also process_range, process_rate_range
        '''
        allowed_voltage_ranges=[10,5,2,1,0.5,0.2]
        return DI4108_WRAPPER.process_range(v_range,allowed_voltage_ranges)
    
    def process_rate_range(rate_range) :
        '''
        USAGE:
            process_rate_range(rate_range)
        INPUT:
            rate_range=frequency scale, allowed to be
                [50E3,20E3,10E3,5E3,2E3,1E3,500,200,100,50,20,10].
                Corresponding code is the index in this list + 1 (i.e.
                the list is indexed starting at 1).
                The nearest value to the supplied value of rate_range is used.
        See also process_range, process_v_range
        '''
        allowed_rate_ranges=[50E3,20E3,10E3,5E3,2E3,1E3,500,200,100,50,20,10]
        allowed_rate,rate_ind=DI4108_WRAPPER.process_range(rate_range,allowed_rate_ranges)
        return (allowed_rate,rate_ind+1)

    @property
    def fs(self):
        return self._fs
    
    @fs.setter
    def fs(self,fs):
        if fs < DI4108_WRAPPER._FS_MIN or fs > DI4108_WRAPPER._FS_MAX :
            raise ValueError("Sampling frequency must be <={} Hz and >={} Hz".format(DI4108_WRAPPER._FS_MIN,DI4108_WRAPPER._FS_MAX))
        else :
            self._fs=fs
    
    @property
    def v_range(self) :
        return self._v_range

    @v_range.setter
    def v_range(self,v_range):
        '''
        Set a new value for v_range - side-effect method.
        Sets both v_range and v_code attributes.
        
        Uses process_v_range(v_range), which returns a tuple of
        (v_range,v_code), and restricts v_range to allowed voltage ranges,
        [10, 5, 2, 1, 0.5, 0.2] V, by finding the closest allowed voltage
        to given voltage.  Index in this list is v_code.
        
        T. Golfinopoulos, 24 August 2018
        '''
        allowed_v_range,v_code=DI4108_WRAPPER.process_v_range(v_range)
        self._v_range=allowed_v_range
        self._v_code=v_code
        
    @property
    def chans(self):
        return self._chans
    
    @chans.setter
    def chans(self,chans):
        '''
        Set which channels on DI4108 are active, and what order they are polled.
        
        USAGE:
            my_di4108.chans=chans_input
        
        When chans_input is None, chans defaults to the list, [0,1,2,3,4,5,6,7]
        When chans_input is an integer between 0 and 7 (inclusive), chans is list(range(self.nchans))
        When chans_input is a list whose elements are between 0 and 7 (inclusive) and are unique, chans is assigned this list

        Otherwise, a ValueError is raised.

        T. Golfinopoulos, 7 September 2018
        '''
        
        msg="chans input can be either empty, or a list of 8 or fewer unique channel numbers between 0 and 7 (inclusive), or an integer between 0 and 8 (inclusive)"
        if chans is None :
            self.nchans=8
            self._chans=list(range(self.nchans))
        elif type(chans) is list :
            if any([x<0 or x>7 for x in chans]) or len(chans)>8:
                raise ValueError(msg)
            else :
                for i in range(len(chans)) :
                    if chans[i] in chans[0:i]+chans[i+1:] :
                        #Duplicate values in list
                        raise ValueError(msg)
                
                self._chans=chans
                self.nchans=len(chans)
                
        elif type(chans) is int :
            self.nchans=chans
            if self.nchans<0 or self.nchans>8 :
                raise ValueError(msg)
            else :
                self._chans=list(range(self.nchans))
        else :
            raise ValueError(msg)
    
    @property
    def dig_in(self):
        return self._dig_in
    
    @dig_in.setter
    def dig_in(self,dig_in):
        '''
        dig_in is a Boolean flag indicating whether the digital input data
        should be polled on every sample.
        
        USAGE:
            my_di4108.dig_in=dig_in
        
        dig_in must be Boolean
        '''
        if not dig_in is True and not dig_in is False :
            raise ValueError("dig_in must be a Boolean flag, True or False")
        else :
            self._dig_in=dig_in
    
    @property
    def rate_in(self):
        return self._rate_in
    
    @rate_in.setter
    def rate_in(self,rate_in):
        '''
        rate_in is a Boolean flag indicating whether the rate measure on Digital Input 2 
        should be polled on every sample.
        
        USAGE:
            my_di4108.rate_in=rate_in
        
        rate_in must be Boolean
        '''
        if not rate_in is True and not rate_in is False :
            raise ValueError("rate_in must be a Boolean flag, True or False")
        else :
            self._rate_in=rate_in
    
    @property
    def counter_in(self):
        return self._counter_in
    
    @counter_in.setter
    def counter_in(self,counter_in):
        '''
        counter_in is a Boolean flag indicating whether the counter measure on Digital Input 3 
        should be polled on every sample.
        
        USAGE:
            my_di4108.counter_in=counter_in
        
        counter_in must be Boolean
        '''
        if not counter_in is True and not counter_in is False :
            raise ValueError("counter_in must be a Boolean flag, True or False")
        else :
            self._counter_in=counter_in
        
    @property
    def packet_time(self):
        return self._packet_time

    @packet_time.setter
    def packet_time(self,packet_time):
        '''
        Set time between data reads - units=seconds.

        USAGE:
            my_di4108.packet_time=packet_time

        packet_time must be a numeric value > 0.

        T. Golfinopoulos, 5 Sep. 2018
        '''
        if packet_time<=0.0 :
            raise ValueError('packet_time must be numerical value > 0')
        else :
            self._packet_time=packet_time
        
    @property
    def packet_size(self):
        return self._packet_size

    @packet_size.setter
    def packet_size(self,packet_size):
        '''
        Set packet size, the number of bytes transferred in each transmission burst

        USAGE:
            my_di4108.packet_size=packet_size

        packet_size can only be 16, 32, 64, 128, 256, 512, 1024, or 2048 bytes.
        It should be chosen in such a way that the packet will be full on reads,
        but will not overflow buffers.  This means that a consideration of the
        sampling rate and number of channels to be digitized should be taken
        into account.

        The next largest value to these allowed values to the given packet_size will ultimately
        be chosen.

        If packet_size is None, then the packet size is set such that it will
        be full after 5 ms, i.e. ceil(self.fs*self.poll_time)
        '''
        allowed_values=[16,32,64,128,256,512,1024,2048]
        if packet_size is None :
            #Calculate the packet size/poll_time by #samples*(data size in bytes)/sample*#samples/poll_time
            #This is the default value
            packet_size=ceil(self.fs*self.poll_time/self.packet_buffer_size*self.number_records*2)

        packet_size_ind=max(min(ceil(log2(packet_size))-4,len(allowed_values)-1),0) #Index of 0 corresponds to 2^4
        allowed_packet_size=pow(2,packet_size_ind+4)

        #Don't use process_range - need next highest power of 2, rather than nearest value
        #(allowed_packet_size,packet_size_ind)=self.process_range(packet_size,allowed_values)
        self._packet_size=allowed_packet_size
        self._packet_size_ind=packet_size_ind

        #Recalculate poll time to better fite packet size
        self.poll_time=self._packet_size/(self.fs*self.number_records*2)*self.packet_buffer_size
    
    @property
    def packet_buffer_size(self) :
        return self._packet_buffer_size
        
    @packet_buffer_size.setter
    def packet_buffer_size(self, packet_buffer_size) :
        if int(packet_buffer_size) < 1 :
            raise ValueError("packet_buffer_size must be an integer greater than or equal to 1 - you entered {}".format(packet_buffer_size))
        else :
            self._packet_buffer_size=int(packet_buffer_size) #Ensure input is integer
    
    @property
    def rate_range(self) :
        return self._rate_range
    
    @rate_range.setter
    def rate_range(self,rate_range):
        '''
        Set a new value for rate_range - side-effect method.
        Sets both rate_range and rate_code attributes.
        
        Uses process_rate_range(rate_range), which returns a tuple of
        (rate_range,rate_code), and restricts rate_range to allowed voltage ranges,
        [50E3,20E3,10E3,5E3,2E3,1E3,500,200,100,50,20,10] Hz, by finding the closest
        #allowed rate range to given rate.  Index in this list +1 is rate_code.
        
        T. Golfinopoulos, 24 August 2018
        '''
        allowed_rate_range,rate_code=DI4108_WRAPPER.process_rate_range(rate_range)
        self._rate_range=allowed_rate_range
        self.rate_code=rate_code
    
    @property
    def filt_settings(self):
        return self._filt_settings
    
    @filt_settings.setter
    def filt_settings(self,filt_settings):
        '''
        Set values for filter settings.
        The allowable values are 0, 1, 2, or 3, which imply 
        0=>take last value in decimation window
        1=>Apply cascaded integrator-comb filter
        2=>take maximum value in decimation window
        3=>take minimum value in decimation window

        filt_settings can be a scalar, in which case the same setting
        is applied to all analog channels, or a list with the same
        length as chans, wherein each element of filt_settings contains
        the setting of the channel with the corresponding index in chans.
        '''
        def test_val(x) :
            '''
            Ensure the settings have an allowed value
            '''
            if not x in [0,1,2,3] :
                raise ValueError("filt_settings must have value(s) of 0, 1, 2, or 3 - value is {}".format(x))

        if filt_settings is None :
            filt_settings=0 #Default value for filt_settings
        if type(filt_settings) is list :
            for x in filt_settings :
                test_val(x)
            if len(filt_settings) != len(self.chans) :
                raise ValueError("If filt_settings is an array, it must have the same length as chans")
            else :
                self._filt_settings=filt_settings
        else :
            test_val(filt_settings)
            self._filt_settings=filt_settings
    
    @property
    def dec(self):
        return self._dec
    
    @dec.setter
    def dec(self,dec):
        '''
        Set the number of samples in the decimation window.  Allowed values are integers,
        1<=dec<=512
        
        T. Golfinopoulos, 24 August 2018
        '''
        if dec<1 or dec>512 or type(dec)!=int :
            raise ValueError('dec must be an integer, 1<=dec<=512')
        else :
            self._dec=dec
    
    @property
    def ffl(self) :
        return self._ffl
    
    @ffl.setter
    def ffl(self,ffl):
        '''
        Set ffl.  Allowable values are integers between 1 and 64, inclusive.
        
        T. Golfinopoulos, 24 August 2018
        '''
        if ffl is None :
            self._ffl=None
        elif ffl>=1 and ffl<=64 and type(ffl) is int :
            self._ffl=ffl
        else :
            raise ValueError('ffl must be an integer, 1<=ffl<=64')
    
    def set_led(self,led_val=2):
        '''
        Set LED color according to the following table for led_val:
        led_val=0 => black (off)
        led_val=1 => blue
        led_val=2 => green
        led_val=3 => cyan
        led_val=4 => red
        led_val=5 => magenta
        led_val=6 => yellow
        led_val=7 => white
        
        USAGE:
        my_di4108.set_led(led_val)
        my_di4108.set_led()
        
        led_val must be an integer, 0<=led_val<=7.  If not specified, default value is 2 (green)
        
        T. Golfinopoulos, 24 August 2018
        ''' 
        if led_val<0 or led_val>7 :
            raise ValueError("led_val must be an integer, 0<=led_val<=7")
        else :
            self.ep_out.write('led {}'.format(led_val))
    
    def debugging(self):
        import os
        if self.debug == None:
            self.debug=os.getenv("DEBUG_DEVICES")
        return(self.debug)
