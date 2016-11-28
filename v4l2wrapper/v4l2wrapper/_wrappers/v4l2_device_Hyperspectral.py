'''
    Provides additional functionality for hyperspectral devices
'''

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Dimitrios Katsaros
# @Date:   2014-12-01 14:54:37
# @Email:  patcherwork@gmail.com
# @Last Modified by:   Dimitrios Katsaros
# @Last Modified time: 2016-11-29 17:20:46

import v4l2
from v4l2wrapper._wrappers.v4l2_device_Base import (
    v4l2DeviceBase, DeviceError, LOGGING_LEVEL_FINE_GRAINED_DEBUG)
import numpy as np
import select, errno, os

DEFAULT_MOSAIC = np.array([[739,753,727,713,688],
                  [638,647,630,621,664],
                  [843,854,833,638,655],
                  [600,609,874,864,672],
                  [790,802,778,765,673]])

class v4l2DeviceHyperspectral(v4l2DeviceBase):
    '''
    Provides an interface for handling read/write system calls
    '''

    def __init__(self, tup):
        cap = tup[2]
        kwargs = tup[3]
        super(v4l2DeviceHyperspectral, self).__init__(tup)
        type_ctrl = self.find_ctrl('Sensor Type')
        qry = self.query_ext_ctrl(type_ctrl.id)
        stype = self.get_ext_ctrl(qry)
        if stype.controls[0].string[-2:] != "IR":
            raise DeviceError("Hyperspectral: sensor is not a hyperspectral sensor")
        self.device_wrapper_list.append('Hyperspectral')

    def cleanup(self):
       	super(v4l2DeviceHyperspectral, self).cleanup()

    def capture_hspec_image(self, bands=None, whiteref=None, blackref=None, v4l2fmt=v4l2.V4L2_PIX_FMT_Y16_BE, mosaic=DEFAULT_MOSAIC):
        """ returns a dictionary with the bands specified by the user. If no
            bands are specified, all bands are returned. If both whiteref and blackref
            are defined, the relative reflectance of the image is calcuated
        """

        fmt = self.get_fmt()
        fmt.fmt.pix.pixelformat = v4l2fmt
        self.set_fmt(fmt, strmoff=True)
        img = self.capture()
        self._stream_ioctl_off()
        #perform relative reflectance

        if whiteref != None and blackref != None:
            if (whiteref.shape == blackref.shape == img.shape) and (whiteref.dtype == blackref.dtype == img.dtype):
                mask = img < blackref
                img = (((img-blackref).astype(np.float32)/(whiteref-blackref)) * np.iinfo(img.dtype).max).astype(img.dtype)
                img[mask] = 0
            else:
                raise DeviceError("The shape or type of the whiteref,blackref and captured image "
                    "do not match for relative reflectance")

        mx,my = mosaic.shape
        if bands == None:
            bands = mosaic.ravel()
        bandlist = {}
        for band in bands:
            xl, yl = np.where(mosaic == band)
            if xl.size == 0 or yl.size == 0:
                raise Exception("Band {} is not part of the mosaic".format(band))
            bandlist[band] = img[xl[0]::mx,yl[0]::my]

        return bandlist
