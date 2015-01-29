import rover
import cvutils
import time
import pygame
import sys
import signal
import numpy as np
import time


# Try to start OpenCV for video
try:
    import cv2
except:
    cv2 = None

# Handler passed to Rover constructor
class MediaRover(rover.Rover):
            
    def processVideo(self, jpegbytes):
                            
        try:
                    
            if cv2:
                
                ts=time.time();
                wname = 'Rover 2.0'
                nparr = np.fromstring(jpegbytes, np.uint8)
                img_np = cv2.imdecode(nparr, cv2.CV_LOAD_IMAGE_COLOR)
                cv2.namedWindow(wname, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(wname, 640, 480)
                cv2.imshow(wname,img_np)
                cv2.waitKey(5)
                
            else:
                pass
            
        except:
            info=sys.exc_info()  
            print info[0],":",info[1]
            pass
            
rover = MediaRover()

a = raw_input('Enter your input:')

if a=='q':
    
    rover.close()
    
elif a=='t':
    
    rover.startTalk(rover.MEDIA_PASS)

while True:
    pass

# Shut down Rover
rover.close()