'''
    Basic cropping functionality
'''

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Dimitrios Katsaros
# @Date:   2014-12-01 14:54:37
# @Email:  patcherwork@gmail.com
# @Last Modified by:   Dimitrios Katsaros
# @Last Modified time: 2016-11-29 17:32:39

import v4l2
from v4l2wrapper._wrappers.v4l2_device_Base import (v4l2DeviceBase,
    DeviceError, LOGGING_LEVEL_FINE_GRAINED_DEBUG)
import errno

class v4l2DeviceCrop(v4l2DeviceBase):

    def __init__(self, tup):
        cap = tup[2]
        kwargs = tup[3]
        super(v4l2DeviceCrop, self).__init__(tup)

        #set up default cropping and center cropping to the middle of the sensior
        try:
            self.defaultcrop =  self.get_crop(target=v4l2.V4L2_SEL_TGT_CROP_DEFAULT)
            self.defaultcrop.target = v4l2.V4L2_SEL_TGT_CROP
            if self._try_reset(kwargs):
                self.reset_cropping()
                #self.center_img()

        except IOError as e:
            raise DeviceError("Crop: Cropping not supported by device")

        self.device_wrapper_list.append('Crop')

    def cleanup(self):
        try:
            self.reset_cropping()
        except Exception as e:
            self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Crop: In cleanup: {}'.format(str(e)))
        super(v4l2DeviceCrop, self).cleanup()

    def reset_cropping(self):
        self.reset_fmt(strmoff=True)
        self.set_selection(self.defaultcrop)

    def get_crop(self, target=v4l2.V4L2_SEL_TGT_CROP):
        if target >= 0x0100:
            self.logger.warning('Cropping: Using get_crop with compose target')
        crop = v4l2.v4l2_selection(type=v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE,
            target=target)
        try:
            self._set_ioctl(v4l2.VIDIOC_G_SELECTION, crop)
        except Exception as e:
            if e.errno == errno.ENOSPC:
                crop.rectangles = 64
                crop.pr = (v4l2.v4l2_ext_rect * 64)()
                self._set_ioctl(v4l2.VIDIOC_G_SELECTION, crop)
            else:
                raise
        return crop

    def get_compose(self, target=v4l2.V4L2_SEL_TGT_COMPOSE):
        if target < 0x0100:
            self.logger.warning('Cropping: Using get_compose with crop target')
        compose = v4l2.v4l2_selection(type=v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE,
            target=target)
        try:
            self._set_ioctl(v4l2.VIDIOC_G_SELECTION, compose)
        except Exception as e:
            if e.errno == errno.ENOSPC:
                compose.rectangles = 64
                compose.pr = (v4l2.v4l2_ext_rect * 64)()
                self._set_ioctl(v4l2.VIDIOC_G_SELECTION, compose)
            else:
                raise
        return compose

    def set_selection(self, selection, strmoff=True):
        if strmoff is True:
            self._stream_ioctl_off()
        return self._set_ioctl(v4l2.VIDIOC_S_SELECTION, selection)

    def set_crop_rect(self, width=None, height=None, top=None, left=None):
        crop = self.get_crop()
        if left:
            crop.r.left = left
        if top:
            crop.r.top  = top
        if width:
            crop.r.width = width
        if height:
            crop.r.height = height
        return self.set_selection(crop)

    def get_crop_rect(self):
        crop = self.get_crop()
        return (crop.r.left, crop.r.top, crop.r.width, crop.r.height)


    def center_img(self):
        crop = self.get_crop()
        comp = self.get_compose(v4l2.V4L2_SEL_TGT_COMPOSE_DEFAULT)
        crop.r.left = abs((comp.r.width-crop.r.width)/2)
        crop.r.top = abs((comp.r.height-crop.r.height)/2)
        return self.set_selection(crop)
