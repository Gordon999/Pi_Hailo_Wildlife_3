#!/usr/bin/env python3

"""Example module for Hailo Detection."""

# v0.5

import pygame, sys
from pygame.locals import *
pygame.init()
windowSurfaceObj = pygame.display.set_mode((320,450),1, 24)
pygame.display.set_caption("Review Captures" ) 

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
import shutil
from gpiozero import LED

# detection objects
objects = ["cat","bear","clock","person"]

# set variables
v_width      = 1456  # video width
v_height     = 1088  # video height
v_length     = 5     # seconds, minimum video length
pre_frames   = 10     # seconds, defines length of pre-detection buffer (1,2,3,5 or 10)
fps          = 25    # video frame rate
mp4_timer    = 10    # seconds, convert h264s to mp4s after this time if no detections
mp4_anno     = 1     # show timestamps on video, 1 = yes, 0 = no
show_detects = 0     # show detections on video, 1 = yes, 0 = no
led          = 21    # recording led gpio
mode         = 1     # camera mode, 0-3 = manual,normal,short,long
speed        = 1000  # manual shutter speed in mS
gain         = 0     # set camera gain, 0 = auto

# mp4_annotation parameters
colour    = (255, 255, 255)
origin    = (184, int(v_height - 35))
font      = cv2.FONT_HERSHEY_SIMPLEX
scale     = 1
thickness = 2

# shutdown time
sd_hour = 19
sd_mins = 0
auto_sd = 0  # set to 1 to shutdown at set time

# ram limit
ram_limit = 150 # stops recording if ram below this

config_file = "Det_Config01.txt"

# check Det_configXX.txt exists, if not then write default values
if not os.path.exists(config_file):
    defaults = [mode,speed,gain]
    with open(config_file, 'w') as f:
        for item in defaults:
            f.write("%s\n" % item)

# read config file
defaults = []
with open(config_file, "r") as file:
   line = file.readline()
   while line:
      defaults.append(line.strip())
      line = file.readline()
defaults = list(map(int,defaults))
mode  = defaults[0]
speed = defaults[1]
gain  = defaults[2]

def text(msg,cr,cg,cb,x,y,ft,bw):
    pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(x,y,bw,20))
    if os.path.exists ('/usr/share/fonts/truetype/freefont/FreeSerif.ttf'):
        fontObj = pygame.font.Font('/usr/share/fonts/truetype/freefont/FreeSerif.ttf',ft)
    else:
        fontObj = pygame.font.Font(None,ft)
    msgSurfaceObj = fontObj.render(msg, False, (cr,cg,cb))
    msgRectobj = msgSurfaceObj.get_rect()
    msgRectobj.topleft = (x,y)
    windowSurfaceObj.blit(msgSurfaceObj, msgRectobj)
    pygame.display.update()

# initialise
Users  = []
Users.append(os.getlogin())
user   = Users[0]
h_user = "/home/" + os.getlogin( )
m_user = "/media/" + os.getlogin( )
start_up = time.monotonic()
startmp4 = time.monotonic()
rec_led  = LED(led)
rec_led.off()
pre_frames = int(pre_frames)
p = 0
modes = ['manual','normal','short','long']
pygame.draw.rect(windowSurfaceObj,(100,100,100),Rect(1,1,80,50),1)
pygame.draw.rect(windowSurfaceObj,(100,100,100),Rect(80,1,80,50),1)
pygame.draw.rect(windowSurfaceObj,(100,100,100),Rect(160,1,80,50),1)
pygame.draw.rect(windowSurfaceObj,(100,100,100),Rect(240,1,80,50),1)
pygame.draw.rect(windowSurfaceObj,(100,100,100),Rect(1,400,80,50),1)
pygame.draw.rect(windowSurfaceObj,(100,100,100),Rect(80,400,80,50),1)
pygame.draw.rect(windowSurfaceObj,(100,100,100),Rect(240,400,80,50),1)
text("PREV",100,100,100,10,15,18,60)
pygame.draw.rect(windowSurfaceObj,(100,100,100),Rect(160,400,80,50),1)
text("NEXT",100,100,100,90,15,18,60)
text("MODE",100,100,100,90,402,18,60)
text(str(modes[mode]),100,100,100,95,420,18,60)
if mode == 0:
    text("SPEED",100,100,100,170,402,18,60)
    text(str(speed),100,100,100,170,420,18,60)
text("GAIN",100,100,100,250,402,18,60)
if gain != 0:
    text(str(gain),100,100,100,250,420,18,60)
else:
    text("Auto",100,100,100,250,420,18,60)
text("Please wait...",100,100,100,10,60,18,60)
time.sleep(10)
text("",100,100,100,10,60,18,100)

# show last captured image
Pics = glob.glob(h_user + '/Pictures/*.jpg')
Pics.sort()
if len(Pics) > 0:
    p = len(Pics) - 1
    image = pygame.image.load(Pics[p])
    image = pygame.transform.scale(image,(320,320))
    windowSurfaceObj.blit(image,(0,51))
    text(str(p+1) + "/" + str(p+1),100,120,100,10,375,18,60)
    pic = Pics[p].split("/")
    pipc = h_user + '/Videos/' + pic[4][:-3] + "mp4"
    text(str(pic[4]),100,120,100,160,375,18,320)
    if os.path.exists(pipc):
        text("DELETE",100,100,100,163,15,18,60)
        text("DEL ALL",100,100,100,10,415,16,60)
        USB_Files  = []
        USB_Files  = (os.listdir(m_user))
        if len(USB_Files) > 0:
            text("  to USB",100,100,100,243,15,18,60)
    pygame.display.update()
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

def draw_objects(request):
    global show_detects, mp4_anno
    current_detections = detections
    if mp4_anno == 1: # show timestamp on video
      timestamp = time.strftime("%Y/%m/%d %T")
      with MappedArray(request, "main") as m:
          lst = list(origin)
          lst[0] += 365
          lst[1] -= 20
          end_point = tuple(lst)
          cv2.rectangle(m.array, origin, end_point, (0,0,0), -1) 
          cv2.putText(m.array, timestamp, origin, font, scale, colour, thickness)
    if current_detections and show_detects == 1: # show detection box
        with MappedArray(request, "main") as m:
            for class_name, bbox, score in current_detections:
                x0, y0, x1, y1 = bbox
                label = f"{class_name} %{int(score * 100)}"
                cv2.rectangle(m.array, (x0, y0), (x1, y1), (0, 255, 0, 0), 4)
                cv2.putText(m.array, label, (x0 + 5, y0 + 45),
                            cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0, 0), 3, cv2.LINE_AA)

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
          
if __name__ == "__main__":

    # get camera version
    Camera_Version()

    # Parse command-line arguments.
    parser = argparse.ArgumentParser(description="Detection Example")
    parser.add_argument("-m", "--model", help="Path for the HEF model.",
                        default="/usr/share/hailo-models/yolov8s_h8l.hef")
    parser.add_argument("-l", "--labels", default="/home/" + user + "/picamera2/examples/hailo/coco.txt",
                        help="Path to a text file containing labels.")
    parser.add_argument("-s", "--score_thresh", type=float, default=0.5,
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
        main  = {'size': (video_w, video_h), 'format': 'YUV420'}
        lores = {'size': (model_w, model_h), 'format': 'RGB888'}
        if cam1 == "imx708":
            controls2 = {'FrameRate': fps,"AfMode": controls.AfModeEnum.Continuous,"AfTrigger": controls.AfTriggerEnum.Start}
        else:
            controls2 = {'FrameRate': fps}
        picam2 = Picamera2()
        config = picam2.create_preview_configuration(main, lores=lores, controls=controls2)
        picam2.configure(config)
        encoder = H264Encoder(2000000)
        if pre_frames < 2:
            circular = CircularOutput2(buffer_duration_ms=1000)
        elif pre_frames < 3:
            circular = CircularOutput2(buffer_duration_ms=2000)
        elif pre_frames < 4:
            circular = CircularOutput2(buffer_duration_ms=3000)
        elif pre_frames < 10:
            circular = CircularOutput2(buffer_duration_ms=5000)
        elif pre_frames >= 10:
            circular = CircularOutput2(buffer_duration_ms=10000)
        picam2.start_preview(Preview.QTGL, x=0, y=0, width=480, height=480)
        picam2.start_recording(encoder, circular)
        picam2.title_fields = ["ExposureTime"]
        encoding = False
        if show_detects == 1 or mp4_anno == 1:
            picam2.pre_callback = draw_objects
        picam2.set_controls({"AnalogueGain": gain})
        if mode == 0:
            picam2.set_controls({"AeEnable": False,"ExposureTime": speed})
        else:
            if mode == 1:
                picam2.set_controls({"AeEnable": True,"AeExposureMode": controls.AeExposureModeEnum.Normal})
            elif mode == 2:
                picam2.set_controls({"AeEnable": True,"AeExposureMode": controls.AeExposureModeEnum.Short})
            elif mode == 3:
                picam2.set_controls({"AeEnable": True,"AeExposureMode": controls.AeExposureModeEnum.Long})
            
        while True:
            # get free ram space
            st = os.statvfs("/run/shm/")
            freeram = (st.f_bavail * st.f_frsize)/1100000
                
            # capture frame
            frame = picam2.capture_array('lores')

            # Run inference on the preprocessed frame
            results = hailo.run(frame)
                
            # Extract detections from the inference results
            detections = extract_detections(results, video_w, video_h, class_names, args.score_thresh)
            # detection
            for d in range(0,len(objects)):
                if len(detections) != 0:
                    value = float(detections[0][2])
                    obj = detections[0][0]
                    if value > args.score_thresh and value < 1 and obj == objects[d]:
                        startrec = time.monotonic()
                        startmp4 = time.monotonic()
                        # start recording
                        if not encoding and freeram > ram_limit:
                            now = datetime.datetime.now()
                            timestamp = now.strftime("%y%m%d_%H%M%S")
                            circular.open_output(PyavOutput("/run/shm/" + timestamp +".mp4"))
                            encoding = True
                            print("New  Detection",timestamp,objects[d])
                            rec_led.on()
                            # save lores image
                            cv2.imwrite(h_user + "/Pictures/" + str(timestamp) + ".jpg",frame)
                            # show captured lores trigger image
                            Pics = glob.glob(h_user + '/Pictures/*.jpg')
                            Pics.sort()
                            p = len(Pics)-1
                            img = cv2.cvtColor(frame,cv2.COLOR_RGB2BGR)
                            image = pygame.surfarray.make_surface(img)
                            image = pygame.transform.scale(image,(320,320))
                            image = pygame.transform.rotate(image,int(90))
                            image = pygame.transform.flip(image,0,1)
                            windowSurfaceObj.blit(image,(0,51))
                            text(str(p+1) + "/" + str(p+1),100,120,100,10,375,18,60)
                            pic = Pics[p].split("/")
                            text(str(pic[4]),100,120,100,160,375,18,320)
                            text("    ",100,100,100,163,15,18,70)
                            text("    ",100,100,100,243,15,18,70)
                            pygame.display.update()

            # stop recording
            if encoding and (time.monotonic() - startrec > v_length + pre_frames or freeram <= ram_limit):
                now = datetime.datetime.now()
                timestamp2 = now.strftime("%y%m%d_%H%M%S")
                print("Stopped Record", timestamp2)
                circular.close_output()
                encoding = False
                startmp4 = time.monotonic()
                rec_led.off()

            # move mp4s
            if time.monotonic() - startmp4 > mp4_timer and not encoding:
                startmp4 = time.monotonic()
                Videos = glob.glob('/run/shm/*.mp4')
                Videos.sort()
                # move Video RAM mp4s to SD card
                for xx in range(0,len(Videos)):
                    if not os.path.exists(h_user + "/" + '/Videos/' + Videos[xx]):
                        shutil.move(Videos[xx], h_user + '/Videos/')
                Pics = glob.glob(h_user + '/Pictures/*.jpg')
                Pics.sort()
                if len(Pics) > 0:
                  pic = Pics[p].split("/")
                  pipc = h_user + '/Videos/' + pic[4][:-3] + "mp4"
                  if os.path.exists(pipc):
                    text("DELETE",100,100,100,163,15,18,60)
                    text("DEL ALL",100,100,100,10,415,16,60)
                    USB_Files  = []
                    USB_Files  = (os.listdir(m_user))
                    if len(USB_Files) > 0:
                        text("  to USB",100,100,100,243,15,18,60)
                  else:
                    text("    ",100,100,100,163,15,18,70)
                    text("    ",100,100,100,243,15,18,70)
                    text("    ",100,100,100,10,415,18,70)
                else:
                    text("    ",100,100,100,163,15,18,70)
                    text("    ",100,100,100,243,15,18,70)
                    text("    ",100,100,100,10,415,18,70)

                # auto shutdown
                if auto_sd == 1:
                    # check if clock synchronised
                    if "System clock synchronized: yes" in os.popen("timedatectl").read().split("\n"):
                        synced = 1
                    else:
                        synced = 0
                    # check current hour and shutdown
                    now = datetime.datetime.now()
                    sd_time = now.replace(hour=sd_hour, minute=sd_mins, second=0, microsecond=0)
                    if now >= sd_time and time.monotonic() - start_up > 300 and synced == 1:
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
                        os.system("sudo shutdown -h now")

            #check for any mouse button presses
            for event in pygame.event.get():
                    if (event.type == MOUSEBUTTONUP):
                        mousex, mousey = event.pos
                        # delete ALL Pictures and Videos
                        if mousex < 80 and mousey > 400 and event.button == 3:
                            Videos = glob.glob(h_user + '/Videos/*.mp4')
                            Videos.sort()
                            for w in range(0,len(Videos)):
                                os.remove(Videos[w])
                            Pics = glob.glob(h_user + '/Pictures/*.jpg')
                            Pics.sort()
                            for w in range(0,len(Pics)):
                                os.remove(Pics[w])
                            pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,371,320,28))
                            pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,51,320,320))
                            p = 0
                        # camera control
                        # MODE
                        if mousex > 80 and mousex < 160 and mousey > 400:
                            if event.button == 3 or event.button == 5:
                                mode -=1
                                if mode < 0:
                                    mode = 3
                            else:
                                mode +=1
                                if mode > 3:
                                    mode = 0
                            text(str(modes[mode]),100,100,100,95,420,18,60)
                            if mode == 0:
                                picam2.set_controls({"AeEnable": False,"ExposureTime": speed,"AnalogueGain": gain})
                                text("SPEED",100,100,100,170,402,18,60)
                                text(str(speed),100,100,100,170,420,18,60)
                            else:
                                if mode == 1:
                                    picam2.set_controls({"AeEnable": True,"AeExposureMode": controls.AeExposureModeEnum.Normal,"AnalogueGain": gain})
                                elif mode == 2:
                                    picam2.set_controls({"AeEnable": True,"AeExposureMode": controls.AeExposureModeEnum.Short,"AnalogueGain": gain})
                                elif mode == 3:
                                    picam2.set_controls({"AeEnable": True,"AeExposureMode": controls.AeExposureModeEnum.Long,"AnalogueGain": gain})
                                text(" ",100,100,100,170,402,18,60)
                                text(" ",100,100,100,170,420,18,60)
                        # SHUTTER SPEED
                        if mousex > 160 and mousex < 240 and mousey > 400 and mode == 0:
                            if event.button == 3 or event.button == 5:
                                speed -=1000
                                speed = max(1000,speed)
                            else:
                                speed += 1000
                                speed = min(100000,speed)
                            picam2.set_controls({"AeEnable": False,"ExposureTime": speed,"AnalogueGain": gain})
                            text("SPEED",100,100,100,170,402,18,60)
                            text(str(speed),100,100,100,170,420,18,60)
                        # GAIN
                        if mousex > 240 and mousey > 400:
                            if event.button == 3 or event.button == 5:
                                gain -=1
                                gain = max(0,gain)
                            else:
                                gain +=1
                                gain = min(64,gain)
                            picam2.set_controls({"AnalogueGain": gain})
                            text("GAIN",100,100,100,250,402,18,60)
                            if gain != 0:
                                text(str(gain),100,100,100,250,420,18,60)
                            else:
                                text("Auto",100,100,100,250,420,18,60)
                        # show previous
                        elif mousex < 80 and mousey < 50:
                            Pics = glob.glob(h_user + '/Pictures/*.jpg')
                            Pics.sort()
                            p -= 1
                            if p < 0:
                                p = 0
                            if len(Pics) > 0:
                                image = pygame.image.load(Pics[p])
                                image = pygame.transform.scale(image,(320,320))
                                windowSurfaceObj.blit(image,(0,51))
                                text(str(p+1) + "/" + str(p+1),100,120,100,10,375,18,60)
                                pic = Pics[p].split("/")
                                text(str(pic[4]),100,120,100,160,375,18,320)
                                pygame.display.update()
                        # show next
                        elif mousex > 80 and mousex < 160 and mousey < 50:
                            Pics = glob.glob(h_user + '/Pictures/*.jpg')
                            Pics.sort()
                            p += 1
                            if p > len(Pics)-1:
                                p = len(Pics)-1
                            if len(Pics) > 0:
                                image = pygame.image.load(Pics[p])
                                image = pygame.transform.scale(image,(320,320))
                                windowSurfaceObj.blit(image,(0,51))
                                pic = Pics[p].split("/")
                                text(str(pic[4]),100,120,100,160,375,18,320)
                                text(str(p+1) + "/" + str(p+1),100,120,100,10,375,18,60)
                                pygame.display.update()
                        # delete picture and video
                        elif mousex > 160 and mousex < 240 and mousey < 50 and event.button == 3:
                            pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,51,320,320))
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
                                image = pygame.transform.scale(image,(320,320))
                                windowSurfaceObj.blit(image,(0,51))
                                pic = Pics[p].split("/")
                                text(str(pic[4]),100,120,100,160,375,18,320)
                            else:
                                pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,375,320,20))
                            pygame.display.update()
                        # move picture and video to USB
                        elif mousex > 240 and mousey < 50  and event.button != 3:
                            pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,51,320,320))
                            Pics = glob.glob(h_user + '/Pictures/*.jpg')
                            Pics.sort()
                            Videos = glob.glob(h_user + '/Videos/*.mp4')
                            Videos.sort()
                            if len(Pics) > 0:
                                pic = Pics[p].split("/")
                                pipc = h_user + '/Videos/' + pic[4][:-3] + "mp4"
                                print(pipc)
                                # move mp4s to USB if present, and less than 90% full
                                USB_Files  = []
                                USB_Files  = (os.listdir(m_user))
                                if len(USB_Files) > 0:
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
                            if p > len(Pics) - 1:
                                p -= 1
                            if len(Pics) > 0:
                                image = pygame.image.load(Pics[p])
                                image = pygame.transform.scale(image,(320,320))
                                windowSurfaceObj.blit(image,(0,51))
                                pic = Pics[p].split("/")
                                text(str(pic[4]),100,120,100,160,375,18,320)
                            else:
                                pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,375,320,20))
                            pygame.display.update()
                            
                        # move ALL pictures and videos to USB
                        elif mousex > 240 and mousey < 50 and event.button == 3:
                            pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,51,320,320))
                            Pics = glob.glob(h_user + '/Pictures/*.jpg')
                            Pics.sort()
                            Videos = glob.glob(h_user + '/Videos/*.mp4')
                            Videos.sort()
                            if len(Pics) > 0 or len(Videos) > 0:
                                # move mp4s and jpgs to USB if present, and USB storage < 90% full
                                USB_Files  = []
                                USB_Files  = (os.listdir(m_user))
                                if len(USB_Files) > 0:
                                    # make directories (if required)
                                    if not os.path.exists(m_user + "/'" + USB_Files[0] + "'/Videos/") :
                                        os.system('mkdir ' + m_user + "/'" + USB_Files[0] + "'/Videos/")
                                    if not os.path.exists(m_user + "/'" + USB_Files[0] + "'/Pictures/") :
                                        os.system('mkdir ' + m_user + "/'" + USB_Files[0] + "'/Pictures/")
                                    usedusb = os.statvfs(m_user + "/" + USB_Files[0] + "/")
                                    USB_storage = ((1 - (usedusb.f_bavail / usedusb.f_blocks)) * 100)
                                    print(USB_storage)
                                if len(USB_Files) > 0 and USB_storage < 90:
                                    for w in range(0,len(Pics)):
                                        pic = Pics[w].split("/")
                                        if not os.path.exists(m_user + "/" + USB_Files[0] + "/Pictures/" + pic[4]):
                                            shutil.move(Pics[w],m_user + "/" + USB_Files[0] + "/Pictures/")
                                    for w in range(0,len(Videos)):
                                        vid = Videos[w].split("/")
                                        if not os.path.exists(m_user + "/" + USB_Files[0] + "/Videos/" + vid[4]):
                                            shutil.move(Videos[w],m_user + "/" + USB_Files[0] + "/Videos/")
                                Videos = glob.glob(h_user + '/Videos/*.mp4')
                                Videos.sort()
                                Pics = glob.glob(h_user + '/Pictures/*.jpg')
                                Pics.sort()
                            if p > len(Pics) - 1:
                                p -= 1
                            if len(Pics) > 0:
                                image = pygame.image.load(Pics[p])
                                image = pygame.transform.scale(image,(320,320))
                                windowSurfaceObj.blit(image,(0,51))
                                pic = Pics[p].split("/")
                                text(str(pic[4]),100,120,100,160,375,18,320)
                            else:
                                pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,375,320,20))
                            pygame.display.update()
                        Videos = glob.glob(h_user + '/Videos/*.mp4')
                        Videos.sort()
                        Pics = glob.glob(h_user + '/Pictures/*.jpg')
                        Pics.sort()
                        Pics = glob.glob(h_user + '/Pictures/*.jpg')
                        Pics.sort()
                        if len(Pics) > 0:
                            pic = Pics[p].split("/")
                            pipc = h_user + '/Videos/' + pic[4][:-3] + "mp4"
                            if os.path.exists(pipc):
                                text("DELETE",100,100,100,163,15,18,60)
                                text("DEL ALL",100,100,100,10,415,16,60)
                                USB_Files  = []
                                USB_Files  = (os.listdir(m_user))
                                if len(USB_Files) > 0:
                                    text("  to USB",100,100,100,243,15,18,60)
                            else:
                                text("    ",100,100,100,163,15,18,70)
                                text("    ",100,100,100,243,15,18,70)
                                text("    ",100,100,100,10,415,18,70)
                        else:
                            text("    ",100,100,100,163,15,18,70)
                            text("    ",100,100,100,243,15,18,70)
                            text("    ",100,100,100,10,415,18,70)

                        if len(Pics) > 0:
                            msg = str(p+1) + "/" + str(len(Pics))
                            pic = Pics[p].split("/")
                            text(str(pic[4]),100,120,100,160,375,18,320)
                        else:
                            msg = str(len(Pics))
                        text(msg,100,120,100,10,375,18,60)
                        pygame.display.update()

                        defaults[0] = mode
                        defaults[1] = speed
                        defaults[2] = gain
                        with open(config_file, 'w') as f:
                            for item in defaults:
                                f.write("%s\n" % item)
