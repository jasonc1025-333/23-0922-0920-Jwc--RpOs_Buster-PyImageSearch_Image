# USAGE
# python pan_tilt_tracking.py --cascade haarcascade_frontalface_default.xml

# import necessary packages
from pyimagesearch.objcenter import ObjCenter
from pyimagesearch.pid import PID
from multiprocessing import Manager
from multiprocessing import Process
from imutils.video import VideoStream
import pantilthat as pth
import argparse
import signal
import time
import sys
import cv2

# define the range for the motors
servoRange = (-90, 90)

# function to handle keyboard interrupt
def signal_handler(sig, frame):
	# disable the servos and gracefully exit
	print("[INFO] You pressed `ctrl + c`! Exiting...")
	pth.servo_enable(1, False)
	pth.servo_enable(2, False)
	sys.exit()

def obj_center(args, objX, objY, centerX, centerY):
	# set the signal trap to handle keyboard interrupt and then
	# initialize the object center finder
	signal.signal(signal.SIGINT, signal_handler)
	obj = ObjCenter(args["cascade"])

	# start the video stream and wait for the camera to warm up
	vs = VideoStream(usePiCamera=True).start()
	time.sleep(2.0)

	# loop indefinitely
	while True:
		# grab the frame from the threaded video stream and flip it
		# vertically (since our camera was upside down)
		frame = vs.read()
		frame = cv2.flip(frame, 0)

		# calculate the center of the frame as this is (ideally) where
		# we will we wish to keep the object
		(H, W) = frame.shape[:2]
		centerX.value = W // 2
		centerY.value = H // 2

		# find the object's location
		objectLoc = obj.update(frame, (centerX.value, centerY.value))
		((objX.value, objY.value), rect) = objectLoc

		# extract the bounding box and draw it on the frame
		if rect is not None:
			(x, y, w, h) = rect
			cv2.rectangle(frame, (x, y), (x + w, y + h),
				(0, 255, 0), 2)

		# display the frame to the screen
		cv2.imshow("Pan-Tilt Face Tracking", frame)
		cv2.waitKey(1)

def pid_process(output, p, i, d, objCoord, centerCoord):
	# set the signal trap to handle keyboard interrupt, then create a
	# PID and initialize it
	signal.signal(signal.SIGINT, signal_handler)
	p = PID(p.value, i.value, d.value)
	p.initialize()

	# loop indefinitely
	while True:
		# calculate the error and update the vlaue
		error = centerCoord.value - objCoord.value
		output.value = p.update(error)

def in_range(val, start, end):
	# determine the input vale is in the supplied range
	return (val >= start and val <= end)

def set_servos(pan, tlt):
	# set the signal trap to handle keyboard interrupt
	signal.signal(signal.SIGINT, signal_handler)

	# loop indefinitely
	while True:
		# the pan and tilt angles are reversed so multiply by -1
		panAngle = -1 * pan.value
		tltAngle = -1 * tlt.value

		# if the pan angle is within the range, pan
		if in_range(panAngle, servoRange[0], servoRange[1]):
			pth.pan(panAngle)

		# if the tilt angle is within the range, tilt
		if in_range(tltAngle, servoRange[0], servoRange[1]):
			pth.tilt(tltAngle)

# check to see if this is the main body of execution
if __name__ == "__main__":
	# construct the argument parser and parse the arguments
	ap = argparse.ArgumentParser()
	ap.add_argument("-c", "--cascade", type=str, required=True,
		help="path to input Haar cascade for face detection")
	args = vars(ap.parse_args())

	# start a manager for managing process-safe variables
	with Manager() as manager:
		# enable the servos
		pth.servo_enable(1, True)
		pth.servo_enable(2, True)

		# set integer values for the object center (x, y)-coordinates
		centerX = manager.Value("i", 0)
		centerY = manager.Value("i", 0)

		# set integer values for the object's (x, y)-coordinates
		objX = manager.Value("i", 0)
		objY = manager.Value("i", 0)

		# pan and tilt values will be managed by independent PIDs
		pan = manager.Value("i", 0)
		tlt = manager.Value("i", 0)

		# set PID values for panning
		panP = manager.Value("f", 0.09)
		panI = manager.Value("f", 0.08)
		panD = manager.Value("f", 0.002)

		# set PID values for tilting
		tiltP = manager.Value("f", 0.11)
		tiltI = manager.Value("f", 0.10)
		tiltD = manager.Value("f", 0.002)

		# we have 4 independent processes
		# 1. objectCenter  - finds/localizes the object
		# 2. panning       - PID control loop determines panning angle
		# 3. tilting       - PID control loop determines tilting angle
		# 4. setServos     - drives the servos to proper angles based
		#                    on PID feedback to keep object in center
		processObjectCenter = Process(target=obj_center,
			args=(args, objX, objY, centerX, centerY))
		processPanning = Process(target=pid_process,
			args=(pan, panP, panI, panD, objX, centerX))
		processTilting = Process(target=pid_process,
			args=(tlt, tiltP, tiltI, tiltD, objY, centerY))
		processSetServos = Process(target=set_servos, args=(pan, tlt))

		# start all 4 processes
		processObjectCenter.start()
		processPanning.start()
		processTilting.start()
		processSetServos.start()

		# join all 4 processes
		processObjectCenter.join()
		processPanning.join()
		processTilting.join()
		processSetServos.join()

		# disable the servos
		pth.servo_enable(1, False)
		pth.servo_enable(2, False)