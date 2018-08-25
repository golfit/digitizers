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
#import numpy

class DI4108 :
    def __init__(self,fs=10000,v_range=None,chans=None,dig_in=False, \
     rate_in=False, rate_range=None, ffl=None, counter_in=False,dec=1,filt_settings=None,\
     packet_size=128):
        '''
        Initialize instance of DI4108 object.  Attributes:
        def __init__(self,fs=10000,v_range=10,chans=8,dig_in=False,  \
         rate_in=False, rate_range=1,counter_in=False,dec=1,filt_settings=None,\
         packet_size=128)
     
        fs=sampling frequency in Hz.  Must be <=160000 Hz
        
        v_range=voltage range [units=V].  Scalar input, default=10.  Can either be 0.2, 0.5, 1, 2, 5, or 10.  Numeric inputs will be rounded to closest of these values.
        
        chans=can be either empty, or a list of channel numbers between 0 and 7 (inclusive), or an integer between 0 and 8 (inclusive).  If an integer, channels 0 to chans-1 are recorded.  Default=8.

        dig_in=Boolean flag indicating whether or not to store digital inputs
        
        rate_in=Boolean flag indicating whether to store rate input on Digital Input 2
        
        rate_range=scale for rate (frequency) measurement on Digital Input 2
        
        ffl=Setting for moving average filter applied to rate measurement on Digital Input 2.  Default=None.
         Can be an integer between 1 and 64, inclusive.
        
        dec=decimation factor.  Default=1 (i.e. no decimation).  Can be between 1 and 512.
        
        filt_settings=filter controls for analog inputs.  Default is to select the last point
         in the decimation window.  Allowable values are 0 (select last point), 1 (apply
         cascaded integrator-comb filter), 2 (take maximum point in decimation window),
         and 3 (take minimum point in decimation window).  Input may also be a list of these
         allowed values, corresponding to the list input in chans, with each filter mode
         applied to the channel with the same index in chans.  Otherwise, the same filter mode
         is applied to all analog channels.
        
        counter_in=Boolean flag indicating whether to store counter input on Digital Input 3
        
        packet_size=size of packets transferred in each sample.  Units=bytes.  Default=128 bytes
        
        T. Golfinopoulos, 24 August 2018
        '''
        self.fs=fs #Sampling frequency
        if self.fs>160E3 :
            raise ValueError("Sampling frequency must be <=160000 Hz")
        
        if v_range is None :
            self.v_range=10
             #+-10 V corresponds to voltage programming code of 0b0000
             #(four least-significant bits of channel slist program)
            print(self.v_code) #Debug
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
        
        msg="chans input can be either empty, or a list of 8 or fewer channel numbers between 0 and 7 (inclusive), or an integer between 0 and 8 (inclusive)"
        if chans is None :
            self.nchans=8
            self.chans=list(range(self.nchans))
        elif type(chans) is list :
            if any([x<0 or x>7] for x in chans) or len(chans)>8:
                raise ValueError(msg)
            else :
                self.chans=chans
        elif type(chans) is int :
            self.nchans=chans
            if self.nchans<0 or self.nchans>8 :
                raise ValueError(msg)
            else :
                self.chans=list(range(self.nchans))
        else :
            raise ValueError(msg)
        
        self.dig_in=dig_in #Boolean flag indicating whether or not to store digital inputs
        self.counter_in=counter_in #Boolean flag indicating whether to store counter input
        self.rate_in=rate_in #Boolean flag indicating whether to store rate input
        
        self.packet_size=packet_size #Size of packets transferred in each sample.
        
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

        assert self.ep_out is not None
        assert self.ep_in is not None
        
        #Test that all devices respond correctly to basic requests for information
        def test_dev(ep_o,ep_i):
            '''
            This method makes sure device responds to basic information test.
            '''
            ep_o.write('info 0')
            my_output=ep_i.read()
            if my_output!='info 0 DATAQ\r' :
                raise IOError("Device does not respond to info 0 with info 0 DATAQ\\r")
        
        if hasattr(self.ep_out,'__iter__') :
            assert(len(self.ep_out)==len(self.ep_in))
            for i in range(len(self.ep_out)) :
                test_dev(self.ep_out[i],self.ep_in[i])
        else :
            test_dev(self.ep_out,self.ep_in)
        
        #Configure device
        self.setup_device()
    
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
            record_config_number.append(self.chans[i]+(self.v_code<<8))
        

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
        if self.count_in :
            record_config_number.append(10)
        
        #Invoke slist commands to configure device
        for record_counter in range(len(record_config_number)) :
            self.ep_out.write('slist {} {}'.format{record_counter,record_config_num[i]})
        
        #Next, set sampling frequency
        #Calculate srate parameter from desired sampling frequency, self.fs
        #and decimation factor.  Enforce range for srate.  See protocol
        self.srate=max(375,min(int(60E6/(self.fs*self.dec)),65535))
        
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
        ep_out.write('dec {}'.format(self.dec))
        
        #Apply moving average filter setting for rate measurement on Digital Input DI2, if specified.
        if not self.ffl is None :
            ep_out.write('ffl {}'.format(self.ffl))

        
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
        return DI4108.process_range(v_range,allowed_voltage_ranges)
    
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
        allowed_rate,rate_ind=DI4108.process_range(rate_range,allowed_rate_ranges)
        return (allowed_rate,rate_ind+1)
    
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
        allowed_v_range,v_code=DI4108.process_v_range(v_range)
        self._v_range=allowed_v_range
        self._v_code=v_code
    
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
        allowed_rate_range,rate_code=DI4108.process_rate_range(rate_range)
        self.rate_range=allowed_rate_range
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
                raise ValueError("filt_settings must have value(s) of 0, 1, 2, or 3")
        
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
