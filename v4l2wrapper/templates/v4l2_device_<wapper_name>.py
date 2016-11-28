''' Template for a device wrapper. Make sure the name of the file is v4l2_device_
'''


from v4l2_device_Base import v4l2DeviceBase, DeviceError, LOGGING_LEVEL_FINE_GRAINED_DEBUG
import fcntl
import v4l2
import numpy as np
import ctypes
import sys

class v4l2Device<wrapper_name>(v4l2DeviceBase):

    def __init__(self, tup):

        super(v4l2Device<wrapper_name>, self).__init__(tup)

        cap = tup[2]
        kwdict = tup[3]

        #perform initialization of wrapper. If something fails, raise a DeviceError

        #once initialization is completed, add the wrapper name to the device wrapper list
        #this is useful for idenitfying the available functionality of the final wrapper
        self.device_wrapper_list.append('<wrapper_name>')

    #deletion function, do not change
    def __del__(self):
        if self._perform_cleanup:
            self.cleanup()

    #cleanup function.
    def cleanup(self):
        try:
            #perform device cleanup operations here
        except Exception,e:
            self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG,
                '<wrapper_name>: In cleanup: {}'.format(str(e)))
        super(v4l2DeviceTestgen, self).cleanup()
