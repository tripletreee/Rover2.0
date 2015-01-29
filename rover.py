'''
A Python class for interacting with the Brookstone Rover 2.0.  

Copyright (C) 2014 Simon D. Levy

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as 
published by the Free Software Foundation, either version 3 of the 
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
'''

import struct
import threading
import socket
import time
import audioop
import binascii
import pyaudio
import wave
import sys
import numpy

from blowfish import Blowfish
from adpcm import *
from byteutils import *

    
class Rover:

    def __init__(self):
        ''' Creates a Rover object that you can communicate with. 
        '''
      
        self.HOST = '192.168.1.100'
        self.PORT = 80
        
        TARGET_ID = 'AC13'
        TARGET_PASSWORD = 'AC13'      
        
        self.TREAD_DELAY_SEC = 0.5
        self.KEEPALIVE_PERIOD_SEC = 60
        
                            
        # Create command socket connection to Rover      
        self.commandsock = self._newSocket()
        
        # Send login request with four arbitrary numbers
        self._sendCommandIntRequest(0, [0, 0, 0, 0])
                
        # Get login reply
        reply = self._receiveCommandReply(82)
                
        # Extract Blowfish key from camera ID in reply
        cameraID = reply[25:37].decode('utf-8')
        key = TARGET_ID + ':' + cameraID + '-save-private:' + TARGET_PASSWORD
        
        # Extract Blowfish inputs from rest of reply
        L1 = bytes_to_int(reply, 66)
        R1 = bytes_to_int(reply, 70)
        L2 = bytes_to_int(reply, 74)
        R2 = bytes_to_int(reply, 78)
        
        # Make Blowfish cipher from key
        bf = _RoverBlowfish(key)
        
        # Encrypt inputs from reply
        L1,R1 = bf.encrypt(L1, R1)
        L2,R2 = bf.encrypt(L2, R2)
        
        # Send encrypted reply to Rover
        self._sendCommandIntRequest(2, [L1, R1, L2, R2])     
        
        # Ignore reply from Rover
        self._receiveCommandReply(26)
        
        # Start timer task for keep-alive message every 60 seconds
        self._startKeepaliveTask()
        
        # Set up treads
        self.leftTread = _RoverTread(self, 4)
        self.rightTread = _RoverTread(self, 1)
        
        # Set up camera position
        self.cameraIsMoving = False
                      
        # Send video-start request
        self._sendCommandByteRequest(4, [1])
        
        # Get reply from Rover
        reply = self._receiveCommandReply(29)
                                
        # Create media socket connection to Rover      
        self.mediasock = self._newSocket()

        # Send video-start request based on last four bytes of reply
        self._sendRequest(self.mediasock, 'V', 0, 4, map(ord, reply[25:]))
        
        self.MEDIA_PASS = reply[25:]
        
        # Set the frame rate of the camera
        #self._sendCommandByteRequest(7, [50])
        
        # Send audio-start request
        self._sendCommandByteRequest(8, [1])
        
        # Ignore audio-start reply
        reply2 = self._receiveCommandReply(29)

        
        
        # Receive video and audio on another thread until closed
        self.is_active = True
        self.reader_thread = _MediaThread(self)
        self.reader_thread.start()
        
        # Start the talk function
        self.startTalk()
        
        
    def startTalk(self):
        ''' Start rover's talk function.
        '''
        
        # Send talk-start request
        self._sendCommandByteRequest(11, [1])
                
        # Ignore talk-start reply
        reply3 = self._receiveCommandReply(29)
        
        # Start talk thread
        self.talk_thread = _TalkThread(self)
        self.talk_thread.start()
        
    def endTalk(self):
        self._sendCommandByteRequest(13, [1])
        
        
    def close(self):
        ''' Closes off commuincation with Rover.
        '''
        
        # Stop moving treads
        self.setTreads(0, 0)
                
        self.keepalive_timer.cancel()
        
        self.is_active = False
        self.commandsock.close()
        
        if self.mediasock:
            self.mediasock.close()
            
    
        
    def getBatteryPercentage(self):
        ''' Returns percentage of battery remaining.
        '''
        self._sendCommandByteRequest(251)
        reply = self._receiveCommandReply(32)
        return 15 * ord(reply[23])
        
    def moveCamera(self, where):
        ''' Moves the camera up or down, or stops moving it.  A nonzero value for the 
            where parameter causes the camera to move up (+) or down (-).  A
            zero value stops the camera from moving.
        '''
        if where == 0:
            if self.cameraIsMoving:
                self._sendCameraRequest(1)
                self.cameraIsMoving = False
            
        elif not self.cameraIsMoving:
            if where == 1:
                self._sendCameraRequest(0)
            else:
                self._sendCameraRequest(2)                    
            self.cameraIsMoving = True
        
    def turnInfraredOn(self):    
        ''' Uses the infrared (stealth) camera.
        '''
        self._sendCameraRequest(94)  
        
    
    def turnInfraredOff(self):   
        ''' Uses the default camera.
        '''
        self._sendCameraRequest(95)   
    
    def setTreads(self, left, right):
        ''' Sets the speed of the left and right treads (wheels).  + = forward;
        - = backward; 0 = stop. Values should be in [-1..+1].
        ''' 
        currTime = time.time()
        
        self.leftTread.update(left)
        self.rightTread.update(right)
      
    def turnLightsOn(self):    
        ''' Turns the headlights and taillights on.
        '''
        self._setLights(8)   
        
    
    def turnLightsOff(self):   
        ''' Turns the headlights and taillights off.
        '''
        self._setLights(9)    
        
    def processVideo(self, jpegbytes):
        ''' Proccesses bytes from a JPEG image streamed from Rover.  
            Default method is a no-op; subclass and override to do something 
            interesting.
        '''
        pass
        
    def processAudio(self, pcmsamples):
        ''' Proccesses a block of 320 PCM audio samples streamed from Rover.  
            Audio is sampled at 8192 Hz and quantized to +/- 2^15.
            Default method is a no-op; subclass and override to do something 
            interesting.
        '''
        pass        
    
    # "Private" methods ========================================================
         
    def _startKeepaliveTask(self,):
        self._sendCommandByteRequest(255)
        self.keepalive_timer = \
            threading.Timer(self.KEEPALIVE_PERIOD_SEC, self._startKeepaliveTask, [])
        self.keepalive_timer.start()
    
    def _setLights(self, onoff):    
        self._sendDeviceControlRequest(onoff, 0)
        
    def _spinWheels(self, wheeldir, speed):    
        # 1: Right, forward
        # 2: Right, backward
        # 4: Left, forward
        # 5: Left, backward        
        self._sendDeviceControlRequest(wheeldir, speed) 
    
        
    def _sendDeviceControlRequest(self, a, b) : 
        self._sendCommandByteRequest(250, [a,b])

    def _sendCameraRequest(self, request):
        self._sendCommandByteRequest(14, [request]) 
    
    def _sendCommandByteRequest(self, id, bytes=[]):
        self._sendCommandRequest(id, len(bytes), bytes)
        
    def _sendCommandIntRequest(self, id, intvals):
        bytevals = []
        for val in intvals:
            for c in struct.pack('I', val):
                bytevals.append(ord(c))
        self._sendCommandRequest(id, 4*len(intvals), bytevals)       

    def _sendCommandRequest(self, id, n, contents):
        self._sendRequest(self.commandsock, 'O', id, n, contents)

    def _sendRequest(self, sock, c, id, n, contents):                  
        bytes = [ord('M'), ord('O'), ord('_'), ord(c), id, \
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, n, 0, 0, 0, 0, 0, 0, 0]
        
        bytes.extend(contents)
        request = ''.join(map(chr, bytes))
        sock.send(request)
        
    def _receiveCommandReply(self, count):
        reply = self.commandsock.recv(count)
        return reply
        
    def _newSocket(self):
        sock = socket.socket()
        sock.connect((self.HOST, self.PORT))
        return sock
    
# "Private" classes ===========================================================

        
# A special Blowfish variant with P-arrays set to zero instead of digits of Pi
class _RoverBlowfish(Blowfish):
    
    def __init__(self, key):
        
        ORIG_P = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

        self._keygen(key, ORIG_P)

# A thread for sending talk data to the Rover
class _TalkThread(threading.Thread):
    ''' This is a talk thread that can make the rover talk.
        In this example, a adpcm file is read. The adpcm file is created by the adpcm.py
        You can write your own thread.
        The protocal is shown below:
            
            --protocal header: MO_V
            --operation number : 3
            --text length: 180
            --text data length: 160
            --text content: 160 bytes ADPCM string plus 3 bytes.
              The three bytes are: two bytes for offsetsample(int16), one byte for index(int8)
    '''
    
    def __init__(self, rover):
        
        threading.Thread.__init__(self)
        self.rover = rover                        
          
    def run(self):
        
        tick = 0                #tick count number. 0,40,80,120...
        psn = 0                 #package serial number. 0,1,2,3,4... 
        s_offset = 0            #sample offset. Refreshed by the adpcm.py encodePCMToADPCM function.
        s_index = 0             #steptable index. Refreshed by the adpcm.py encodePCMToADPCM function
        wr_frame_pointer = 0    #string pointer in the adpcm file.
        ts = 0                  #timestamp
        
        # Read ADPCM data from this file
        adpcm_f = open('adpcm.txt','rb')
        
        adpcm_str = adpcm_f.read()
        
        adpcm_str_length = len(adpcm_str)
        
        final_request = ''
        
        # Starts True; set to False by Rover.close()
        while self.rover.is_active:
            
            if wr_frame_pointer+163 > adpcm_str_length:
                talk_string = ''.join(map(chr,[0]*163))
            else:
                # talk_string is a 163 bytes length string. 160 for data, 2 for offset, 1 for index
                talk_string = adpcm_str[wr_frame_pointer : wr_frame_pointer+163]
            
            intvals = [tick, psn, int(ts), 160]
            
            bytevals = []
            
            for intval in intvals:
                for c in struct.pack('I', intval):
                    bytevals.append(ord(c))
            bytevals.insert(12,0)
            
            bytes = [ord('M'), ord('O'), ord('_'), ord('V'), 3, \
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 180, 0, 0, 0, 0, 0, 0, 0]
            
            bytes.extend(bytevals)
            request = ''.join(map(chr, bytes))
            request += talk_string

            try:
            
                self.rover.mediasock.send(request)
                
                psn = psn + 1
            
                ts = time.time()
                
                tick = tick + 40
                
                # Here, because the ADPCM data are pre-written, so it's 163
                wr_frame_pointer = wr_frame_pointer + 163
                
                time.sleep(0.02)
                      
            except:
                
                print('error')
        
        self.rover.endTalk()
            

                
# A thread for reading streaming media from the Rover
class _MediaThread(threading.Thread):
    
    def __init__(self, rover):
        
        threading.Thread.__init__(self)
        
        self.rover = rover
        self.BUFSIZE = 1048576
        self.buf = ''
                        
          
    def run(self):
                            
        # Starts True; set to False by Rover.close()       
        while self.rover.is_active:
            
            # Grab bytes from rover, halting on failure            
            try:
                buf = self.rover.mediasock.recv(self.BUFSIZE)
                
            except:
                break
            
            
            self.buf +=buf
            
            if len(self.buf)>10000:
                
                k = self.buf.find('MO_V')
                
                if k>=0:
                    self.buf = self.buf[k:]
                    
                    
                    packs = self.buf.split('MO_V')
                    packs_length = len(packs)
                    pack_index = 0
                    
                    for pack in packs:
                        
                        if pack_index == packs_length-1:
                            self.buf = 'MO_V'+pack
                            break
                            
                        elif len(pack)>23:
                            pack_op = ord(pack[0])
                            
                            if pack_op == 1:
                                
                                video_length = bytes_to_int(pack,28)
                                video_actual_length = len(pack)-32
                                
                                if video_actual_length == video_length:
                                    self.rover.processVideo(pack[32:32+video_length])
                            
                            elif pack_op == 2:
                                
                                audio_length = bytes_to_int(pack,32)
                                audio_actual_length = len(pack)-36
                                
                                if audio_actual_length-3 == audio_length:
                                
                                    offset = bytes_to_short(pack, 196)
                                    index  = ord(pack[198])
                                    audiobytes = decodeADPCMToPCM(pack[36:196], offset, index)
                                    self.rover.processAudio(audiobytes)
                    
                        pack_index +=1

                
class _RoverTread:
    
    def __init__(self, rover, index):
        
        self.rover = rover
        self.index = index
        self.isMoving = False
        self.startTime = 0

    def update(self, value):

        if value == 0:
            if self.isMoving:
                self.rover._spinWheels(self.index, 0)
                self.isMoving = False
        else:
            if value > 0:
                wheel = self.index
            else:
                wheel = self.index + 1
            currTime = time.time()
            if (currTime - self.startTime) > self.rover.TREAD_DELAY_SEC:              
                self.startTime = currTime
                self.rover._spinWheels(wheel, int(round(abs(value)*10)))  
                self.isMoving = True
                
        