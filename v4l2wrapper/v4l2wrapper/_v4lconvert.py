#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Dimitrios Katsaros
# @Date:   2014-12-01 14:54:37
# @Email:  patcherwork@gmail.com
# @Last Modified by:   Dimitrios Katsaros
# @Last Modified time: 2016-11-30 09:21:14

''' interface with libv4lconvert '''
''' provides wrapper for converting read images into a different format'''

import ctypes, logging, v4l2, select, time, os
import numpy as np


#making it as a context manager
class v4l2_Capture_Data_Converter(object):
    ''' context manager for handling data conversion '''

    def __init__(self, device_wrapper, target_format):
        self.device_wrapper = device_wrapper
        self.target_format = target_format
        self.logger = self.device_wrapper.logger.getChild(__name__)
        try:
            self._libso = ctypes.CDLL('libv4l2.so.0', use_errno=True)
        except:
            self._libso = None

    def __enter__(self):
        if 'RWCap' not in self.device_wrapper.device_wrapper_list:
            self.logger.warning('Device wrapper does not support RW Capability, returning None')
            return None

        self.device_wrapper.open_fd()
        if self._libso is not None:
            self._data_pointer = self._libso.v4lconvert_create(self.device_wrapper.fd.fileno())
        #    res = _libso.v4lconvert_try_format(self._data_pointer, ctypes.addressof(self.target_format),
        #            self.device_wrapper.get_fmt())
        #    if res == 0:
            return self.converted_capture
        #    else:
        #        return None
        else:
            self.logger.warning("Converter could not be initialized, data will not be converted!")
            self._data_pointer = None
            return self.device_wrapper.capture


    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._data_pointer:
            _libso.v4lconvert_destroy(self._data_pointer)
        self.device_wrapper.close_fd()
        return False

    def converted_capture(self, timeout=None, fmt=None):
        dev = self.device_wrapper
        if not timeout:
            timeout = self.device_wrapper.capture_timeout
        if fmt:
            self.target_format = fmt.fmt.pix.pixelformat

        dev.open_fd()
        if (timeout>=0):
            ready = select.select([dev.fd], [], [], timeout)
            if not ready[0]:
                return None

        if  ((self.target_format == v4l2.V4L2_PIX_FMT_Y10) or
             (self.target_format == v4l2.V4L2_PIX_FMT_Y12) or
             (self.target_format == v4l2.V4L2_PIX_FMT_Y16) or
             (self.target_format == v4l2.V4L2_PIX_FMT_QTEC_GREEN16)) :
            pixformat = '<u2'
        elif ((self.target_format == v4l2.V4L2_PIX_FMT_Y16_BE) or
             (self.target_format == v4l2.V4L2_PIX_FMT_QTEC_GREEN16_BE)) :
            pixformat = '>u2'
        else:
            pixformat = np.uint8

        if self.target_format == v4l2.v4l2_fourcc('Q', '5', '4', '0'):
            colors = 5
        elif (self.target_format == v4l2.V4L2_PIX_FMT_RGB32 or
              self.target_format == v4l2.V4L2_PIX_FMT_BGR32):
            colors = 4
        elif (self.target_format == v4l2.V4L2_PIX_FMT_RGB24 or
              self.target_format == v4l2.V4L2_PIX_FMT_BGR24):
            colors = 3
        elif (self.target_format == v4l2.V4L2_PIX_FMT_YUYV or
              self.target_format == v4l2.V4L2_PIX_FMT_UYVY):
            colors = 2
        else:
            colors = 1

        dev_fmt = dev.get_fmt()
        if not fmt:
            fmt = dev.get_fmt()
            fmt.fmt.pix.pixelformat = self.target_format
            fmt.fmt.pix.bytesperline = fmt.fmt.pix.width * colors
            fmt.fmt.pix.sizeimage = fmt.fmt.pix.width * fmt.fmt.pix.height * colors

        if self._libso.v4lconvert_needs_conversion(self._data_pointer, ctypes.addressof(dev_fmt), ctypes.addressof(fmt)) == 1:
            tar_buff = (ctypes.c_char*fmt.fmt.pix.sizeimage)()
            tar_addr = ctypes.addressof(tar_buff)
            tar_addr = ctypes.cast(tar_addr, ctypes.POINTER(ctypes.c_ubyte))
            #read from file
            data = dev.raw_read(dev_fmt.fmt.pix.sizeimage)
            src_buff= (ctypes.c_char*dev_fmt.fmt.pix.sizeimage).from_buffer_copy(data)
            src_addr = ctypes.addressof(src_buff)
            src_addr = ctypes.cast(src_addr, ctypes.POINTER(ctypes.c_ubyte))
            res = self._libso.v4lconvert_convert(self._data_pointer, ctypes.pointer(dev_fmt), ctypes.pointer(fmt),
                            src_addr, dev_fmt.fmt.pix.sizeimage,
                            tar_addr, fmt.fmt.pix.sizeimage)
            if res != 0:
                data = np.fromstring(tar_buff, dtype=pixformat, count=(fmt.fmt.pix.height * fmt.fmt.pix.width * colors))
            else:
                data = None
        else:
            buf = os.read(self.fd, fmt.fmt.pix.height * fmt.fmt.pix.width * colors)
            self.close_fd()
            data = np.frombuffer(buf, dtype=pixformat)
        dev.close_fd()

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