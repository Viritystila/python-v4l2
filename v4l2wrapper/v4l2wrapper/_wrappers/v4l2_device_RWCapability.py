'''
    Provides basic functionality for Read and Write system calls

    Requires that the device is compatible with the V4L2_CAP_READWRITE ioctl
    IMPORTANT NOTE: the device ioctl does not specify that BOTH read and write
    are supported!!! Thus, even if the wrapper does load, one of the functions
    may fail. In case of a failure an exception will be thrown.
'''

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Dimitrios Katsaros
# @Date:   2014-12-01 14:54:37
# @Email:  patcherwork@gmail.com
# @Last Modified by:   Dimitrios Katsaros
# @Last Modified time: 2016-11-30 13:45:14

import v4l2
from v4l2wrapper._wrappers.v4l2_device_Base import (v4l2DeviceBase,
    DeviceError, LOGGING_LEVEL_FINE_GRAINED_DEBUG)
import numpy as np
import select, errno, os
from numbers import Number

class v4l2DeviceRWCap(v4l2DeviceBase):
    '''
    Provides an interface for handling read/write system calls
    '''

    def __init__(self, tup):
        cap = tup[2]
        kwargs = tup[3]
        super(v4l2DeviceRWCap, self).__init__(tup)
        if not cap.capabilities & v4l2.V4L2_CAP_READWRITE:
            raise DeviceError("DeviceWRCap: Attempted to wrap device that doesn't support Read/Write")
        self.device_wrapper_list.append('RWCap')
        self.capture_timeout = 3
        if kwargs is not None:
            if 'capture_timeout' in kwargs:
                if isinstance(kwargs['capture_timeout'], Number):
                    self.capture_timeout = kwargs['capture_timeout']

    def cleanup(self):
        super(v4l2DeviceRWCap, self).cleanup()

    def read(self, size=-1):
        '''
        reads raw data from the device.
        Index is reset to start after read

        return value: string holding byte data
        '''
        if not self.fd:
            return ""
        self._strmoff_force_fd_reset = True
        #os.lseek(self.fd, 0, os.SEEK_SET)
        data = os.read(self.fd, size)
        #os.lseek(self.fd, 0, os.SEEK_SET)
        return data

    def raw_read(self, size=1):
        '''
        reads raw data from the device.

        return value: string holding byte data
        '''
        if not self.fd:
            return ""
        self._strmoff_force_fd_reset = True
        data = os.read(self.fd, size)
        return data

    def write(self, data, flush=False):
        '''
        writes to device
        '''
        if not self.fd:
            return ""
        self._strmoff_force_fd_reset = True
        #os.lseek(self.fd, 0, os.SEEK_SET)
        data = os.write(self.fd, data)
        #os.lseek(self.fd, 0, os.SEEK_SET)
        if flush:
            self.fd.flush()

    def select_for_read(self, timeout=3):
        '''
        runs the select function checking if fd is ready for reading from
        return boolean statement that can be used to determine if a read can be performed
        '''
        self._strmoff_force_fd_reset = True
        ret = select.select([self.fd], [], [], timeout)
        if not ret[0]:
            return False
        return True

    def capture(self, timeout=None, fmt=None):
        '''
        performs read from device and formats into correct image format
        returns a numpy structure with image information
        If image capture fails, None is returned
        '''

        if not fmt:
            fmt = self.get_fmt()
        else:
            self.set_fmt(fmt, strmoff=True)

        if not timeout:
            timeout = self.capture_timeout
        self._strmoff_force_fd_reset = True
        self.open_fd()
        if (timeout>=0):
            ready = select.select([self.fd], [], [], timeout)
            if not ready[0]:
                return None

        if  ((fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_Y10) or
             (fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_Y12) or
             (fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_Y16) or
             (fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_QTEC_GREEN16)) :
            pixformat = '<u2'
        elif ((fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_Y16_BE) or
             (fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_QTEC_GREEN16_BE)) :
            pixformat = '>u2'
        else:
            pixformat = np.uint8

        if fmt.fmt.pix.pixelformat == v4l2.v4l2_fourcc('Q', '5', '4', '0'):
            colors = 5
        elif fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_RGB32 or fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_BGR32:
            colors = 4
        elif fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_RGB24 or fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_BGR24:
            colors = 3
        elif fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_YUYV or fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_UYVY:
            colors = 2
        else:
            colors = 1

        buf = os.read(self.fd, fmt.fmt.pix.height * fmt.fmt.pix.width * colors)
        self.close_fd()
        data = np.frombuffer(buf, dtype=pixformat)

        if data is None or data.size == 0:
            return None

        if colors == 1:
            data = data.reshape((fmt.fmt.pix.height, fmt.fmt.pix.width))
        else:
            data = data.reshape((fmt.fmt.pix.height, fmt.fmt.pix.width, colors))

        if colors > 3:
            data = data[:, :, 0:3]

        if fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_BGR32 or fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_BGR24:
            data = data[:, :, [2, 1, 0]]

        if fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_YUYV or fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_UYVY:
            data = data.reshape((fmt.fmt.pix.height, fmt.fmt.pix.width / 2, 4)).astype('int32')
            rgb = np.empty((fmt.fmt.pix.height, fmt.fmt.pix.width / 2, 6))
            if fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_YUYV:
                y1 = data[:, :, 0]
                y2 = data[:, :, 2]
                u = data[:, :, 1]
                v = data[:, :, 3]
            else:
                y1 = data[:, :, 1]
                y2 = data[:, :, 3]
                v = data[:, :, 2]
                u = data[:, :, 0]

            rgb[:, :, 0] = (298 * (y1 - 16) + 409 * (v - 128) + 128) / 256
            rgb[:, :, 1] = (298 * (y1 - 16) - 100 * (u - 128) - 208 * (v - 128) + 128) / 256
            rgb[:, :, 2] = (298 * (y1 - 16) + 516 * (u - 128) + 128) / 256
            rgb[:, :, 3] = (298 * (y2 - 16) + 409 * (v - 128) + 128) / 256
            rgb[:, :, 4] = (298 * (y2 - 16) - 100 * (u - 128) - 208 * (v - 128) + 128) / 256
            rgb[:, :, 5] = (298 * (y2 - 16) + 516 * (u - 128) + 128) / 256
            rgb = np.clip(rgb, 0, 255)
            data = rgb.reshape((fmt.fmt.pix.height, fmt.fmt.pix.width, 3)).astype('uint8')
        return data


    def capture_byte_by_byte(self, fmt=None, timeout=None):
        '''
        performs read from device and formats into correct image format
        returns a numpy structure with image information
        If image capture fails, None is returned

        This version reads from the buffer byte by byte,checking if the fd is set.
        It is a slower version that protects from performing reads that are larger
        than the data in the buffer.
        '''
        if not fmt:
            fmt = self.get_fmt()
        else:
            self.set_fmt(fmt, strmoff=True)

        if not timeout:
            timeout = self.capture_timeout
        self._strmoff_force_fd_reset = True
        self.open_fd()
        if (timeout>=0):
            ready = select.select([self.fd], [], [], timeout)
            if not ready[0]:
                return None

        if  ((fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_Y10) or
             (fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_Y12) or
             (fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_Y16) or
             (fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_QTEC_GREEN16)) :
            pixformat = '<u2'
        elif ((fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_Y16_BE) or
             (fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_QTEC_GREEN16_BE)) :
            pixformat = '>u2'
        else:
            pixformat = np.uint8

        if fmt.fmt.pix.pixelformat == v4l2.v4l2_fourcc('Q', '5', '4', '0'):
            colors = 5
        elif fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_RGB32 or fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_BGR32:
            colors = 4
        elif fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_RGB24 or fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_BGR24:
            colors = 3
        elif fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_YUYV or fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_UYVY:
            colors = 2
        else:
            colors = 1

        dsize = fmt.fmt.pix.height * fmt.fmt.pix.width * colors
        data = np.empty([dsize], dtype=pixformat)

        for i in range(fmt.fmt.pix.height * fmt.fmt.pix.width * colors):
            if self.select_for_read(timeout=1):
                data[i] = ord(self.raw_read())
            else:
                return None
        self.close_fd()

        if colors == 1:
            data = data.reshape((fmt.fmt.pix.height, fmt.fmt.pix.width))
        else:
            data = data.reshape((fmt.fmt.pix.height, fmt.fmt.pix.width, colors))

        if colors > 3:
            data = data[:, :, 0:3]

        if fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_BGR32 or fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_BGR24:
            data = data[:, :, [2, 1, 0]]

        if fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_YUYV or fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_UYVY:
            data = data.reshape((fmt.fmt.pix.height, fmt.fmt.pix.width / 2, 4)).astype('int32')
            rgb = np.empty((fmt.fmt.pix.height, fmt.fmt.pix.width / 2, 6))
            if fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_YUYV:
                y1 = data[:, :, 0]
                y2 = data[:, :, 2]
                u = data[:, :, 1]
                v = data[:, :, 3]
            else:
                y1 = data[:, :, 1]
                y2 = data[:, :, 3]
                v = data[:, :, 2]
                u = data[:, :, 0]

            rgb[:, :, 0] = (298 * (y1 - 16) + 409 * (v - 128) + 128) / 256
            rgb[:, :, 1] = (298 * (y1 - 16) - 100 * (u - 128) - 208 * (v - 128) + 128) / 256
            rgb[:, :, 2] = (298 * (y1 - 16) + 516 * (u - 128) + 128) / 256
            rgb[:, :, 3] = (298 * (y2 - 16) + 409 * (v - 128) + 128) / 256
            rgb[:, :, 4] = (298 * (y2 - 16) - 100 * (u - 128) - 208 * (v - 128) + 128) / 256
            rgb[:, :, 5] = (298 * (y2 - 16) + 516 * (u - 128) + 128) / 256
            rgb = np.clip(rgb, 0, 255)
            data = rgb.reshape((fmt.fmt.pix.height, fmt.fmt.pix.width, 3)).astype('uint8')

        return data
