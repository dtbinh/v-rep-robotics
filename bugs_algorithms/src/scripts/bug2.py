#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'ar1'

import math
import time
import vrep
import sys
import numpy as np

from support import *

PI = math.pi

class State:
    MOVING = 1
    ROTATING = 2
    ENVELOPING = 3

class Bug2:
    def __init__(self):

        self._init_client_id()
        self._init_handles()
        self._init_sensor_handles()

        self.state = State.MOVING

        self.MIN_DETECTION_DIST = 0.0
        self.MAX_DETECTION_DIST = 1.0
        self.WHEEL_SPEED = 1.0
        self.INDENT_DIST = 0.5

        self.SLEEP_TIME = 0.2

        self.bot_pos = None
        self.bot_euler_angles = None
        self.target_pos = None
        self.obstacle_dist_stab_PID = None
        self.obstacle_follower_PID = None

        self.targetDir = None
        self.botDir = None
        self.botPos = None
        self.targetPos = None
        self.botEulerAngles = None

        self.detect = np.zeros(16)

    def _init_client_id(self):
        vrep.simxFinish(-1)

        self.client_id = vrep.simxStart('127.0.0.1', 19999, True, True, 5000, 5)

        if self.client_id != -1:
            print 'Connected to remote API server'

        else:
            print 'Connection not successful'
            sys.exit('Could not connect')

    def angle_between_vectors(self, a, b):  # a -> b

        def unit_vector(vector):
            n = 1.0 / math.sqrt(np.sum(np.array(vector) ** 2))
            return vector * n

        a = unit_vector(a)
        b = unit_vector(b)

        if len(a) == 4:
            a = a[1:]

        if len(b) == 4:
            b = b[1:]

        angle = math.acos(b.dot(a))

        if (a * b)[2] > 0.0:
            return -angle
        return angle

    def create_quaternion(self, angle, vector):
        halfAngle = angle / 2.0
        sinHalfAngle = math.sin(halfAngle)
        w = math.cos(halfAngle)
        x = sinHalfAngle * vector[0]
        y = sinHalfAngle * vector[1]
        z = sinHalfAngle * vector[2]
        return np.array([w, x, y, z])

    def rotate(self, q_rot, vector):
        vect_quad = np.array([0, vector[0], vector[1], vector[2]])
        q1 = self.multiply_quternions(q_rot, vect_quad)
        res = self.multiply_quternions(q1, self.inverse_quaternion(q_rot))
        return res

    def multiply_quternions(self, a, b):
        w = a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3]
        x = a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2]
        y = a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1]
        z = a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0]
        return np.array([w, x, y, z])

    def inverse_quaternion(self, q_rot):

        n = self.norm_quaternion(q_rot)

        w =   q_rot[0] / n
        x = - q_rot[1] / n
        y = - q_rot[2] / n
        z = - q_rot[3] / n
        return np.array([w, x, y, z])

    def norm_quaternion(self, q):
        return np.sum(np.array(q) ** 2)

    def dot_quaternion(self, q1, q2):
        return q1[0] * q2[0] + q1[1] * q2[1] + q1[2] * q2[2] + q1[3] * q2[3]

    def _init_handles(self):

        self._init_wheels_handle()

        self._init_target_handle()

        self._init_robot_handle()

    def _init_robot_handle(self):
        # handle of robot
        error_code, self.bot_handle = vrep.simxGetObjectHandle(self.client_id, 'Pioneer_p3dx',
                                                               vrep.simx_opmode_oneshot_wait)

    def _init_target_handle(self):
        # get handle of target robot
        error_code, self.target_handle = vrep.simxGetObjectHandle(self.client_id, 'target',
                                                                  vrep.simx_opmode_oneshot_wait)

    def _init_wheels_handle(self):
        # get handles of robot wheels
        error_code, self.left_motor_handle = vrep.simxGetObjectHandle(self.client_id, 'Pioneer_p3dx_leftMotor',
                                                                     vrep.simx_opmode_oneshot_wait)
        error_code, self.right_motor_handle = vrep.simxGetObjectHandle(self.client_id, 'Pioneer_p3dx_rightMotor',
                                                                      vrep.simx_opmode_oneshot_wait)

    def _init_sensor_handles(self):

        self.sensor_handles = []  # empty list for handles

        for x in range(1, 16 + 1):
            error_code, sensor_handle = vrep.simxGetObjectHandle(self.client_id, 'Pioneer_p3dx_ultrasonicSensor' + str(x),
                                                                 vrep.simx_opmode_oneshot_wait)
            self.sensor_handles.append(sensor_handle)
            vrep.simxReadProximitySensor(self.client_id, sensor_handle, vrep.simx_opmode_streaming)

    def _init_values(self):

        error_code, self.target_pos = vrep.simxGetObjectPosition(self.client_id, self.target_handle, -1,
                                                                 vrep.simx_opmode_oneshot)

        error_code, self.bot_pos = vrep.simxGetObjectPosition(self.client_id, self.bot_handle, -1,
                                                              vrep.simx_opmode_oneshot)

        error_code, self.bot_euler_angles = vrep.simxGetObjectOrientation(self.client_id, self.bot_handle, -1,
                                                                          vrep.simx_opmode_streaming)

    def read_values(self):

        error_code, self.target_pos = vrep.simxGetObjectPosition(self.client_id, self.target_handle, -1,
                                                                 vrep.simx_opmode_buffer)

        error_code, self.bot_pos = vrep.simxGetObjectPosition(self.client_id, self.bot_handle, -1,
                                                              vrep.simx_opmode_buffer)

        error_code, self.bot_euler_angles = vrep.simxGetObjectOrientation(self.client_id, self.bot_handle, -1,
                                                                          vrep.simx_opmode_buffer)

    def stop_move(self):
        error_code = vrep.simxSetJointTargetVelocity(self.client_id, self.left_motor_handle,  0, vrep.simx_opmode_streaming)
        error_code = vrep.simxSetJointTargetVelocity(self.client_id, self.right_motor_handle, 0, vrep.simx_opmode_streaming)

    def read_from_sensors(self):

        for i in range(0, 16):

            error_code, detection_state, detected_point, detected_object_handle, detected_surface_normal_vector = vrep.simxReadProximitySensor(self.client_id, self.sensor_handles[i], vrep.simx_opmode_buffer)

            dist = math.sqrt(np.sum(np.array(detected_point) ** 2))

            if dist < self.MIN_DETECTION_DIST:
                self.detect[i] = 0.0
            elif dist > self.MAX_DETECTION_DIST or detection_state is False:
                self.detect[i] = 1.0
            else:
                self.detect[i] = 1.0 - ((dist - self.MAX_DETECTION_DIST) / (self.MIN_DETECTION_DIST - self.MAX_DETECTION_DIST))

    def loop(self):

        self._init_values()

        self.obstacle_dist_stab_PID = PIDController(50.0)
        self.obstacle_follower_PID = PIDController(50.0)
        self.obstacle_dist_stab_PID.setCoefficients(2, 0, 0.5)
        self.obstacle_follower_PID.setCoefficients(2, 0, 0)

        self.targetDir = np.zeros(3)

        while True:

            self.tick()

            self.stop_move()
            self.read_values()

            # self.targetPos = Vector3(x=self.target_pos[0], y=self.target_pos[1], z=self.target_pos[2])
            self.targetPos = np.array(self.target_pos)

            # self.botPos = Vector3(x=self.bot_pos[0], y=self.bot_pos[1], z=self.bot_pos[2])
            self.botPos = np.array(self.bot_pos)

            # self.botEulerAngles = Vector3(x=self.bot_euler_angles[0], y=self.bot_euler_angles[1], z=self.bot_euler_angles[2])
            self.botEulerAngles = np.array(self.bot_euler_angles)

            self.read_from_sensors()

            self.targetPos[2] = self.botPos[2] = 0.0
            # qRot = Quaternion()
            # qRot.set_from_vector(self.botEulerAngles[2], Vector3( 0.0, 0.0, 1.0 ))
            # self.botDir = qRot.rotate( Vector3( 1.0, 0.0, 0.0 ) )

            qRot = self.create_quaternion(self.botEulerAngles[2], np.array([0.0, 0.0, 1.0]))
            self.botDir = self.rotate(qRot, np.array([1.0, 0.0, 0.0]))

            if self.state == State.MOVING:
                self.action_moving()
            elif self.state == State.ROTATING:
                self.action_rotating()
            elif self.state == State.ENVELOPING:
                self.action_enveloping()

    def action_moving(self):

        if self.detect[4] < 0.6:

            self.state = State.ROTATING
            # tmp = Quaternion()
            # tmp.set_from_vector(PI / 2.0, Vector3( 0.0, 0.0, 1.0 ))
            # self.targetDir = tmp.rotate(self.botDir)

            qRot = self.create_quaternion(PI / 2, np.array([0.0, 0.0, 1.0]))
            self.targetDir = self.rotate(qRot, self.botDir)

            return

        angle = self.angle_between_vectors(self.botDir, self.targetPos - self.botPos)

        if math.fabs(angle) > 1.0 / 180.0 * PI:
            vrep.simxSetJointTargetVelocity(self.client_id, self.left_motor_handle, self.WHEEL_SPEED + angle, vrep.simx_opmode_streaming)
            vrep.simxSetJointTargetVelocity(self.client_id, self.right_motor_handle, self.WHEEL_SPEED - angle, vrep.simx_opmode_streaming)
        else:
            vrep.simxSetJointTargetVelocity(self.client_id, self.left_motor_handle, self.WHEEL_SPEED, vrep.simx_opmode_streaming)
            vrep.simxSetJointTargetVelocity(self.client_id, self.right_motor_handle, self.WHEEL_SPEED, vrep.simx_opmode_streaming)

    def action_rotating(self):

        angle = self.angle_between_vectors(self.botDir, self.targetDir)

        if math.fabs(angle) > 5.0 / 180.0 * PI:
            vrep.simxSetJointTargetVelocity(self.client_id, self.left_motor_handle,   angle, vrep.simx_opmode_streaming)
            vrep.simxSetJointTargetVelocity(self.client_id, self.right_motor_handle, -angle, vrep.simx_opmode_streaming)
        else:
            self.state = State.ENVELOPING

    def action_enveloping(self):
        # tmp_dir = Quaternion()
        # tmp_dir.set_from_vector(PI / 2.0, Vector3( 0.0, 0.0, 1.0 ))
        # perp_bot_dir = tmp_dir.rotate(self.botDir)

        qRot = self.create_quaternion(PI / 2, np.array([0.0, 0.0, 1.0]))
        perp_bot_dir = self.rotate(qRot, self.botDir)

        angle = self.angle_between_vectors(perp_bot_dir, self.targetPos - self.botPos)

        if math.fabs(angle) < 5.0 / 180.0 * PI:
            self.state = State.MOVING
            return

        delta = self.detect[7] - self.detect[8]

        if delta < 0.0:
            obstacle_dist = self.detect[7] - self.INDENT_DIST
        else:
            obstacle_dist = self.detect[8] - self.INDENT_DIST

        u_obstacle_dist_stab = self.obstacle_dist_stab_PID.output(obstacle_dist)
        u_obstacle_follower = self.obstacle_follower_PID.output(delta)

        vrep.simxSetJointTargetVelocity(self.client_id, self.left_motor_handle, self.WHEEL_SPEED + u_obstacle_follower + u_obstacle_dist_stab - (1 - self.detect[4]), vrep.simx_opmode_streaming)
        vrep.simxSetJointTargetVelocity(self.client_id, self.right_motor_handle, self.WHEEL_SPEED - u_obstacle_follower - u_obstacle_dist_stab + (1 - self.detect[4]), vrep.simx_opmode_streaming)

    def tick(self):
        time.sleep(self.SLEEP_TIME)



####################################################

if __name__ == '__main__':

    bug2 = Bug2()

    bug2.loop()




