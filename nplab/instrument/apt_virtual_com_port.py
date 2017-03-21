# -*- coding: utf-8 -*-
"""
Created on Mon Mar 20 20:43:17 2017

@author: Will
"""

import serial
import serial.tools.list_ports as list_ports
import struct
import numpy as np
import time
from collections import deque
import re

import nplab.instrument.serial_instrument as serial
import nplab.instrument.stage as stage


def detect_APT_VCP_devices(self):
    """Function to tell you what devices are connected to what comports """
    possible_destinations = [0x50,0x11,0x21,0x22,0x23,0x24,0x25,0x26,0x27,0x28,0x29,0x2A]
    device_dict = dict()
    for port_name, _, _ in list_ports.comports(): #loop through serial ports, apparently 256 is the limit?!
            
            print "Trying port",port_name
            try:
                for destination in possible_destinations:
                    try:
                        test_device = APT_VCP(port_name,destination = destination)
                        device_dict[port_name: {'destination':destination ,'Serial Number' : test_device.serial_number, 'Model' : test_device.model}]
                        break
                    except struct.error:
                        pass
            except serial.serialutil.SerialException:
                pass
    return device_dict

    

class APT_VCP(serial.SerialInstrument):
    """
    This class handles all the basic communication with APT virtual com ports
    """
    port_settings = dict(baudrate = 115200,
                          bytesize=8,
                          parity=serial.PARITY_NONE, 
                          stopbits=1,
                          xonxoff=0,
                          rtscts=0,
                          timeout=1,
                          writeTimeout=1)
    termination_character = "" #The APt communicates via fixed length messages therefore this is not required
    surprise_message_codes = {'MGMSG_HW_RESPONSE': 0x0080,#The message id codes for messages sent from the hardware to the device.
                              'MGMSG_HW_RICHRESPONSE' : 0x0081, # One for one line error code and one for longer error codes
                              'Status update id' : None} #This is the satus update message id that varies for each device and therefore must be set
    
    channel_number_to_identity = {1 : 0x01, 2 : 0x02, 3 : 0x04, 4 : 0x08 } # Sets up the channel numbers to values
    state_conversion = {True : 0x01, False : 0x02} # Sets up the conversion from True and False values to 1's and 2's (godknows why they havnt used 0 and 1)
    reverse_state_conversion = {0x01 : True, 0x02 : False}
    serial_num_to_device_types = {20 : ['Legacy Single channel stepper driver','BSC001'],
                                25 : ['Legacy single channel mini stepper driver','BMS001'],
                                30 : ['Legacy dual channel stepper driver','BSC002'],
                                35 : ['Legacy dual channel mini stepper driver','BMS002'],
                                40 : ['Single channel stepper driver','BSC101'],
                                60 : ['OptoSTDriver(mini stepper driver)', 'OST001'],
                                63 : ['OptoDCDriver (mini DC servo driver)','ODC001'],
                                70 : ['Three channel card slot stepper driver', 'BSC103'],
                                80 : ['Stepper Driver T-Cube','TST001'],
                                73 : ['Brushless DC motherboard','BBD102/BBD103'],
                                94 : ['Brushless DC motor card','BBD102/BBD103']}
    command_log = deque(maxlen = 20) #stores commands sent to the device
    def __init__(self, port=None,source =0x01,destination = None,verbosity = True, use_si_units = False):
        """
        Set up the serial port, setting source and destinations, verbosity and hardware info.
        """
        serial.SerialInstrument.__init__(self, port=port) #this opens the port
        self.source = source
        if destination == None:
            print 'destination has not been set!'
        else:
            self.destination = destination
        self.verbosity = verbosity
        self.verbose(self.get_hardware_info())
        
    def read(self):
        '''Overwrite the read command with a fixed length read, check 
            for aditional data stream and error codes'''
        header=bytearray(self.ser.read(6))              #read 6 byte header
        msgid, length, dest, source = struct.unpack('<HHBB', header) #unpack the header as described by the format were a second data stream is expected 
        
        if msgid in self.surprise_message_codes.values():  #Compare the message code to the list of suprise message codes
            if msgid == self.surprise_message_codes['MGMSG_HW_RESPONSE']: 
                msgid, param1, param2, dest, source = struct.unpack('<HBBBB', header)
                returned_message = {'message': msgid,'param1' : param1, 
                                    'param2' : param2, 'dest' : dest,
                                    'source' : source}
                self.verbose(returned_message)
                self.read()
            elif msgid == self.surprise_message_codes['MGMSG_HW_RICHRESPONSE']:
                data = self.ser.read(length)
                returned_message = {'message': msgid,'length' : length,
                                    'dest' : dest, 'source' : source, 
                                    'data' : data}
                self.verbose(returned_message)
                self.read()
            elif (msgid == self.surprise_message_codes['Status update id'] 
                    and self.command_log[-1] == self.surprise_message_codes['Status update id']):
                data = self.ser.read(length)
                returned_message = {'message': msgid,'length' : length,
                                    'dest' : dest, 'source' : source,
                                    'data' : data}
                self.update_status(returned_message)
                self.read()                
            
        else:
            if self.source|0x80 == dest:
                data = self.ser.read(length)
                returned_message = {'message': msgid,'length' : length,
                                    'dest' : dest, 'source' : source,
                                    'data' : data}
            else:
                msgid, param1, param2, dest, source = struct.unpack('<HBBBB', header)
                
                returned_message = {'message': msgid,'param1' : param1, 
                                    'param2' : param2, 'dest' : dest, 
                                    'source' : source}
            return returned_message
        
    def write(self,message_id,param1 = 0x00,param2 = 0x00):
        """Overwrite the serial write command to combine message_id,
            two possible paramters (set to 0 if not given)
            with the source and destinations """
        formated_message=bytearray(struct.pack('<HBBBB', message_id, param1, param2, 
                                               self.destination, self.source))
        self.ser.write(formated_message)
    
    def query(self,message_id,param1 = 0x00,param2 = 0x00):
        """Oveawrite the query command to allow the correct passing of 
            message_ids and paramaters """
        with self.communications_lock:
            self.flush_input_buffer()
            self.write(message_id,param1,param2)
            return self.read()#question: should we strip the final newline?
            
    def verbose(self,message):
        if self.verbosity == True:
            print message
    #Listing General control message, not all of these can be used with every piece of equipment
    def identify(self):
        """ Instruct hardware unit to identify itself by flashing its LED"""
        self.write(0x0223)
    
    def set_channel_state(self,channel_number,new_state):
        """ Enable or disable a channel"""
        channel_identity = self.channel_number_to_identity[channel_number]
        new_state = self.state_conversion[new_state]
        self.write(message = 0x0210, param_1 = channel_identity,param_2 = new_state)
        
    def get_channel_state(self,channel_number):
        """Get the current state of a channel """
        message_dict = self.query(0x0211,param1 = self.channel_number_to_identity[channel_number]) # Get the entire message dictionary
        current_state = self.reverse_state_conversion[message_dict['param2']] # pull out the current state parameter and convert it to a True/False value
        return current_state 
        
    def disconnect(self):
        """Disconnect the controller from the usb bus"""
        self.write(0x002)
        
    def enable_updates(self,enable_state, update_rate = 10):
        '''Enable or disable hardware updates '''
        if enable_state==True:
            self.write(0x0011,param1 = update_rate)
        if enable_state==False:
            self.write(0x0012)

    def get_hardware_info(self):
        '''Manually get a status update '''
        message_dict = self.query(0x0005)
        serialnum, model, hwtype, swversion, notes, hwversion, modstate, nchans = struct.unpack('<I8sHI48s12xHHH', message_dict['data'])
        hardware_dict = {'serial_number':serialnum, 'model' :model, 'hardware_type': hwtype, 
                       'software_version' : swversion, 'notes':notes,'hardware_version' : hwversion, 
                       'modstate' : modstate, 'number_of_channels' : nchans}
        self.serial_number = serialnum
        self.model = self.serial_num_to_device_types[int(str(serialnum)[0:2])]
        self.number_of_channels = nchans
        return hardware_dict
    def get_status_update(self):
        '''This need subclassing and written over as the commands and format 
        varies between devices '''
        raise NotImplementedError
        
    def update_status(self):
        '''This  command should update device properties from the update message
            however this has to be defined for every device as the status update format
            and commands vary, 
            please implement me
            Args:
                The returned message from a status update request           (dict)
            '''
        raise NotImplementedError


if __name__ == '__main__' :
    microscope_stage = APT_VCP(port = 'COM12',source = 0x01,destination = 0x21)