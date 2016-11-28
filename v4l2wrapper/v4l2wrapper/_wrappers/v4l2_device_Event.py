'''
    Contains Event handling

    Currently the cameras only support V4L2_EVENT_CTRL type
    events
'''

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Dimitrios Katsaros
# @Date:   2014-12-01 14:54:37
# @Email:  patcherwork@gmail.com
# @Last Modified by:   Dimitrios Katsaros
# @Last Modified time: 2016-11-29 17:20:29

import v4l2
from v4l2wrapper._wrappers.v4l2_device_Base import (v4l2DeviceBase,
    LOGGING_LEVEL_FINE_GRAINED_DEBUG)
import select

class v4l2DeviceEvents(v4l2DeviceBase):

    def __init__(self, tup):
        cap = tup[2]
        super(v4l2DeviceEvents, self).__init__(tup)

        self.device_wrapper_list.append('Event')

    def cleanup(self):
        try:
            self.reset_events()
        except Exception as e:
            self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Events: In cleanup: {}'.format(str(e)))
        super(v4l2DeviceEvents, self).cleanup()

    def subscribe_event(self, type, id=0, flags=None):
        self.open_fd()
        eventsub = v4l2.v4l2_event_subscription(type=type, id=id)
        if flags:
            eventsub.flags = flags
        self._set_ioctl(v4l2.VIDIOC_SUBSCRIBE_EVENT, eventsub)

    def unsubscribe_event(self, type):
        eventunsub = v4l2.v4l2_event_subscription(type=type)
        self._set_ioctl(v4l2.VIDIOC_UNSUBSCRIBE_EVENT, eventunsub)

    def reset_events(self):
        self.unsubscribe_event(type=v4l2.V4L2_EVENT_ALL)

    def get_event(self, timeout=0.5):
        if not self.check_for_event(timeout):
            return None
        event = v4l2.v4l2_event()
        self._set_ioctl(v4l2.VIDIOC_DQEVENT, event)
        return event

    def check_for_event(self, timeout=0):
        ''' attempts to get an event, also throws event exceptions '''
        epoll = select.epoll()
        epoll.register(self.fd, select.EPOLLPRI)

        if epoll.poll(timeout):
            epoll.close()
            return True
        epoll.close()
        return False

    def pprint_event(self, event):
        print ('=== event informaton ===')
        print ('type:', event.type)
        print ('pending:', event.pending)
        print ('sequence:', event.sequence)
        print ('timestamp:', event.timestamp)
        print ('id:', event.id)
        #print 'reserved:', event.reserved