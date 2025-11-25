# Pi_Hailo_Wildlife_3

Pi5 + Hailo HAT + PI Camera to capture Wildlife videos in MP4 directly.

## Screenshot...(Note there is no red squirrel in the objects list, so it sees them as bears or cats !!)

![screenshot](screenshot.jpg)

## My Camera setup...

![screenshot](camera.jpg)

It is a modified version of the hailo picamera2 detect.py example https://github.com/raspberrypi/picamera2/tree/main/examples/hailo
and https://github.com/raspberrypi/picamera2/blob/main/examples/pyav_circular_capture.py

To setup the hailo..

     with Trixie sudo apt install dkms

     sudo apt install hailo-all

reboot

     git clone --depth 1 https://github.com/raspberrypi/picamera2

reboot

sudo apt install python3-opencv -y

to autostart at boot if using labwc...

(note: change XXXX to your username)

sudo nano /home/XXXX/.config/labwc/autostart

type in...

/usr/bin/python3 /home/XXXX/detect_003.py

press Ctrl and X, Y, return to save..

Reboot

Captures videos as .mp4 videos

v_width and v_height are set for a Pi GS camera, you may need to change to suit other cameras ....

Runs a pre-capture buffer of approx 5 seconds by default

you can set the objects to detect in line 41, objects = ["cat","bear","bird"], the objects must be in coco.txt file

Copy detect_003.py into /home/USERNAME/picamera2/examples/hailo/

Videos saved in /home/USERNAME/Videos

to run ... 

cd /home/USERNAME/picamera2/examples/hailo/

python3 detect_003.py

When running you will see 2 windows, a live window and a capture review and control window.
