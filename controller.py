from vision.vision import Vision, Camera, GUI
from planning.planner import Planner
from postprocessing.postprocessing import Postprocessing
from preprocessing.preprocessing import Preprocessing
import vision.tools as tools
from cv2 import waitKey
import cv2
import serial
import warnings
import time


warnings.filterwarnings("ignore", category=DeprecationWarning)


class Controller:
    """
    Primary source of robot control. Ties vision and planning together.
    """

    def __init__(self, pitch, color, our_side, video_port=0, comm_port='/dev/ttyACM0', comms=1):
        """
        Entry point for the SDP system.

        Params:
            [int] video_port                port number for the camera , Feed is only reachable from the same room
                                            therefor always 0
            [string] comm_port              port number for the arduino
            [int] pitch                     0 - main pitch, 1 - secondary pitch , get's the correct croppings from json
            [string] our_side               the side we're on - 'left' or 'right'
            *[int] port                     The camera port to take the feed from
            [int]comms                      Sets the communications with the arduino, If 0 and using set write function
                                            no actual write will be done to arduino, If 1 (or higher) commands will
                                            be able to be sent to Arduino
        """
        assert pitch in [0, 1]
        assert color in ['yellow', 'blue']
        assert our_side in ['left', 'right']

        self.pitch = pitch

        # Set up the Arduino communications
        self.arduino = Arduino(comm_port, 115200, 1, comms)

        # Set up camera for frames
        self.camera = Camera(port=video_port, pitch=self.pitch)
        frame = self.camera.get_frame()
        # gets center of the frame based on the table croppings,
        #TODO Check whether this is working correctly, as it gets the left and top coordinate from croppings and always substracts it
        center_point = self.camera.get_adjusted_center(frame)

        # Set up vision
        self.calibration = tools.get_colors(pitch)
        self.vision = Vision(
            pitch=pitch, color=color, our_side=our_side,
            frame_shape=frame.shape, frame_center=center_point,
            calibration=self.calibration)

        # Set up postprocessing for vision
        self.postprocessing = Postprocessing()

        # Set up main planner
        self.planner = Planner(our_side=our_side, pitch_num=self.pitch)

        # Set up GUI
        self.GUI = GUI(calibration=self.calibration, arduino=self.arduino, pitch=self.pitch)

        self.color = color
        self.side = our_side

        self.preprocessing = Preprocessing()

        #Planning code

        self.robot = RobotController()

    def wow(self):
        """
        Ready your sword, here be dragons.
        """
        counter = 1L
        timer = time.clock()

        try:
            c = True
            while c != 27:  # the ESC key

                frame = self.camera.get_frame()
                pre_options = self.preprocessing.options
                # Apply preprocessing methods toggled in the UI
                preprocessed = self.preprocessing.run(frame, pre_options)
                frame = preprocessed['frame']
                if 'background_sub' in preprocessed:
                    cv2.imshow('bg sub', preprocessed['background_sub'])
                # Find object positions
                # model_positions have their y coordinate inverted

                model_positions, regular_positions = self.vision.locate(frame)
                model_positions = self.postprocessing.analyze(model_positions)

                # ###################### PLANNING ########################
                # Find appropriate action
                self.planner.update_world(model_positions)

                actions = self.planner.plan()
                self.robot.execute(self.arduino, actions)

                # Information about the grabbers from the world
                grabbers = {
                    'our_defender': self.planner._world.our_defender.catcher_area,
                    'our_attacker': self.planner._world.our_attacker.catcher_area
                }

                # Information about states
                attackerState = "whatever"
                defenderState = "whatever"
                # ######################## END PLANNING ###############################

                # Use 'y', 'b', 'r' to change color.
                c = waitKey(2) & 0xFF
                fps = float(counter) / (time.clock() - timer)
                # Draw vision content and actions

                default_actions = {'move': 0, 'strafe': 0, 'angle': 0, 'grabber': -1, 'kick': 0}

                self.GUI.draw(
                    frame, model_positions, regular_positions, fps, attackerState,
                    defenderState, default_actions, actions, grabbers,
                    our_color=self.color, our_side=self.side, key=c, preprocess=pre_options)
                counter += 1
            if self.arduino.isOpen:
                self.arduino.close()

        except:
            self.robot.shutdown(self.arduino)
            raise

        finally:
            # Write the new calibrations to a file.
            tools.save_colors(self.pitch, self.calibration)
            self.robot.shutdown(self.arduino)


class RobotController(object):
    """
        Defender Controller
    """

    def __init__(self):
        self.current_speed = 0
        self.busy = False
        self.old_action = {"move": None,
                           "angle": None,
                           "strafe": None}
        self.time = time.clock()
        self.flag = False

    def isBusy(self, comm):
        bits_waiting = comm.serial.inWaiting()
        if bits_waiting:
            a = ord(comm.serial.read())
            if a == 255:
                self.busy = False
        if self.time + 0.4 < time.clock() and self.flag:
            print "time out"
            self.busy = False
            self.flag = False
        return self.busy

    def execute(self, comm, action):
        """
        Execute robot action.
        """
        if action["move"] and action["move"] == self.old_action["move"]:
            return
        if action["move"] == 0 and self.old_action["move"] == 0 \
                and action["angle"] == 0 and self.old_action["angle"] == 0 \
                and action["strafe"] == 0 and self.old_action["strafe"] == 0 \
                and action["grabber"] == -1 and not action["kick"]:
            return

        # Sends move forward
        if action["move"] > 0:
            print "trying to move"
            if not self.isBusy(comm):
                self.old_action = action
                self.time = time.clock()
                self.flag = True
                print("Move forward")
                comm.send('W', action['move'])

        # Sends move backward
        elif action['move'] < 0:
            if not self.isBusy(comm):
                self.old_action = action
                self.time = time.clock()
                self.flag = True
                print("Move Backward")
                comm.send('S', abs(action['move']))

        #sends strafe right
        elif action['strafe'] < 0:
            if not self.isBusy(comm):
                self.old_action = action
                self.time = time.clock()
                self.flag = True
                print("Strafe right")
                comm.send('V', abs(action['strafe']))

        #sends strafe left
        elif action['strafe'] > 0:
            if not self.isBusy(comm):
                self.old_action = action  #
                self.time = time.clock()
                self.flag = True

                print("Strafe left")
                comm.send('C', action['strafe'])

        #sends turn right by a certain angle
        elif action['angle'] < 0:
            if not self.isBusy(comm):
                self.old_action = action
                print("Turn right by " + str(action['angle'] * 2))
                comm.send('D', abs(action['angle']))
                self.busy = True
                self.time = time.clock()
                self.flag = True

        #sends turn left by a certain angle
        elif action['angle'] > 0:
            if not self.isBusy(comm):
                self.old_action = action
                print("Turn left by " + str(abs(action['angle'] * 2)))
                comm.send('A', action['angle'])
                self.busy = True
                self.time = time.clock()
                self.flag = True

        # Else stop
        else:
            print "Sending stop"
            self.old_action = action
            comm.send(' ', 0)
            self.busy = False

        #sends close both grabbers at the same time
        if action['grabber'] == 0:
            self.old_action = action
            print("Close both grabbers at once")
            comm.send('X', (action['grabber']))

        #sends close right grabber first
        elif action['grabber'] == 1:
            self.old_action = action
            print("Close right grabber first")
            comm.send('X', 0)

        #sends close left grabber first
        elif action['grabber'] == 2:
            self.old_action = action
            print("Close left grabber first")
            comm.send('X', 0)

        elif action['grabber'] == 3:
            self.old_action = action
            print("Open grabber")
            comm.send('Z', 0)

        #sends kick command
        elif action['kick'] > 1:
            self.old_action = action
            print("Kick")
            comm.send('Q', action['kick'])

    def shutdown(self, comm):
        pass


class Arduino:
    def __init__(self, port, rate, timeOut, comms):
        """
            [int]comms                      Sets the communications with the arduino, If 0 and using set write function
                                            no actual write will be done to arduino, If 1 (or higher) commands will
                                            be able to be sent to Arduino
        """
        self.serial = None
        self.comms = comms
        self.port = port
        self.rate = rate
        self.timeout = timeOut
        self.setComms(comms)

    def setComms(self, comms):
        if comms > 0:
            self.comms = 1
            if self.serial is None:
                try:
                    print("sending heartbeat")
                    self.serial = serial.Serial(self.port, self.rate, timeout=self.timeout)
                    self.heartBeat()
                except Exception as e:
                    print ("No Arduino detected!")
                    print ("Continuing without comms.")
                    print (e)
                    self.comms = 0
                    # raise
        else:
            print ("Communication with Arduino is turned off")
            # self.write('A_RUN_KICK\n')
            #self.send('A_RUN_ENGINE %d %d\n' % (0, 0))
            #self.write('D_RUN_KICK\n')
            #self.send('D_RUN_ENGINE %d %d\n' % (0, 0))
            self.comms = 0

    def send(self, string, data):
        if self.comms == 1:
            # print ("Sending message to Arduino: " + string + str(data))
            self.serial.write(string + chr(data))

    def heartBeat(self):
        # TODO refactor this method, waiting for response from heartbeat
        bits_toSend = "X"
        self.serial.write("L" + bits_toSend)
        time.sleep(0.3)
        bits_waiting = self.serial.inWaiting()
        if (bits_waiting):
            if (self.serial.read() == bits_toSend):
                print ("Communication estabilished - correct response")
            else:
                print ("Communication estabilished - incorrect response")
        else:
            print ("Communication not established")

    def isOpen(self):
        return self.serial is not None

    def close(self):
        self.serial.flush()
        self.serial.close()


if __name__ == '__main__':
    # argparse is used for including help -h to python command line, also to translate arguments like nocomms
    #from -n to True or False
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("pitch", help="[0] Main pitch, [1] Secondary pitch")
    parser.add_argument("side", help="The side of our defender ['left', 'right'] allowed.")
    parser.add_argument("color", help="The color of our team - ['yellow', 'blue'] allowed.")
    #store_true translates -n or --nocomms to True value for comms argument
    parser.add_argument(
        "-n", "--nocomms", help="Disables sending commands to the robot.", action="store_true")

    args = parser.parse_args()
    #Based on nocomms value ( -n / --nocomms) turns off or on the communications for arduino
    if args.nocomms:
        c = Controller(
            pitch=int(args.pitch), color=args.color, our_side=args.side, comms=0).wow()
    else:
        c = Controller(
            pitch=int(args.pitch), color=args.color, our_side=args.side).wow()

