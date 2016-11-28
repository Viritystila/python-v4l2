'''
    Basic wrapper for performing operations related to the
    Xform Capability

'''

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Dimitrios Katsaros
# @Date:   2014-12-01 14:54:37
# @Email:  patcherwork@gmail.com
# @Last Modified by:   Dimitrios Katsaros
# @Last Modified time: 2016-11-29 17:21:15


from v4l2wrapper._wrappers.v4l2_device_Base import (
    v4l2DeviceBase, DeviceError, LOGGING_LEVEL_FINE_GRAINED_DEBUG)
import fcntl
import v4l2

XFORM_GAIN_KEYWORD = 'XFormGainDevice'
XFORM_DIST_KEYWORD = 'XFormDistDevice'

class v4l2DeviceXform(v4l2DeviceBase):

    def __init__(self, tup):

        super(v4l2DeviceXform, self).__init__(tup)
        cap = tup[2]
        kwdict = tup[3]
        self.open_fd()

        if not XFORM_GAIN_KEYWORD in kwdict or not XFORM_DIST_KEYWORD in kwdict:
            raise DeviceError('XForm: {}, {} keywords not set, cannot set Xform device'.format(
                                   XFORM_GAIN_KEYWORD,
                                   XFORM_DIST_KEYWORD))

        dist_map = self.find_ctrl('Distortion Map')
        if dist_map is None:
            raise DeviceError('Xform: Distortion Map control not found')
        gain_map = self.find_ctrl('Gain Map')
        if gain_map is None:
            raise DeviceError('Xform: Gain Map control not found')
        extra_gain = self.find_ctrl('Extra Gain for Gain Map')
        if extra_gain is None:
            raise DeviceError('Xform: Extra Gain for Gain Map control not found')

        self.xform_gain_device = kwdict[XFORM_GAIN_KEYWORD]
        self.xform_dist_device = kwdict[XFORM_DIST_KEYWORD]
        self.dist_map = dist_map
        self.gain_map = gain_map
        self.extra_gain = extra_gain
        self.xform_off()

        self.gain_fd, gain_fmt = self._xform_open_gain()
        self.dist_fd, dist_fmt = self._xform_open_dist()
        self.gain_fmt = gain_fmt
        self.gain_defaultfmt = gain_fmt
        self.dist_fmt = dist_fmt
        self.dist_defaultfmt = dist_fmt

        if self.gain_fd is None:
            raise DeviceError('Xform: failed to open gain')
        if self.dist_fd is None:
            raise DeviceError('Xform: failed to open dist')

        self.device_wrapper_list.append('Xform')

    def cleanup(self):
        try:
            self.gain_fd.close()
        except Exception as e:
            self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Xform: In cleanup: {}'.format(str(e)))
        try:
            self.dist_fd.close()
        except Exception as e:
            self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Xform: In cleanup: {}'.format(str(e)))
        try:
            self.xform_off()
        except Exception as e:
            self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Xform: In cleanup: {}'.format(str(e)))
        super(v4l2DeviceXform, self).cleanup()

    def xform_off(self):
        self._stream_ioctl_off()
        self.set_ctrl(self.dist_map.id, 0)
        self.set_ctrl(self.gain_map.id, 0)
        self.set_ctrl(self.extra_gain.id, 1)

    def _xform_open_gain(self):
       	(a,b) = self._xform_open(self.xform_gain_device)
        return (a,b)

    def _xform_open_dist(self):
        (a,b) = self._xform_open(self.xform_dist_device)
        return (a,b)

    def _xform_open(self, filename):
        fd = open(filename , 'wb', buffering=0)
        fmt = v4l2.v4l2_format(type=v4l2.V4L2_BUF_TYPE_VIDEO_OUTPUT)
        fcntl.ioctl(fd, v4l2.VIDIOC_G_FMT, fmt)
        return (fd, fmt)

    def set_gainmap(self,buf):
        n_pixels=self.gain_fmt.fmt.pix.height * self.gain_fmt.fmt.pix.width
        for a in range(0,n_pixels,len(buf)):
            self.gain_fd.write(buf)
        self.gain_fd.close()