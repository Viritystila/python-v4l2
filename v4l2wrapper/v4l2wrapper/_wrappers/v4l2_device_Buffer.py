'''
    provides buffer functionality to device

    Requires that the device have V4L2_CAP_STREAMING and V4L2_BUF_TYPE_VIDEO_CAPTURE
    capabilities
'''

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Dimitrios Katsaros
# @Date:   2014-12-01 14:54:37
# @Email:  patcherwork@gmail.com
# @Last Modified by:   Dimitrios Katsaros
# @Last Modified time: 2016-11-30 13:09:53

# simple class used to hold the mmap capability data
class __mmap_capable(object):
    _MMAP_ENABLED = None

import v4l2
from v4l2wrapper._wrappers.v4l2_device_Base import (v4l2DeviceBase,
    DeviceError, LOGGING_LEVEL_FINE_GRAINED_DEBUG)
import numpy as np
import copy
import logging
import ctypes as ct
import errno
from builtins import range

try:
    import mmap
    __mmap_capable._MMAP_ENABLED = True
except ImportError as e:
    __mmap_capable._MMAP_ENABLED = False
    logging.error(str(e))
    logging.error('Disabling mmap functions')


#Overlay memory type has no documentation! will support if documentation is out
#DMABUF is not within this version of v4l2 header. Also, it is experimental so
#for now refraining from adding it.
_supportedBuffers = [v4l2.V4L2_MEMORY_MMAP, v4l2.V4L2_MEMORY_USERPTR]

class v4l2DeviceBuffer(__mmap_capable,v4l2DeviceBase):

    def __init__(self, tup):
        cap = tup[2]
        if not cap.capabilities & v4l2.V4L2_CAP_STREAMING:
            raise DeviceError("DeviceBuffer: Attempted to wrap device that doesn't support buffering")
        elif not cap.capabilities & v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE:
            raise DeviceError("DeviceBuffer: Attempted to wrap device that doesn't support video capture")
        super(v4l2DeviceBuffer, self).__init__(tup)
        self.device_wrapper_list.append('Buffer')
        self.buffersrequested = False
        self.buffersqueued    = False
        self.buffers = []
        self.dequeued_buffers = []

    def cleanup(self):
        try:
            if self.buffersqueued:
                self.dequeue_buffers()
        except Exception as e:
                self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Buffer: In cleanup: {}'.format(str(e)))
        try:
            for i in range(len(self.buffers)):
                try:
                    self.buffers[i].close()
                except e:
                    self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Buffer: In cleanup: {}'.format(str(e)))
        except:
            pass
        super(v4l2DeviceBuffer, self).cleanup()

    def request_buffers(self, bufcount=2, bufmemory=v4l2.V4L2_MEMORY_MMAP): #, buftype=v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE, bufmemory=v4l2.V4L2_MEMORY_MMAP):
        '''
        Requests buffers from the device

        bufcount : number of buffers, default = 2
        bufmemory: type of memory being used for buffers, default = v4l2.V4L2_MEMORY_MMAP,
            supports - v4l2.V4L2_MEMORY_MMAP, V4L2_MEMORY_USERPTR
        '''
        #perform cleanup if there are previous buffers
        self.cleanup_buffers()
        self.open_fd()

        #first check if the memory type can be handled
        if bufmemory not in _supportedBuffers:
             raise DeviceError("DeviceBuffer: Wrapper does not support {}".format(str(bufmemory)))

        self.buftype=v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        reqbufs = v4l2.v4l2_requestbuffers(count=bufcount, type=self.buftype, memory=bufmemory)
        res = self._set_ioctl(v4l2.VIDIOC_REQBUFS, reqbufs)
        if res != 0:
            raise DeviceError("DeviceBuffer: Device does not support {}".format(str(bufmemory)))
        self.bufcount=reqbufs.count
        self._bufmemory=reqbufs.memory
        self.buffersrequested = True

    def cleanup_buffers(self):
        if not self.buffersrequested:
            return
        for i in range(len(self.buffers)):
            try:
                self.buffers[i].close()
            except e:
                self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Buffer: In cleanup: {}'.format(str(e)))

        reqbufs = v4l2.v4l2_requestbuffers(count=0,
            type=v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE, memory=self._bufmemory)
        res = self._set_ioctl(v4l2.VIDIOC_REQBUFS, reqbufs)
        self.close_fd()

    def enqueue_buffers(self):
        '''
        enqueues all buffers
        Used to initialize buffering
        '''
        if not self.buffersrequested:
            raise DeviceError("DeviceBuffer: attempting to queue unrequested buffers")
        if self.buffersqueued:
            raise DeviceError("DeviceBuffer: attempting to requeue buffers")
        if self._bufmemory == v4l2.V4L2_MEMORY_USERPTR and not self.buffers:
            raise DeviceError("DeviceBuffer: attempting to enqueue buffers when user pointers have not been initialized")

        self.init_memory()
        buf = v4l2.v4l2_buffer(type=self.buftype, memory=self._bufmemory)

        try_qtec_mem = False

        for i in range(self.bufcount):
            buf.index = i
            if self._bufmemory == v4l2.V4L2_MEMORY_USERPTR:
                buf.m.userptr = ct.addressof(self.buffers[i])
                buf.length = self.format.fmt.pix.sizeimage
            ret = 0
            try:
                ret = self._set_ioctl(v4l2.VIDIOC_QBUF, buf)
            except IOError as e:
                #if an IO exception happens and we are using user pointers than probably the
                #memory isn't contiguous. So we will try using qtec memory instead
                if e.errno == errno.EIO:
                    try_qtec_mem = True
                    break
            if ret != 0:
                raise DeviceError("DeviceBuffer: Unable to enqbuf frame interval {}".format(i))

        if try_qtec_mem and self._bufmemory == v4l2.V4L2_MEMORY_USERPTR:
            self.logger.warning('Buffer: Fragmented memory detected, attempting to use QTec contiguous memory')
            self._qtec_mem_enqueue()
            self.buffersqueued = True
            return

        self.buffersqueued = True

    def _qtec_mem_enqueue(self):
        #first, try import
        try:
            from qtec_memory import qtec_memory as qtmem
        except:
            return False
        buf = v4l2.v4l2_buffer(type=self.buftype, memory=self._bufmemory)
        qt = qtmem()
        for i in range(self.bufcount):
            self.buffers[i] = qt.get_next_memory_frame(self.format.fmt.pix.sizeimage)

            buf.index = i
            buf.m.userptr = ct.addressof(self.buffers[i])
            buf.length = self.format.fmt.pix.sizeimage
            ret = self._set_ioctl(v4l2.VIDIOC_QBUF, buf)

            if ret != 0:
                raise DeviceError("DeviceBuffer: Unable to enqbuf frame interval {}".format(i))

    def dequeue_buffers(self):
        '''
        dequeues all buffers
        Used to remove all buffers from queue
        '''
        if not self.buffersqueued:
            raise DeviceError("DeviceBuffer: attempting to dequeue unqueued buffers")
        #Deque buffers
        buf = v4l2.v4l2_buffer(type=self.buftype, memory=self._bufmemory, index=0)
        for i in range(self.bufcount-len(self.dequeued_buffers)):
            ret = self._set_ioctl(v4l2.VIDIOC_DQBUF, buf)

        self.buffersqueued = False

    def init_memory(self):
        if self._bufmemory == v4l2.V4L2_MEMORY_MMAP:
            self.init_memorymapping()
        elif self._bufmemory == v4l2.V4L2_MEMORY_USERPTR:
            self.init_userptr()
        else:
            raise DeviceError('DeviceBuffer:Unsupported memory type initialization requested:')

    def init_userptr(self):
        '''
        creates user defined buffers in memory. used with V4L2_MEMORY_USERPTR
        WARNING: there is no garantee that the reserved memory is contiguous so
        this will cause an IO exception with VIDIOC_QBUF if the memory is fragmented
        '''
        if self._bufmemory != v4l2.V4L2_MEMORY_USERPTR:
            raise DeviceError('DeviceBuffer: Making a call to create user defined memory when set memory type is: {}'.format(self._bufmemory))
        #reset the buffer list just in case
        if not self.buffers:
            for i in self.buffers:
                if isinstance(i, mmap.mmap):
                    i.close()
                del i

        for i in range(self.bufcount):
            buf = (ct.c_char*self.format.fmt.pix.sizeimage)()
            self.buffers.append(buf)

    def init_memorymapping(self):
        '''
        creates buffers on the device and created mappings to the buffers.
        used with V4L2_MEMORY_MMAP
        '''
        if not self._MMAP_ENABLED:
            return False
        if self._bufmemory != v4l2.V4L2_MEMORY_MMAP:
            raise DeviceError('DeviceBuffer: Making a call to create memory mapping when set memory type is: {}'.format(self._bufmemory))
	    #reset the buffer list just in case
        if not self.buffers:
            for i in self.buffers:
                if isinstance(i, mmap.mmap):
                    i.close()
                del i
        buf = v4l2.v4l2_buffer(type=self.buftype, memory=self._bufmemory)

        for i in range(self.bufcount):
            buf.index = i
            self._set_ioctl(v4l2.VIDIOC_QUERYBUF, buf)
            self.buffers.append(mmap.mmap(self.fd, buf.length, flags=mmap.MAP_SHARED, prot=mmap.PROT_READ | mmap.PROT_WRITE, offset=buf.m.offset))
        return True

    def get_frame_info(self, requeue=True):
        '''
        Dequeues an available buffer and returns the buffer information

        input:
        - requeue : determines if older buffers should be requeued, defaults to true

        return value:
        - v4l2_buffer
        '''

        #call a requeue if there are dequeued buffers
        if requeue and len(self.dequeued_buffers) > 0:
            for i in range(len(self.dequeued_buffers)):
                self._set_ioctl(v4l2.VIDIOC_QBUF, self.dequeued_buffers[i])
            del self.dequeued_buffers[:]

        buf = v4l2.v4l2_buffer(type=self.buftype, memory=self._bufmemory)
        self._set_ioctl(v4l2.VIDIOC_DQBUF, buf)
        self.dequeued_buffers.append(buf)

        return copy.copy(buf)


    def get_frame(self, requeue=True):
        '''
        Dequeues an available buffer and returns the buffer information and the memory mapping.
        data is returned as raw byte data, stored in a string. Use get_fmt() to get a v4l2_format
        with all formatting information

        input:
        - requeue : determines if older buffers should be requeued, defaults to true

        return value:
        - (v4l2_buffer, mmap_of_the_buffer)
        '''
        if not self._MMAP_ENABLED:
            return None, None
        if len(self.buffers) == 0:
            raise DeviceError("DeviceBuffer: Attempting to get a frame when buffers have not been set")

        #call a requeue if there are dequeued buffers
        if requeue and len(self.dequeued_buffers) > 0:
            for i in range(len(self.dequeued_buffers)):
                self._set_ioctl(v4l2.VIDIOC_QBUF, self.dequeued_buffers[i])
            del self.dequeued_buffers[:]

        buf = v4l2.v4l2_buffer(type=self.buftype, memory=self._bufmemory)
        self._set_ioctl(v4l2.VIDIOC_DQBUF, buf)
        self.dequeued_buffers.append(buf)
        if self._bufmemory != v4l2.V4L2_MEMORY_MMAP:
            data = self.buffers[buf.index].read(buf.length)
            self.buffers[buf.index].seek(0)
        elif self._bufmemory != v4l2.V4L2_MEMORY_USERPTR:
            data = self.buffers[buf.index]

        return copy.copy(buf), data

    def get_formatted_frame(self, requeue=True):
        '''
        Dequeues an available buffer and returns the memory mapping.
        Formats the mapping into a numpy array with the correct formatting.

        input:
        - requeue : determines if older buffers should be requeued, defaults to true

        return value:
        - np_array_with_formatted_data
        '''
        if not self._MMAP_ENABLED:
            return None

        if len(self.buffers) == 0:
            raise DeviceError("DeviceBuffer: Attempting to get a frame when buffers have not been set")

        #call a requeue if there are dequeued buffers
        if requeue and len(self.dequeued_buffers) > 0:
            for i in range(len(self.dequeued_buffers)):
                self._set_ioctl(v4l2.VIDIOC_QBUF, self.dequeued_buffers[i])
            del self.dequeued_buffers[:]
        buf = v4l2.v4l2_buffer(type=self.buftype, memory=self._bufmemory, index=0)
        self._set_ioctl(v4l2.VIDIOC_DQBUF, buf)
        self.dequeued_buffers.append(buf)

        if self._bufmemory == v4l2.V4L2_MEMORY_MMAP:
            data = self.buffers[buf.index].read(buf.length)
            self.buffers[buf.index].seek(0)
        elif self._bufmemory == v4l2.V4L2_MEMORY_USERPTR:
            data = self.buffers[buf.index]


        #format data using formatting information

        #ensure that data has been retrieved from the buffer
        fmt = self.get_fmt()
        if fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_Y16:
            pixformat = '>u2'
        else:
            pixformat = np.uint8

        data = np.fromstring(data, pixformat)

        if len(data) > 0:
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

            if colors == 1:
                data = data.reshape((fmt.fmt.pix.height, fmt.fmt.pix.width))
            else:
                data = data.reshape((fmt.fmt.pix.height, fmt.fmt.pix.width, colors))

            #if fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_BGR32 or fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_BGR24:
            #    data = data[:, :, [2, 1, 0]]

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



