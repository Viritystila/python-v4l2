'''
	Provides streaming functionality to device

'''

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Dimitrios Katsaros
# @Date:   2014-12-01 14:54:37
# @Email:  patcherwork@gmail.com
# @Last Modified by:   Dimitrios Katsaros
# @Last Modified time: 2016-11-30 13:38:19

import v4l2
from v4l2wrapper._wrappers.v4l2_device_Base import (
    DeviceError, LOGGING_LEVEL_FINE_GRAINED_DEBUG)
from v4l2wrapper._wrappers.v4l2_device_Buffer import v4l2DeviceBuffer
import ctypes
from fractions import Fraction

class v4l2DeviceStream(v4l2DeviceBuffer):

    def __init__(self, tup):
        cap = tup[2]
        if not cap.capabilities & v4l2.V4L2_CAP_STREAMING:
            raise DeviceError("StreamDevice: Attempted to wrap device that doesn't support streaming")
        super(v4l2DeviceStream, self).__init__(tup)

        frmivalenum = v4l2.v4l2_frmivalenum()
        frmivalenum.index = 0
        frmivalenum.pixel_format = self.format.fmt.pix.pixelformat
        frmivalenum.width = self.format.fmt.pix.width
        frmivalenum.height = self.format.fmt.pix.height

        ret = self._set_ioctl(v4l2.VIDIOC_ENUM_FRAMEINTERVALS, frmivalenum)
        self.frmivalenum = frmivalenum

        streamparm = v4l2.v4l2_streamparm()
        streamparm.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        ret = self._set_ioctl(v4l2.VIDIOC_G_PARM, streamparm)

        self.default_strmparm = streamparm

        self.device_wrapper_list.append('Stream')
        self.streaming = False

    def cleanup(self):
        try:
            if self.streaming:
                self.stream_off()
        except Exception as e:
            self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Stream: In cleanup: {}'.format(str(e)))
        try:
            ret = self._set_ioctl(v4l2.VIDIOC_S_PARM, self.default_strmparm)
        except Exception as e:
            self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Stream: In cleanup: {}'.format(str(e)))
        super(v4l2DeviceStream, self).cleanup()

    def stream_off(self):
        '''
            deactivates streaming
        '''
        if self.streaming:
            try:
                self._stream_ioctl_off()
                self.dequeue_buffers()
            except (IOError, DeviceError) as e:
                self.logger.debug('Stream: at stream_off: {}'.format(str(e)))

        self.streaming = False

    def stream_on(self):
        '''
            activates streaming
        '''
        if not self.buffersrequested:
            return False
        #ignoring if the buffers are already enqueued
        try:
            super(v4l2DeviceStream, self).enqueue_buffers()
        except DeviceError:
            pass
        buffertype = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        res = self._set_ioctl(v4l2.VIDIOC_STREAMON, ctypes.c_int(buffertype))
        self.streaming = True
        return res == 0

    def cleanup_stream(self):
        self.stream_off()
        self.cleanup_buffers()

    def set_fps(self, value):
        frc = Fraction(value).limit_denominator()
        self.set_tpf(frc.denominator, frc.numerator)

    def set_tpf(self, num, denom):
        streamparm = v4l2.v4l2_streamparm()
        streamparm.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        streamparm.parm.capture.timeperframe.numerator = num
        streamparm.parm.capture.timeperframe.denominator = denom
        if self._set_ioctl(v4l2.VIDIOC_S_PARM, streamparm)!=0:
            raise DeviceError('Unable to set framerate {}/{}'.format(nom,denom))

    def get_real_tpf(self, average=1):
        '''
            gets the actual time per frame by calculating the difference
            between two consecutive frames.

            input:
             average: Sets the number of samples to average over
        '''
        total = 0
        for _ in range(average):
            buf0 = self.get_frame_info()
            buf1 = self.get_frame_info()
            real_diff = buf0.timestamp.secs*1000000 +  buf0.timestamp.usecs
            real_diff -= buf1.timestamp.secs*1000000 +  buf1.timestamp.usecs
            total += abs(real_diff)
        return total / average

    def get_expected_tpf(self):
        '''
            get tpf as stated by the device stream param
        '''
        streamparm = v4l2.v4l2_streamparm()
        streamparm.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        ret = self._set_ioctl(v4l2.VIDIOC_G_PARM, streamparm)
        if ret != 0:
            raise DeviceError('Unable to get v4l2 streamparm')
        expected_diff = (streamparm.parm.capture.timeperframe.numerator * 1000000)\
                        /streamparm.parm.capture.timeperframe.denominator
        return expected_diff

    def get_expected_num_denom(self):
        '''
            get tpf numerator/denominator as a tuple
        '''
        streamparm = v4l2.v4l2_streamparm()
        streamparm.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        ret = self._set_ioctl(v4l2.VIDIOC_G_PARM, streamparm)
        if ret != 0:
            raise DeviceError('Unable to get v4l2 streamparm')
        return (streamparm.parm.capture.timeperframe.numerator,
                        streamparm.parm.capture.timeperframe.denominator)

    def reset_stream(self):
        self.stream_off()
        return self._set_ioctl(v4l2.VIDIOC_S_PARM, self.default_strmparm)
