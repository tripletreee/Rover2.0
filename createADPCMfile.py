'''
A Python script for creating adpcm data files.  

'''

import pyaudio
import wave
from adpcm import *
import struct
import time

nchannels = 1
sampwidth = 2 #Sample is 16 bits (2 bytes)
framerate = 8000
nframes = 320

wr_frame_pointer = 0
s_offset = 0
s_index = 0

wr = wave.open('happy.wav', 'r')
wr_frame_length = wr.getnframes()
wr_frame_rate = wr.getframerate()
wr_para = wr.getparams()

print('para:',wr_para)

WAVE_OUTPUT_FILENAME = "pcm_adpcm_pcm.wav"
wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
wf.setnchannels(nchannels)
wf.setsampwidth(sampwidth)
wf.setframerate(framerate)
wf.setnframes(nframes)

p = pyaudio.PyAudio()

stream = p.open(format=pyaudio.paInt16,
                channels=nchannels,
                rate=framerate,
                output=True,
                frames_per_buffer = nframes)

        
wr_str = wr.readframes(wr_frame_length)

text_file = open('adpcm.txt','wb')

while wr_frame_pointer+640<wr_frame_length*2:
    
    talk_string = wr_str[wr_frame_pointer : wr_frame_pointer+640]
    
    adpcm = encodePCMToADPCM(talk_string, s_offset, s_index)
    
    s_offset_temp = adpcm[160]
    
    s_index_temp = adpcm[161]
    
    adpcm = adpcm[0:160]
    
    adpcm_str = ''.join(map(chr,adpcm))
    
    offset_index_str = ''
    
    offset_index_str = struct.pack('<h',s_offset_temp)
    
    offset_index_str += chr(s_index_temp)
    
    text_file.write(adpcm_str+offset_index_str)
    
    wr_frame_pointer += 640
    
    pcmsamples = decodeADPCMToPCM(adpcm_str, s_offset, s_index)
    
    s_offset = s_offset_temp
    
    s_index = s_index_temp
    
    newdata = []
    for x in pcmsamples:
        newdata.append(struct.pack('<h',x))
    
    data_string = ''.join(newdata)
    
    
    wf.writeframes(data_string)

    
wr.close()
wf.close()
text_file.close()
stream.close()
