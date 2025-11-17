#!/usr/bin/env python3

"""Example module for Hailo Detection."""

"""Copyright (c) 2025
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""

# v0.52

import argparse
import cv2
from picamera2 import MappedArray, Picamera2, Preview
from picamera2.devices import Hailo
from picamera2.encoders import H264Encoder
from picamera2.outputs import CircularOutput2, PyavOutput
from libcamera import controls
import time
import os
import glob
import datetime
from datetime import timedelta
import shutil
from gpiozero import LED
import pygame, sys
from pygame.locals import *

# detection objects
objects = ["cat","bear","dog"]

# shutdown time
sd_hour      = 0     # if sd_hour = 0 and sd_mins = 0 won't shutdown
sd_mins      = 0

# set variables
screen       = 1     # 1 = 1280 x 720, 2 = 800 x 480
show_detects = 1     # show detections, 1 = on stills, 2 = on video & stills, 0 = no
log          = 0     # set to 1 to make a log of detections in detect_log.txt
v_width      = 1088  # video width
v_height     = 1088  # video height
v_length     = 15    # seconds, minimum video length, minimum value 5
pre_frames   = 5     # seconds, defines length of pre-detection buffer, minimum value 1
fps          = 30    # video frame rate
mp4_timer    = 10    # seconds, move mp4s to SD Card after this time if no detections
mp4_anno     = 1     # show timestamps on video, 1 = yes, 0 = no
led          = 21    # recording led gpio
bitrate      = 10000000 # video bitrate

# default camera settings, note these will be overwritten if changed whilst running
mode         = 1     # camera mode,     0 to 3,  see modes below, 1 = normal
speed        = 1000  # manual shutter speed in mS
gain         = 0     # set camera gain, 0 to 64, 0 = auto
meter        = 2     # set meter mode,  0 to 2,  see meters below, 2 = matrix
brightness   = 0     # set brightness,  0 to 20
contrast     = 8     # set contrast,    0 to 20
ev           = 0     # set eV,        -20 to 20        
sharpness    = 10    # set sharpness    0 to 16
saturation   = 10    # set saturation   0 to 32
awb          = 0     # set awb mode     0 to 6,  see awbs below, 0 = auto
red          = 10    # set red,         1 to 80, only in awb custom mode
blue         = 10    # set blue,        1 to 80, only in awb custom mode
modes        = ['manual','normal','short','long']
meters       = ["Center","Spot","Matrix"]
awbs         = ['auto','tungsten','fluorescent','indoor','daylight','cloudy','custom']

# mp4_annotation parameters
colour       = (255, 255, 255)
origin       = (20, int(v_height - 25))
font         = cv2.FONT_HERSHEY_SIMPLEX
scale        = 1
thickness    = 2

# ram limit
ram_limit    = 150 # stops recording if ram below this

# setup screen parameters
if screen == 1: # 1280 x 720
    bw = 80  # button width
    bh = 40  # button height
    ft = 17  # font size
    rw = 480 # review width
    rh = 480 # review height
    cw = 640 # preview width
    ch = 640 # preview height
    ds = 10  # preview x position
    dg = 20  # gap to review window
    
else: # 800 x 480
    bw = 53
    bh = 30
    ft = 12
    rw = 320
    rh = 320
    cw = 480
    ch = 480
    ds = 0
    dg = 0

# set review window position
x = cw + ds + dg
y = 1
os.environ['SDL_VIDEO_WINDOW_POS'] = "%d,%d" % (x,y)
pygame.init()
windowSurfaceObj = pygame.display.set_mode((rw,ch),1, 24)
pygame.display.set_caption("Review Captures" )

# check Det_configXX.txt exists, if not then write default values
config_file = "Det_Config5.txt"
if not os.path.exists(config_file):
    defaults = [mode,speed,gain,meter,brightness,contrast,ev,sharpness,saturation,awb,red,blue,sd_hour,sd_mins,pre_frames,v_length]
    with open(config_file, 'w') as f:
        for item in defaults:
            f.write("%s\n" % item)

# read config file
defaults    = []
with open(config_file, "r") as file:
   line = file.readline()
   while line:
      defaults.append(line.strip())
      line = file.readline()
defaults = list(map(int,defaults))
mode       = defaults[0]
speed      = defaults[1]
gain       = defaults[2]
meter      = defaults[3]
brightness = defaults[4]
contrast   = defaults[5]
ev         = defaults[6]
sharpness  = defaults[7]
saturation = defaults[8]
awb        = defaults[9]
red        = defaults[10]/10
blue       = defaults[11]/10
sd_hour    = defaults[12]
sd_mins    = defaults[13]
pre_frames = defaults[14]
v_length   = defaults[15]

# define colors
global greyColor, dgryColor, whiteColor, redColor, greenColor,yellowColor,dredColor,blackColor
greyColor   = pygame.Color(130, 130, 130)
dgryColor   = pygame.Color( 64,  64,  64)
whiteColor  = pygame.Color(250, 250, 250)
redColor    = pygame.Color(200,   0,   0)
dredColor   = pygame.Color(130,   0,   0)
greenColor  = pygame.Color(  0, 255,   0)
yellowColor = pygame.Color(255, 255,   0)
blackColor  = pygame.Color(  0,   0,   0)

# draw a button
def button(col,row,bw,bh,bColor):
    global screen
    colors = [greyColor, dgryColor, whiteColor, redColor, greenColor,yellowColor,dredColor,blackColor]
    Color = colors[bColor]
    if screen == 2 and row > 12:
        row -= 1
    bx = col * bw
    by = row * bh
    pygame.draw.rect(windowSurfaceObj,Color,Rect(bx+1,by,bw-2,bh))
    pygame.draw.line(windowSurfaceObj,whiteColor,(bx,by),(bx,by+bh-1),2)
    pygame.draw.line(windowSurfaceObj,whiteColor,(bx,by),(bx+bw-1,by),1)
    pygame.draw.line(windowSurfaceObj,dgryColor,(bx,by+bh-1),(bx+bw-1,by+bh-1),1)
    pygame.draw.line(windowSurfaceObj,dgryColor,(bx+bw-2,by),(bx+bw-2,by+bh),2)
    pygame.display.update(bx, by, bw-1, bh)

# write text on a button
def text(col,row,line,bColor,msg):
    global bh,bw,ft,screen
    if screen == 2 and row > 11:
        row -= 1
    colors = [greyColor, dgryColor, whiteColor, redColor, greenColor,yellowColor,dredColor,blackColor]
    Color = colors[bColor]
    bx = col * bw
    by = (row * bh) + (line * int(ft/2))
    if row != 2:
        if msg ==   "Recording":
            pygame.draw.rect(windowSurfaceObj,(130,0,0),Rect(bx+2,by+2,bw - 4,ft))
        elif msg == "________":
            pygame.draw.rect(windowSurfaceObj,(130,0,0),Rect(bx+2,by+2,bw - 4,ft))
        elif (row == 12 and col == 0) or (row == 12 and col == 5) or row == 1:
            pygame.draw.rect(windowSurfaceObj,(10,0,0),Rect(bx+2,by+2,bw - 3,ft))
        else:
            pygame.draw.rect(windowSurfaceObj,(130,130,130),Rect(bx+2,by+2,bw - 4,ft))
    if (screen == 1 and col == 0 and row == 12) or (screen == 2 and col == 0 and row == 11):
        pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(bx+2,by+2,bw + 152,ft))
    if os.path.exists ('/usr/share/fonts/truetype/freefont/FreeSerif.ttf'):
        fontObj = pygame.font.Font('/usr/share/fonts/truetype/freefont/FreeSerif.ttf',ft)
    else:
        fontObj = pygame.font.Font(None,ft)
    msgSurfaceObj = fontObj.render(msg, False, (Color))
    msgRectobj = msgSurfaceObj.get_rect()
    msgRectobj.topleft = (bx + 5,by)
    windowSurfaceObj.blit(msgSurfaceObj, msgRectobj)
    pygame.display.update()

# initialise
Users  = []
Users.append(os.getlogin())
user     = Users[0]
h_user   = "/home/" + os.getlogin( )
m_user   = "/media/" + os.getlogin( )
start_up = time.monotonic()
startmp4 = time.monotonic()
pftimer  = time.monotonic()
rec_led  = LED(led)
rec_led.off()
p = 0
Pics = glob.glob(h_user + '/Pictures/*.jpg')
Pics.sort()
record = 0
sd_tim = (sd_hour * 60) + sd_mins

# check if clock synchronised
if "System clock synchronized: yes" in os.popen("timedatectl").read().split("\n"):
    synced = 1
else:
    synced = 0
    
# find camera version
def Camera_Version():
    global cam1
    if os.path.exists('/run/shm/libcams.txt'):
        os.rename('/run/shm/libcams.txt', '/run/shm/oldlibcams.txt')
    os.system("rpicam-vid --list-cameras >> /run/shm/libcams.txt")
    time.sleep(0.5)
    # read libcams.txt file
    camstxt = []
    with open("/run/shm/libcams.txt", "r") as file:
        line = file.readline()
        while line:
            camstxt.append(line.strip())
            line = file.readline()
    cam1 = camstxt[2][4:10]
Camera_Version()

# Draw Screen
for y in range(0,6):
    button(y,0,bw,bh,0)
    button(y,14,bw,bh,0)
    button(y,15,bw,bh,0)
if screen == 1:
    pygame.draw.rect(windowSurfaceObj,(130,130,130),Rect(0,rh + bh,rw,bh))
for y in range(1,5):
    button(y,13,bw,bh,0)

text(0,0,1,5,"< PREV")
text(0,1,1,5,"Initialising  ")
text(1,0,1,5,"NEXT >")
if len(Pics) > 0:
    text(4,0,0,5,"Show")
    text(4,0,2,5,"Video")
text(1,13,1,3,"RECORD")
text(0,14,0,5,"EV")
text(0,14,2,4,str(ev))
text(1,14,0,5,"Mode")
text(1,14,2,4,str(modes[mode]))
if cam1 != "ov9281":
    text(0,15,0,5,"Meter")
    text(0,15,2,4,str(meters[meter]))
    text(1,15,0,5,"Sharpness")
    text(1,15,2,4,str(sharpness))
    text(2,15,0,5,"Saturation")
    text(2,15,2,4,str(saturation))
    text(3,15,0,5,"AWB")
    text(3,15,2,4,str(awbs[awb]))
    if awb == 6:
        text(4,15,0,5,"Red")
        text(4,15,2,4,str(red)[0:3])
        text(5,15,0,5,"Blue")
        text(5,15,2,4,str(blue)[0:3])
if mode == 0:
    text(2,14,0,5,"Speed")
    text(2,14,2,4,str(speed))
text(3,14,0,5,"Gain")
if gain != 0:
    text(3,14,2,4,str(gain))
else:
    text(3,14,2,4,"Auto")
text(4,14,0,5,"Brightness")
text(4,14,2,4,str(brightness))
text(5,14,0,5,"Contrast")
text(5,14,2,4,str(contrast))
text(2,13,0,5,"Shutdown")
sd_tim = (sd_hour * 60) + sd_mins
sd_h = "0" + str(sd_hour)
sd_hr = sd_h[-2:]
sd_m = "0" + str(sd_mins)
sd_mn = sd_m[-2:]
if synced == 1 and sd_tim != 0:
    text(2,13,2,4,"   " + str(sd_hr) + ":" + str(sd_mn))
else:
    text(2,13,2,1,"   " + str(sd_hr) + ":" + str(sd_mn))
text(3,13,0,5,"Pre S")
text(3,13,2,4,str(pre_frames))
text(4,13,0,5,"Video S")
text(4,13,2,4,str(v_length))
time.sleep(10)

# show last captured image
if len(Pics) > 0:
    p = len(Pics) - 1
    image = pygame.image.load(Pics[p])
    image = pygame.transform.scale(image,(rw,rh))
    windowSurfaceObj.blit(image,(0,bh))
    text(0,13,1,4,str(p+1) + "/" + str(p+1))
    pic = Pics[p].split("/")
    pipc = h_user + '/Videos/' + pic[4][:-3] + "mp4"
    mp4 = pic[0] + "/" + pic[1] + "/" + pic[2] + "/Videos/" + pic[4][:-4] + ".mp4"
    cap1 = 0
    cap = cv2.VideoCapture(mp4)
    if not cap.isOpened():
        time.sleep(0.1)
    else:
        cap1 = 1
        fpsv = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = frame_count / fpsv if fpsv else 0
        cap.release()
        text(0,12,1,4,str(pic[4][:-4]) + ".mp4 : " + str(int(duration)) + "s")
    text(5,0,1,3,"DEL ALL")
    if os.path.exists(pipc):
        text(2,0,1,3,"DELETE")
        USB_Files  = []
        USB_Files  = (os.listdir(m_user))
        if len(USB_Files) > 0:
            text(3,0,1,4,"  to USB")
else:
    text(0,1,1,0,"            ")
    text(0,13,1,4,"0")
pygame.display.update()

def extract_detections(hailo_output, w, h, class_names, threshold=0.5):
    """Extract detections from the HailoRT-postprocess output."""
    results = []
    for class_id, detections in enumerate(hailo_output):
        for detection in detections:
            score = detection[4]
            if score >= threshold:
                y0, x0, y1, x1 = detection[:4]
                bbox = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
                results.append([class_names[class_id], bbox, score])
    return results

def draw_objects(request): # on video & stills
    global show_detects,v_width,v_height,model_w,model_h
    current_detections = detections
    if current_detections and show_detects == 2:
        with MappedArray(request, "main") as m:
            for class_name, bbox, score in current_detections:
                x0, y0, x1, y1 = bbox
                label = f"{class_name} %{int(score * 100)}"
                cv2.rectangle(m.array, (x0, y0), (x1, y1), (0, 255, 0, 0), 4)
                cv2.putText(m.array, label, (x0 + 5, y0 + 45),
                            cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0, 0), 3, cv2.LINE_AA)
                            
def draw_box(): # on stills only
    global show_detects,v_width,v_height,model_w,model_h,frame
    current_detections = detections
    if current_detections:
        for class_name, bbox, score in current_detections:
            x0, y0, x1, y1 = bbox
            x0 = int(x0 * (model_w/v_width))
            y0 = int(y0 * (model_h/v_height))
            x1 = int(x1 * (model_w/v_width))
            y1 = int(y1 * (model_h/v_height))
            label = f"{class_name} %{int(score * 100)}"
            cv2.rectangle(frame, (x0, y0), (x1, y1), (0, 255, 0, 0), 2)
            cv2.putText(frame, label, (x0 + 5, y0 + 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0, 0), 2, cv2.LINE_AA)

# apply timestamp to videos
def apply_timestamp(request):
  global mp4_anno
  if mp4_anno == 1:
      timestamp = time.strftime("%Y/%m/%d %T")
      with MappedArray(request, "main") as m:
          lst = list(origin)
          lst[0] += 365
          lst[1] -= 20
          end_point = tuple(lst)
          cv2.rectangle(m.array, origin, end_point, (0,0,0), -1) 
          cv2.putText(m.array, timestamp, origin, font, scale, colour, thickness)
       
# main loop
if __name__ == "__main__":

    # Get camera version
    Camera_Version()

    # Parse command-line arguments.
    parser = argparse.ArgumentParser(description="Detection Example")
    parser.add_argument("-m", "--model", help="Path for the HEF model.",
                        default="/usr/share/hailo-models/yolov8s_h8l.hef")
    parser.add_argument("-l", "--labels", default="/home/" + user + "/picamera2/examples/hailo/coco.txt",
                        help="Path to a text file containing labels.")
    parser.add_argument("-s", "--score_thresh", type=float, default=0.50,
                        help="Score threshold, must be a float between 0 and 1.")
    args = parser.parse_args()

    # Get the Hailo model, the input size it wants, and the size of our preview stream.
    with Hailo(args.model) as hailo:
        model_h, model_w, _ = hailo.get_input_shape()
        video_w, video_h    = v_width,v_height

        # Load class names from the labels file
        with open(args.labels, 'r', encoding="utf-8") as f:
            class_names = f.read().splitlines()

        # The list of detected objects to draw.
        detections = None

        # Configure and start Picamera2.
        with Picamera2() as picam2:
            main  = {'size': (video_w, video_h), 'format': 'XRGB8888'} 
            lores = {'size': (model_w, model_h), 'format': 'RGB888'}
            if cam1 == "imx708":
                controls2 = {'FrameRate': fps,"AfMode": controls.AfModeEnum.Continuous,"AfTrigger": controls.AfTriggerEnum.Start}
            else:
                controls2 = {'FrameRate': fps}
            config = picam2.create_preview_configuration(main, lores=lores, controls=controls2)
            picam2.configure(config)
            encoder = H264Encoder(bitrate)
            pref = pre_frames * 1000
            circular = CircularOutput2(buffer_duration_ms=pref)
            picam2.pre_callback = apply_timestamp
            picam2.start_preview(Preview.QTGL, x=ds, y=1, width=cw, height=ch)
            picam2.title_fields = ["ExposureTime"]
            picam2.start_recording(encoder, circular)
            encoding = False
            if show_detects == 2:
                picam2.pre_callback = draw_objects
            picam2.set_controls({"AnalogueGain": gain})
            picam2.set_controls({"Brightness": brightness/10})
            picam2.set_controls({"Contrast": contrast/10})
            picam2.set_controls({"ExposureValue": ev/10})
            if cam1 != "ov9281":
              picam2.set_controls({"Sharpness": sharpness})
              picam2.set_controls({"Saturation": saturation/10})
              if awb == 0:
                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Auto})
              elif awb == 1:
                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Tungsten})
              elif awb == 2:
                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Fluorescent})
              elif awb == 3:
                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Indoor})
              elif awb == 4:
                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Daylight})
              elif awb == 5:
                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Cloudy})
              elif awb == 6:
                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Custom})
                cg = (red,blue)
                picam2.set_controls({"AwbEnable": False,"ColourGains": cg})
              if meter == 0:
                picam2.set_controls({"AeMeteringMode": controls.AeMeteringModeEnum.CentreWeighted})
              elif meter == 1:
                picam2.set_controls({"AeMeteringMode": controls.AeMeteringModeEnum.Spot})
              elif meter == 2:
                picam2.set_controls({"AeMeteringMode": controls.AeMeteringModeEnum.Matrix})
            if mode == 0:
                picam2.set_controls({"AeEnable": False,"ExposureTime": speed})
            else:
                if mode == 1:
                    picam2.set_controls({"AeEnable": True,"AeExposureMode": controls.AeExposureModeEnum.Normal})
                elif mode == 2:
                    picam2.set_controls({"AeEnable": True,"AeExposureMode": controls.AeExposureModeEnum.Short})
                elif mode == 3:
                    picam2.set_controls({"AeEnable": True,"AeExposureMode": controls.AeExposureModeEnum.Long})
            sta = time.monotonic()
            # Process each low resolution camera frame.
            while True:
                # Get free ram space
                st = os.statvfs("/run/shm/")
                freeram = (st.f_bavail * st.f_frsize)/1100000
                
                # Capture frame
                frame = picam2.capture_array('lores')

                # Run inference on the preprocessed frame
                results = hailo.run(frame)
                
                # Extract detections from the inference results
                detections = extract_detections(results, video_w, video_h, class_names, args.score_thresh)
                
                # detection
                for d in range(0,len(objects)):
                    if len(detections) != 0 or record == 1:
                        if len(detections) != 0:
                            value = float(detections[0][2])
                            obj = detections[0][0]
                        else:
                            value = 0
                            obj = "manual"
                            objects[d] = "manual"
                        if (value > args.score_thresh and value < 1 and obj == objects[d]) or record == 1:
                            startrec = time.monotonic()
                            startmp4 = time.monotonic()
                            record = 0
                            if show_detects == 1:
                                draw_box()
                            text(5,13,1,6,"________")
                            text(5,13,2,6,"________")
                            text(5,13,0,5,"Recording")
                            if log == 1:
                                now = datetime.datetime.now()
                                timestamp = now.strftime("%y%m%d_%H%M%S")
                                with open("detect_log.txt", 'a') as f:
                                    f.write(timestamp + " " + objects[d] + "\n" )
                            # start recording
                            if not encoding and freeram > ram_limit:
                                sta = time.monotonic()
                                now = datetime.datetime.now()
                                timestamp = now.strftime("%y%m%d_%H%M%S")
                                circular.open_output(PyavOutput("/run/shm/" + timestamp +".mp4"))
                                encoding = True
                                print("New  Detection",timestamp + " " + objects[d])
                                rec_led.on()
                                # save lores image
                                cv2.imwrite(h_user + "/Pictures/" + str(timestamp) + ".jpg",frame)
                                # show captured lores trigger image
                                Pics = glob.glob(h_user + '/Pictures/*.jpg')
                                Pics.sort()
                                p = len(Pics) - 1
                                img = cv2.cvtColor(frame,cv2.COLOR_RGB2BGR)
                                image = pygame.surfarray.make_surface(img)
                                image = pygame.transform.scale(image,(rw,rh))
                                image = pygame.transform.rotate(image,int(90))
                                image = pygame.transform.flip(image,0,1)
                                windowSurfaceObj.blit(image,(0,bh))
                                text(0,13,1,4,str(p+1) + "/" + str(p+1))
                                pic = Pics[p].split("/")
                                text(0,12,1,4,str(pic[4]))
                                pygame.display.update()
            
                if encoding:
                    td = timedelta(seconds=int(time.monotonic()-sta))
                    text(5,13,2,5,str(td))

                # stop recording, if time out or low RAM
                if encoding and (time.monotonic() - startrec > v_length + pre_frames or freeram <= ram_limit):
                    now = datetime.datetime.now()
                    timestamp2 = now.strftime("%y%m%d_%H%M%S")
                    print("Stopped Record", timestamp2)
                    circular.close_output()
                    encoding = False
                    startmp4 = time.monotonic()
                    rec_led.off()
                    text(0,12,1,4,str(pic[4][:-4] + ".mp4"))
                    text(5,13,1,4,"          ")
                    text(5,13,0,4,"          ")
                    text(5,13,2,4,"          ")

                # move mp4s
                if time.monotonic() - startmp4 > mp4_timer and not encoding:
                    startmp4 = time.monotonic()
                    # move Video RAM mp4s to SD card
                    Videos = glob.glob('/run/shm/*.mp4')
                    Videos.sort()
                    for xx in range(0,len(Videos)):
                        if not os.path.exists(h_user + "/" + '/Videos/' + Videos[xx]):
                            shutil.move(Videos[xx], h_user + '/Videos/')
                    Pics = glob.glob(h_user + '/Pictures/*.jpg')
                    Pics.sort()
                    if len(Pics) > 0:
                        pic = Pics[p].split("/")
                        pipc = h_user + '/Videos/' + pic[4][:-3] + "mp4"
                        text(0,13,1,4,str(p+1) + "/" + str(len(Pics)))
                        pic = Pics[p].split("/")
                        mp4 = pic[0] + "/" + pic[1] + "/" + pic[2] + "/Videos/" + pic[4][:-4] + ".mp4"
                        cap = cv2.VideoCapture(mp4)
                        if not cap.isOpened():
                            text(0,12,1,4,str(pic[4]))
                        else:
                            fpsv = cap.get(cv2.CAP_PROP_FPS)
                            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                            duration = frame_count / fpsv if fpsv else 0
                            cap.release()
                            text(0,12,1,4,str(pic[4][:-4]) + ".mp4 : " + str(int(duration)) + "s")
                        text(5,0,1,3,"DEL ALL")
                        if os.path.exists(pipc):
                            text(2,0,1,3,"DELETE")
                            if len(Pics) > 0:
                                text(4,0,0,5,"Show")
                                text(4,0,2,5,"Video")
                            USB_Files  = []
                            USB_Files  = (os.listdir(m_user))
                            if len(USB_Files) > 0:
                                text(3,0,1,4,"  to USB")
                        else:
                            text(2,0,1,3,"    ")
                            text(3,0,1,4,"    ")
                            text(4,0,0,5,"    ")
                            text(4,0,2,5,"     ")
                    else:
                        text(2,0,1,3,"    ")
                        text(5,0,1,3,"    ")
                        text(3,0,1,4,"    ")
                        text(4,0,0,5,"    ")
                        text(4,0,2,5,"     ")
                        
                    # auto time shutdown
                    if sd_tim != 0:
                        # check if clock synchronised
                        if "System clock synchronized: yes" in os.popen("timedatectl").read().split("\n"):
                            synced = 1
                        else:
                            synced = 0
                        sd_h = "0" + str(sd_hour)
                        sd_hr = sd_h[-2:]
                        sd_m = "0" + str(sd_mins)
                        sd_mn = sd_m[-2:]
                        if synced == 1:
                            text(2,13,2,4,"   " + str(sd_hr) + ":" + str(sd_mn))
                        else:
                            text(2,13,2,1,"   " + str(sd_hr) + ":" + str(sd_mn))
                        # check current hour and shutdown
                        now = datetime.datetime.now()
                        sd_time = now.replace(hour=sd_hour, minute=sd_mins, second=0, microsecond=0)
                        if now >= sd_time and time.monotonic() - start_up > 300: # and synced == 1:
                            # move jpgs and mp4s to USB if present
                            time.sleep(2 * mp4_timer)
                            USB_Files  = []
                            USB_Files  = (os.listdir(m_user))
                            if len(USB_Files) > 0:
                                usedusb = os.statvfs(m_user + "/" + USB_Files[0] + "/")
                                USB_storage = ((1 - (usedusb.f_bavail / usedusb.f_blocks)) * 100)
                            if len(USB_Files) > 0 and USB_storage < 90:
                                Videos = glob.glob(h_user + '/Videos/*.mp4')
                                Videos.sort()
                                for xx in range(0,len(Videos)):
                                    movi = Videos[xx].split("/")
                                    if not os.path.exists(m_user + "/" + USB_Files[0] + "/Videos/" + movi[4]):
                                        shutil.move(Videos[xx],m_user + "/" + USB_Files[0] + "/Videos/")
                                Pics = glob.glob(h_user + '/Pictures/*.jpg')
                                Pics.sort()
                                for xx in range(0,len(Pics)):
                                    pic = Pics[xx].split("/")
                                    if not os.path.exists(m_user + "/" + USB_Files[0] + "/Pictures/" + pic[4]):
                                        shutil.move(Pics[xx],m_user + "/" + USB_Files[0] + "/Pictures/")
                            time.sleep(5)
                            # shutdown
                            print("SHUTDOWN")
                            os.system("sudo shutdown -h now")

                #check for any mouse button presses
                for event in pygame.event.get():
                    if (event.type == MOUSEBUTTONUP):
                        mousex, mousey = event.pos
                        brow = int(mousey/bh)
                        hcol = mousex/bw
                        bcol = int(hcol)
                        h = 0
                        if (hcol - bcol) > 0.5:
                            h = 1
                        if screen == 2 and brow > 11:
                            brow +=1
    
                        # RECORD VIDEO    
                        if bcol == 1 and brow == 13:
                            if event.button == 3:
                                record = 1
                                
                        elif bcol == 2 and brow == 13:
                            # SHUTDOWN TIME
                            if (h == 0 and event.button == 3) or (h == 0 and event.button == 4):
                                sd_hour +=1
                                if sd_hour > 23:
                                    sd_hour = 0
                            elif (h == 0 and event.button == 1)  or (h == 0 and event.button == 5):
                                sd_hour -=1
                                if sd_hour < 0:
                                    sd_hour = 23
                            elif (h == 1 and event.button == 5) or (h == 1 and event.button == 1):
                                sd_mins -=1
                                if sd_mins  < 0:
                                    sd_hour -= 1
                                    sd_mins = 59
                                    if sd_hour < 0:
                                        sd_hour = 23
                            elif h == 1 or (h == 1 and event.button == 3):
                                sd_mins +=1
                                if sd_mins > 59:
                                    sd_mins = 0
                                    sd_hour += 1
                                    if sd_hour > 23:
                                        sd_hour = 0
                            sd_h = "0" + str(sd_hour)
                            sd_hr = sd_h[-2:]
                            sd_m = "0" + str(sd_mins)
                            sd_mn = sd_m[-2:]
                            sd_tim = (sd_hour * 60) + sd_mins
                            if synced == 1 and sd_tim != 0:
                                text(2,13,2,4,"   " + str(sd_hr) + ":" + str(sd_mn))
                            else:
                                text(2,13,2,1,"   " + str(sd_hr) + ":" + str(sd_mn))
                                                        
                        # Pre Frames
                        elif bcol == 3 and brow == 13:
                            if event.button == 3 or event.button == 4:
                                pre_frames +=1
                            else:
                                pre_frames -=1
                                pre_frames = max(pre_frames,1)
                            text(3,13,2,1,str(pre_frames))
                            picam2.stop_recording()
                            circular = CircularOutput2(buffer_duration_ms=pref)
                            picam2.start_recording(encoder, circular)
                            #time.sleep(pre_frames)
                            text(3,13,2,4,str(pre_frames))
                            
                        # Video length
                        elif bcol == 4 and brow == 13:
                            if event.button == 3 or event.button == 4:
                                v_length +=1
                            else:
                                v_length -=1
                                v_length = max(v_length,5)
                            text(4,13,2,4,str(v_length))
                                                    
                        # camera control
                        # EV
                        elif bcol == 0 and brow == 14:
                            if event.button == 3 or event.button == 4:
                                ev +=1
                                ev = min(ev,20)
                            else:
                                ev -=1
                                ev = max(ev,-20)
                            picam2.set_controls({"ExposureValue": ev/10})
                            text(0,14,0,5,"EV")
                            text(0,14,2,4,str(ev))
                    
                        # MODE
                        elif bcol == 1 and brow == 14:
                            if event.button == 3 or event.button == 4:
                                mode +=1
                                if mode > 3:
                                    mode = 0
                            else:
                                mode -=1
                                if mode < 0:
                                    mode = 3
                                
                            text(1,14,2,4,str(modes[mode]))
                            if mode == 0:
                                picam2.set_controls({"AeEnable": False,"ExposureTime": speed,"AnalogueGain": gain})
                                text(2,14,0,5,"Speed")
                                text(2,14,2,4,str(speed))
                            else:
                                if mode == 1:
                                    picam2.set_controls({"AeEnable": True,"AeExposureMode": controls.AeExposureModeEnum.Normal,"AnalogueGain": gain})
                                elif mode == 2:
                                    picam2.set_controls({"AeEnable": True,"AeExposureMode": controls.AeExposureModeEnum.Short,"AnalogueGain": gain})
                                elif mode == 3:
                                    picam2.set_controls({"AeEnable": True,"AeExposureMode": controls.AeExposureModeEnum.Long,"AnalogueGain": gain})
                                text(2,14,0,5," ")
                                text(2,14,2,4," ")
                                
                        # METER MODE
                        elif bcol == 0 and brow == 15 and cam1 != "ov9281":
                            if event.button == 3 or event.button == 4:
                                meter += 1
                                if meter > 2:
                                    meter = 0
                            else:
                                meter -= 1
                                if meter < 0:
                                    meter = 2
                            if meter == 0:
                                picam2.set_controls({"AeMeteringMode": controls.AeMeteringModeEnum.CentreWeighted})
                            elif meter == 1:
                                picam2.set_controls({"AeMeteringMode": controls.AeMeteringModeEnum.Spot})
                            elif meter == 2:
                                 picam2.set_controls({"AeMeteringMode": controls.AeMeteringModeEnum.Matrix})
                            text(0,15,2,4,str(meters[meter]))
                            
                        # SHUTTER SPEED
                        elif bcol == 2 and brow == 14 and mode == 0:
                            if event.button == 3 or event.button == 4:
                                speed += 1000
                                speed = min(100000,speed)
                            else:
                                speed -=1000
                                speed = max(1000,speed)
                            picam2.set_controls({"AeEnable": False,"ExposureTime": speed,"AnalogueGain": gain})
                            text(2,14,2,4,str(speed))
                            
                        # GAIN
                        elif bcol == 3 and brow == 14:
                            if event.button == 3 or event.button == 4:
                                gain +=1
                                gain = min(64,gain)
                            else:
                                gain -=1
                                gain = max(0,gain)
                            picam2.set_controls({"AnalogueGain": gain})
                            if gain != 0:
                                text(3,14,2,4,str(gain))
                            else:
                                text(3,14,2,4,"Auto")
                                
                        # BRIGHTNESS        
                        elif bcol == 4 and brow == 14:
                            if event.button == 3 or event.button == 4:
                                brightness +=1
                                brightness = min(brightness,20)
                            else:
                                brightness -=1
                                brightness = max(brightness,0)
                            picam2.set_controls({"Brightness": brightness/10})
                            text(4,14,2,4,str(brightness))
                        
                        # CONTRAST
                        elif bcol == 5 and brow == 14:
                            if event.button == 3 or event.button == 4:
                                contrast +=1
                                contrast = min(contrast,20)
                            else:
                                contrast -=1
                                contrast = max(contrast,0)
                            picam2.set_controls({"Contrast": contrast/10})
                            text(5,14,2,4,str(contrast))
                            
                        # SHARPNESS    
                        elif bcol == 1 and brow == 15 and cam1 != "ov9281":
                            if event.button == 3 or event.button == 4:
                                sharpness +=1
                                sharpness = min(sharpness,16)
                            else:
                                sharpness -=1
                                sharpness = max(sharpness,0)
                            picam2.set_controls({"Sharpness": sharpness})
                            text(1,15,2,4,str(sharpness))
                        
                        # SATURATION
                        elif bcol == 2 and brow == 15 and cam1 != "ov9281":
                            if event.button == 3 or event.button == 4:
                                saturation +=1
                                saturation = min(saturation,32)
                            else:
                                saturation -=1
                                saturation = max(saturation,0)
                            picam2.set_controls({"Saturation": saturation/10})
                            text(2,15,2,4,str(saturation))
                        
                        # AWB setting    
                        elif bcol == 3 and brow == 15 and cam1 != "ov9281":
                            if event.button == 3 or event.button == 4:
                                awb +=1
                                awb = min(awb,len(awbs)-1)
                            else:
                                awb -=1
                                awb = max(awb,0)
                            if awb == 0:
                                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Auto})
                            elif awb == 1:
                                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Tungsten})
                            elif awb == 2:
                                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Fluorescent})
                            elif awb == 3:
                                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Indoor})
                            elif awb == 4:
                                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Daylight})
                            elif awb == 5:
                                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Cloudy})
                            elif awb == 6:
                                picam2.set_controls({"AwbEnable": True,"AwbMode": controls.AwbModeEnum.Custom})
                                cg = (red,blue)
                                picam2.set_controls({"AwbEnable": False,"ColourGains": cg})
                            text(3,15,2,4,str(awbs[awb]))
                            if awb == 6:
                                text(4,15,0,5,"Red")
                                text(5,15,0,5,"Blue")
                                text(4,15,2,4,str(red)[0:3])
                                text(5,15,2,4,str(blue)[0:3])
                            else:
                                text(4,15,0,5,"   ")
                                text(5,15,0,5,"    ")
                                text(4,15,2,4,"    ")
                                text(5,15,2,4,"    ")
                        # RED
                        elif bcol == 4 and brow == 15 and awb == 6:
                            if event.button == 3 or event.button == 4:
                                red +=0.1
                                red = min(red,8)
                            else:
                                red -=0.1
                                red = max(red,0.1)
                            cg = (red,blue)
                            picam2.set_controls({"ColourGains": cg})
                            text(4,15,2,4,str(red)[0:3])
                            text(5,15,2,4,str(blue)[0:3])
                        
                        # BLUE
                        elif bcol == 5 and brow == 15 and awb == 6:
                            if event.button == 3 or event.button == 4:
                                blue +=0.1
                                blue = min(blue,8)
                            else:
                                blue -=0.1
                                blue = max(blue,0.1)
                            cg = (red,blue)
                            picam2.set_controls({"ColourGains": cg})
                            text(4,15,2,4,str(red)[0:3])
                            text(5,15,2,4,str(blue)[0:3])
                            
                        # show previous
                        elif bcol == 0 and brow == 0:
                            Pics = glob.glob(h_user + '/Pictures/*.jpg')
                            Pics.sort()
                            p -= 1
                            if p < 0:
                                p = 0
                            if len(Pics) > 0:
                                image = pygame.image.load(Pics[p])
                                image = pygame.transform.scale(image,(rw,rh))
                                windowSurfaceObj.blit(image,(0,bh))
                                pygame.display.update()
                                
                        # show next
                        elif bcol == 1 and brow == 0:
                            Pics = glob.glob(h_user + '/Pictures/*.jpg')
                            Pics.sort()
                            p += 1
                            if p > len(Pics)-1:
                                p = len(Pics)-1
                            if len(Pics) > 0:
                                image = pygame.image.load(Pics[p])
                                image = pygame.transform.scale(image,(rw,rh))
                                windowSurfaceObj.blit(image,(0,bh))
                                pygame.display.update()
                                
                        # delete picture and video
                        elif bcol == 2 and brow == 0 and event.button == 3:
                            pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,bh,rw,rh))
                            Pics = glob.glob(h_user + '/Pictures/*.jpg')
                            Pics.sort()
                            Videos = glob.glob(h_user + '/Videos/*.mp4')
                            Videos.sort()
                            if len(Pics) > 0:
                                pic = Pics[p].split("/")
                                pipc = h_user + '/Videos/' + pic[4][:-3] + "mp4"
                                if os.path.exists(pipc):
                                   os.remove(Pics[p])
                                   if len(Videos) > 0:
                                       os.remove(pipc)
                                       print("DELETED", pipc)
                                Videos = glob.glob(h_user + '/Videos/*.mp4')
                                Videos.sort()
                                Pics = glob.glob(h_user + '/Pictures/*.jpg')
                                Pics.sort()
                            if p > len(Pics) - 1:
                                p -= 1
                            if len(Pics) > 0:
                                image = pygame.image.load(Pics[p])
                                image = pygame.transform.scale(image,(rw,rh))
                                windowSurfaceObj.blit(image,(0,bh))
                            pygame.display.update()
                            
                        # delete ALL Pictures and Videos
                        elif bcol == 5 and brow == 0 and event.button == 3:
                            Videos = glob.glob(h_user + '/Videos/*.mp4')
                            Videos.sort()
                            for w in range(0,len(Videos)):
                                os.remove(Videos[w])
                            Pics = glob.glob(h_user + '/Pictures/*.jpg')
                            Pics.sort()
                            for w in range(0,len(Pics)):
                                os.remove(Pics[w])
                            pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,bh,rw,rh))
                            p = 0
                            text(2,0,1,3,"    ")
                            text(5,0,1,3,"    ")
                            text(3,0,1,4,"    ")
                            text(4,0,0,5,"    ")
                            text(4,0,2,5,"     ")
                            
                        # move picture and video to USB
                        elif bcol == 3 and brow == 0 and event.button != 3:
                            pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,40,rw,rh))
                            Pics = glob.glob(h_user + '/Pictures/*.jpg')
                            Pics.sort()
                            Videos = glob.glob(h_user + '/Videos/*.mp4')
                            Videos.sort()
                            if len(Pics) > 0:
                              try:
                                pic = Pics[p].split("/")
                                pipc = h_user + '/Videos/' + pic[4][:-3] + "mp4"
                                # move mp4s to USB if present, and less than 90% full
                                USB_Files  = []
                                USB_Files  = (os.listdir(m_user))
                                if len(USB_Files) > 0:
                                    text(3,0,1,3,"  to USB")
                                    if not os.path.exists(m_user + "/'" + USB_Files[0] + "'/Videos/") :
                                        os.system('mkdir ' + m_user + "/'" + USB_Files[0] + "'/Videos/")
                                    if not os.path.exists(m_user + "/'" + USB_Files[0] + "'/Pictures/") :
                                        os.system('mkdir ' + m_user + "/'" + USB_Files[0] + "'/Pictures/")
                                    usedusb = os.statvfs(m_user + "/" + USB_Files[0] + "/")
                                    USB_storage = ((1 - (usedusb.f_bavail / usedusb.f_blocks)) * 100)
                                    print(USB_storage)
                                if len(USB_Files) > 0 and USB_storage < 90 and os.path.exists(pipc):
                                    if not os.path.exists(m_user + "/" + USB_Files[0] + "/Pictures/" + pic[4]):
                                        shutil.move(Pics[p],m_user + "/" + USB_Files[0] + "/Pictures/")
                                    if os.path.exists(pipc):
                                        vid = pipc.split("/")
                                        if not os.path.exists(m_user + "/" + USB_Files[0] + "/Videos/" + vid[4]):
                                            shutil.move(Videos[p],m_user + "/" + USB_Files[0] + "/Videos/")
                                    
                                Videos = glob.glob(h_user + '/Videos/*.mp4')
                                Videos.sort()
                                Pics = glob.glob(h_user + '/Pictures/*.jpg')
                                Pics.sort()
                                if len(Pics) > 0 and len(USB_Files) > 0:
                                    text(3,0,1,4,"  to USB")
                              except:
                                pass
                            if p > len(Pics) - 1:
                                p -= 1
                            if len(Pics) > 0:
                                image = pygame.image.load(Pics[p])
                                image = pygame.transform.scale(image,(rw,rh))
                                windowSurfaceObj.blit(image,(0,bh))

                            pygame.display.update()
                            
                        # move ALL pictures and videos to USB
                        elif bcol == 3 and brow == 0 and event.button == 3:
                            Pics = glob.glob(h_user + '/Pictures/*.jpg')
                            Pics.sort()
                            Videos = glob.glob(h_user + '/Videos/*.mp4')
                            Videos.sort()
                            if len(Pics) > 0 or len(Videos) > 0:
                              try:
                                # move mp4s and jpgs to USB if present, and USB storage < 90% full
                                USB_Files  = []
                                USB_Files  = (os.listdir(m_user))
                                if len(USB_Files) > 0:
                                    text(3,0,1,3,"  to USB")
                                    # make directories (if required)
                                    if not os.path.exists(m_user + "/'" + USB_Files[0] + "'/Videos") :
                                        os.system('mkdir ' + m_user + "/'" + USB_Files[0] + "'/Videos")
                                    if not os.path.exists(m_user + "/'" + USB_Files[0] + "'/Pictures") :
                                        os.system('mkdir ' + m_user + "/'" + USB_Files[0] + "'/Pictures")
                                    usedusb = os.statvfs(m_user + "/" + USB_Files[0] + "/")
                                    USB_storage = ((1 - (usedusb.f_bavail / usedusb.f_blocks)) * 100)
                                if len(USB_Files) > 0 and USB_storage < 90:
                                    for w in range(0,len(Videos)):
                                        text(0,13,1,4,str(w+1) + "/" + str(len(Videos)))
                                        vid = Videos[w].split("/")
                                        image = pygame.image.load("/" + vid[1] + "/" + vid[2] + "/Pictures/" + vid[4][:-3] + "jpg")
                                        image = pygame.transform.scale(image,(rw,rh))
                                        windowSurfaceObj.blit(image,(0,bh))
                                        pygame.display.update()
                                        if not os.path.exists(m_user + "/" + USB_Files[0] + "/Videos/" + vid[4]):
                                            shutil.move(Videos[w],m_user + "/" + USB_Files[0] + "/Videos/")
                                    for w in range(0,len(Pics)):
                                        pic = Pics[w].split("/")
                                        if not os.path.exists(m_user + "/" + USB_Files[0] + "/Pictures/" + pic[4]):
                                            shutil.move(Pics[w],m_user + "/" + USB_Files[0] + "/Pictures/")
                                    text(3,0,1,4,"  to USB")
                                Videos = glob.glob(h_user + '/Videos/*.mp4')
                                Videos.sort()
                                Pics = glob.glob(h_user + '/Pictures/*.jpg')
                                Pics.sort()
                              except:
                                  pass
                                
                            if p > len(Pics) - 1:
                                p -= 1
                            pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,bh,rw,rh))
                            if len(Pics) > 0:
                                image = pygame.image.load(Pics[p])
                                image = pygame.transform.scale(image,(rw,rh))
                                windowSurfaceObj.blit(image,(0,bh))
                            pygame.display.update()

                        # MAKE FULL MP4
                        elif bcol == 0 and brow == 1 and event.button == 3:
                          if os.path.exists('mylist.txt'):
                              os.remove('mylist.txt')
                          Videos = glob.glob(h_user + '/Videos/******_******.mp4')
                          Rideos = glob.glob('/run/shm/*.mp4')
                          for x in range(0,len(Rideos)):
                              Videos.append(Rideos[x])
                          for w in range(0,len(Videos)):
                              if Videos[w][:-5] == "f.mp4":
                                  os.remove(Videos[w])
                          Videos.sort()
                          if len(Videos) > 0:
                              frame = 0
                              if os.path.exists('mylist.txt'):
                                os.remove('mylist.txt')
                              for w in range(0,len(Videos)):
                                if Videos[w][len(Videos[w]) - 5:] != "f.mp4":
                                    txt = "file " + Videos[w]
                                    with open('mylist.txt', 'a') as f:
                                        f.write(txt + "\n")
                                    if os.path.exists(h_user + '/Videos/' + Videos[w] + ".jpg"):
                                        image = pygame.image.load( h_user + '/Videos/' + Videos[w] + ".jpg")
                                    elif os.path.exists('/run/shm/' + Videos[w] + ".jpg"):
                                        image = pygame.image.load('/run/shm/' + Videos[w] + ".jpg")
                                    nam = Videos[0].split("/")
                                    outfile = h_user + '/Videos/' + str(nam[len(nam)-1])[:-4] + "f.mp4"
                              if not os.path.exists(outfile):
                                os.system('ffmpeg -f concat -safe 0 -i mylist.txt -c copy ' + outfile)
                                # delete individual MP4s leaving the FULL MP4 only.
                                # read mylist.txt file
                                txtconfig = []
                                with open('mylist.txt', "r") as file:
                                    line = file.readline()
                                    line2 = line.split(" ")
                                    while line:
                                        txtconfig.append(line2[1].strip())
                                        line = file.readline()
                                        line2 = line.split(" ")
                                for x in range(0,len(txtconfig)):
                                    if os.path.exists(txtconfig[x] ) and txtconfig[x][len(txtconfig[x]) - 5:] != "f.mp4":
                                        os.remove(txtconfig[x] )
                                while not os.path.exists(outfile):
                                    time.sleep(0.1)
                                os.rename (h_user + '/Videos/' + str(nam[len(nam)-1])[:-4] + "f.mp4",h_user + '/Videos/' + str(nam[len(nam)-1])[:-4] + ".mp4")
                                Pics = glob.glob(h_user + '/Pictures/*.jpg')
                                for x in range(0,len(Pics)):
                                    if Pics[x] != h_user + '/Pictures/' + str(nam[len(nam)-1])[:-4] + ".jpg":
                                        os.remove(Pics[x])
                                p = 0
                                txtvids = []
                                #move MP4 to usb (if present)
                                USB_Files  = []
                                USB_Files  = (os.listdir(m_user))
                                if len(USB_Files) > 0:
                                    if not os.path.exists(m_user + "/'" + USB_Files[0] + "'/Videos/") :
                                        os.system('mkdir ' + m_user + "/'" + USB_Files[0] + "'/Videos/")
                                    Videos = glob.glob(h_user + '/Videos/******_******.mp4')
                                    Videos.sort()
                                    for xx in range(0,len(Videos)):
                                        movi = Videos[xx].split("/")
                                        if os.path.exists(m_user + "/" + USB_Files[0] + "/Videos/" + movi[4]):
                                            os.remove(m_user + "/" + USB_Files[0] + "/Videos/" + movi[4])
                                        shutil.copy(Videos[xx],m_user + "/" + USB_Files[0] + "/Videos/")
                                        if os.path.exists(m_user + "/" + USB_Files[0] + "/Videos/" + movi[4]):
                                             os.remove(Videos[xx])
                                             Pics = glob.glob(h_user + '/Pictures/*.jpg')
                                             for x in range(0,len(Pics)):
                                                 os.remove(Pics[x])
                       
                              Videos = glob.glob(h_user + '/Videos/******_******.mp4')
                              USB_Files  = (os.listdir(m_user))
                              Videos.sort()
                              w = 0
                              USB_Files  = (os.listdir(m_user))
                              if len(USB_Files) > 0:
                                  usedusb = os.statvfs(m_user + "/" + USB_Files[0] + "/")
                                  USB_storage = ((1 - (usedusb.f_bavail / usedusb.f_blocks)) * 100)
                                  
                        # Capture Screenshot
                        elif bcol == 4 and brow == 0 and event.button == 3:
                            os.system('grim')
                        
                        # Show Video
                        elif bcol == 4 and brow == 0 and event.button != 3 and len(Pics) > 0:
                            Videos = glob.glob(h_user + '/Videos/******_******.mp4')
                            Videos.sort()
                            pic = Pics[p].split("/")
                            vid = "/"+ pic[1] + "/" + pic[2] + "/Videos/" + pic[4][:-4] + ".mp4"
                            if os.path.exists(vid):
                               os.system("vlc " + vid)
                        Videos = glob.glob(h_user + '/Videos/******_******.mp4')
                        Videos.sort()
                        Pics = glob.glob(h_user + '/Pictures/*.jpg')
                        Pics.sort()
                        if len(Pics) > 0:
                            pic = Pics[p].split("/")
                            pipc = h_user + '/Videos/' + pic[4][:-3] + "mp4"
                            text(5,0,1,3,"DEL ALL")
                            if os.path.exists(pipc):
                                text(2,0,1,3,"DELETE")
                                USB_Files  = []
                                USB_Files  = (os.listdir(m_user))
                                if len(USB_Files) > 0:
                                    text(3,0,1,4,"  to USB")
                            else:
                                text(2,0,1,0,"    ")
                                text(3,0,1,0,"    ")
                        else:
                            text(2,0,1,0,"    ")
                            text(5,0,1,0,"    ")
                            text(3,0,1,0,"    ")
                            pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,bh,rw,rh))

                        if len(Pics) > 0 :
                            pic = Pics[p].split("/")
                            text(0,13,1,4,str(p+1) + "/" + str(len(Pics)))
                            pic = Pics[p].split("/")
                            mp4 = pic[0] + "/" + pic[1] + "/" + pic[2] + "/Videos/" + pic[4][:-4] + ".mp4"
                            cap = cv2.VideoCapture(mp4)
                            if not cap.isOpened():
                                text(0,12,1,4,str(pic[4]))
                            else:
                                fpsv = cap.get(cv2.CAP_PROP_FPS)
                                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                                duration = frame_count / fpsv if fpsv else 0
                                cap.release()
                                text(0,12,1,4,str(pic[4][:-4]) + ".mp4 : " + str(int(duration)) + "s")
                        else:
                            text(0,13,1,4,"0")
                        pygame.display.update()
                        
                        # save config
                        defaults[0]  = mode
                        defaults[1]  = speed
                        defaults[2]  = gain
                        defaults[3]  = meter
                        defaults[4]  = brightness
                        defaults[5]  = contrast
                        defaults[6]  = ev
                        defaults[7]  = sharpness
                        defaults[8]  = saturation
                        defaults[9]  = awb
                        defaults[10] = int(red * 10)
                        defaults[11] = int(blue * 10)
                        defaults[12] = sd_hour
                        defaults[13] = sd_mins
                        defaults[14] = pre_frames
                        defaults[15] = v_length 
                        
                        with open(config_file, 'w') as f:
                            for item in defaults:
                                f.write("%s\n" % item)

