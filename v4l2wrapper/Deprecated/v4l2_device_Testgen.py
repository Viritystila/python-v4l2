'''
    Basic wrapper for performing operations related to the
    Testgen Capability

'''


from v4l2wrapper._wrappers.v4l2_device_Base import v4l2DeviceBase, DeviceError, LOGGING_LEVEL_FINE_GRAINED_DEBUG
import fcntl
import v4l2
import numpy as np
import ctypes
import sys

TESTGEN_KEYWORD = 'TestgenDevice'

class v4l2DeviceTestgen(v4l2DeviceBase):

    def __init__(self, tup):

        super(v4l2DeviceTestgen, self).__init__(tup)

        cap = tup[2]
        kwdict = tup[3]

        if not TESTGEN_KEYWORD in kwdict:
            raise DeviceError('Testgen: {} keyword not set, cannot set Testgen device'.format(
                                   TESTGEN_KEYWORD))
        fmt = self.get_fmt()

        fmtdesc = v4l2.v4l2_fmtdesc()
        fmtdesc.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        fmtdesc.index = 0
        fmt.fmt.pix.pixelformat == v4l2.V4L2_PIX_FMT_GREY
        fmt.fmt.pix.width=10*1024
        fmt.fmt.pix.height=10*1024

        for fmtdesc in self.format_iterator():
            if fmtdesc.pixelformat == v4l2.V4L2_PIX_FMT_RGB24: #Color Sesor
                fmt.fmt.pix.pixelformat = v4l2.V4L2_PIX_FMT_QTECRGBPP40
                break

        self.fmt = self.set_fmt(fmt)
        self._stream_ioctl_off()

        self.testgen_device = kwdict[TESTGEN_KEYWORD]

        self.testgen_fd, self.testgen_fmt = self._open_testgen(self.testgen_device)

        self.device_wrapper_list.append('Testgen')

    def __del__(self):
        if self._perform_cleanup:
            self.cleanup()

    def cleanup(self):
        try:
            self._testgen_stream_ioctl_off()
            self.testgen_fd.close()
        except Exception,e:
            self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Testgen: In cleanup: {}'.format(str(e)))
        super(v4l2DeviceTestgen, self).cleanup()

    def _testgen_stream_ioctl_off(self):
        '''
            used to disable streaming if enabled beforehand
        '''
        try:
            fcntl.ioctl(self.testgen_fd, v4l2.VIDIOC_STREAMOFF, ctypes.c_int(v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE))
        except IOError:
            pass
        return

    def _open_testgen(self,filename):
        fd = open(filename, 'wb', buffering=0)
        fmt = v4l2.v4l2_format()
        fmt.type = v4l2.V4L2_BUF_TYPE_VIDEO_OUTPUT
        fcntl.ioctl(fd, v4l2.VIDIOC_G_FMT, fmt)
        return (fd,fmt)

    def check_testgen(self, datain):
        datain.astype(np.uint8).tofile(self.testgen_fd)

        last_err=0
        failed=False
        #FIXME #319 #442
        data = np.fromfile(self.fd, dtype=np.uint8, count=self.fmt.fmt.pix.sizeimage)
        self._stream_ioctl_off()
        self._testgen_stream_ioctl_off()
        if not np.array_equal(data,datain):
            for pos in range(self.fmt.fmt.pix.sizeimage):
                if data[pos] != datain[pos]:
                    print "Error at position {0} read {1}!= in {2} Last error is {3} bytes apart".format(pos,data[pos],datain[pos],pos-last_err)
                    print 'mem snapshot:'
                    maxpr = pos + 20
                    minpr = pos - 10
                    if minpr < 0:
                        minpr = 0
                    if maxpr > self.fmt.fmt.pix.sizeimage:
                        maxpr = self.fmt.fmt.pix.sizeimage
                    print 'testgen data:'
                    for i in range(minpr, maxpr):
                        if i == pos:
                            sys.stdout.write(' *')
                        print(data[i]),
                    print
                    print 'datain:'
                    for i in range(minpr, maxpr):
                        if i == pos:
                            sys.stdout.write(' *')
                        print(datain[i]),
                    print
                    print 'position in image:({},{})'.format(pos/self.fmt.fmt.pix.width, pos%self.fmt.fmt.pix.width)
                    print 'size of image:({},{})'.format(self.fmt.fmt.pix.height, self.fmt.fmt.pix.width)
                    print
                    last_err=pos
                    if failed:
                        break
                    failed=True

        return failed

    def print_testgen(self, datain, minpr=0, maxpr=100):
        datain.astype(np.uint8).tofile(self.testgen_fd)
        np.set_printoptions(threshold='nan')
        data = np.fromfile(self.fd, dtype=np.uint8, count=self.fmt.fmt.pix.sizeimage)
        print 'tg read size', self.fmt.fmt.pix.sizeimage
        print 'datain size', datain.size
        self._stream_ioctl_off()
        self._testgen_stream_ioctl_off()
        print 'printing data for range({},{})'.format(minpr,maxpr)
        print 'datain'
        print '*'*100
        for i in xrange(minpr, maxpr):
            print(datain[i]),
        print
        print '*'*100
        print
        print 'tg_data'
        print '*'*100
        for i in xrange(minpr, maxpr):
                    print(data[i]),
        print
        print '*'*100
        print 'equality of testgen compared to input:',  np.array_equal(data,datain)
