#!/usr/bin/env python

'''
soundReceive.py Receive sound from rover then play it.

Copyright (C) 2014 Haosen Wang

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as 
published by the Free Software Foundation, either version 3 of the 
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
'''

import rover
import pyaudio
import wave
import sys
import time
import signal
import numpy
import struct

nchannels = 1
sampwidth = 2 #Sample is 16 bits (2 bytes)
framerate = 8000
nframes = 320
WAVE_OUTPUT_FILENAME = "output.wav"

p = pyaudio.PyAudio()

# pyaudio.paInt16

stream = p.open(format=pyaudio.paInt16,
                channels=nchannels,
                rate=framerate,
                output=True,
                frames_per_buffer = nframes)

                
                
print("* recording")
wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
wf.setnchannels(nchannels)
wf.setsampwidth(sampwidth)
wf.setframerate(framerate)
wf.setnframes(nframes)

# Overwrite the processAudio function
class AudioRover(rover.Rover):
    
    def __init__(self):
        rover.Rover.__init__(self)
            
    def processAudio(self, pcmsamples):
        
        newdata = []
        for x in pcmsamples:
            newdata.append(struct.pack('<h',x))
        
        data_string = ''.join(newdata)
        stream.write(data_string)
        
        # Save the audio to local data file
        wf.writeframes(data_string)
        
        # Output audio to your computer
        stream.write(pcmsamples)
        
rover = AudioRover()


while True:
    pass



# Shut down Rover
rover.close()


stream.close()

# close PyAudio 
p.terminate()