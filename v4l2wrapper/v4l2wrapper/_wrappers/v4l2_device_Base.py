'''
    Device base class
    ensure that derived classes have the
    correct device tag
'''

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Dimitrios Katsaros
# @Date:   2014-12-01 14:54:37
# @Email:  patcherwork@gmail.com
# @Last Modified by:   Dimitrios Katsaros
# @Last Modified time: 2016-11-30 13:35:03

from __future__ import print_function
import v4l2, fcntl, errno, logging, ctypes, sys, errno, os

from copy import copy
from numbers import Number

LOGGING_LEVEL_FINE_GRAINED_DEBUG = 5
logging.FINE_GRAINED_DEBUG = LOGGING_LEVEL_FINE_GRAINED_DEBUG
DEVICE_WRAPPER_NAME = "v4l2wrapper"

_v4l2_ctrl_id_to_name_map = {
    v4l2.V4L2_CTRL_TYPE_INTEGER: "Integer",
    v4l2.V4L2_CTRL_TYPE_BOOLEAN: "Boolean",
    v4l2.V4L2_CTRL_TYPE_MENU: "Menu",
    v4l2.V4L2_CTRL_TYPE_BUTTON: "Button",
    v4l2.V4L2_CTRL_TYPE_INTEGER64: "Integer64",
    v4l2.V4L2_CTRL_TYPE_CTRL_CLASS: "Control Class",
    v4l2.V4L2_CTRL_TYPE_STRING: "String",
    v4l2.V4L2_CTRL_TYPE_BITMASK: "Bitmask",
    v4l2.V4L2_CTRL_TYPE_INTEGER_MENU: "Integer Menu",
    v4l2.V4L2_CTRL_TYPE_U8: "U8 Array",
    v4l2.V4L2_CTRL_TYPE_U16: "U16 Array",
    v4l2.V4L2_CTRL_TYPE_U32: "U32 Array"
}


class DeviceError(Exception):
    def __init__(self, value):
        self.parameter = value
    def __str__(self):
        return repr(self.parameter)

class ExtCtrlError(Exception):
    def __init__(self,value):
        self.parameter = value
    def __str__(self):
        return repr(self.parameter)

class v4l2DeviceBase(object):
    '''
    Base class for all device objects
    provides core functionality
    '''

    def __init__(self, tupl):
        (device_path, formt, capabilities, kwargs) = tupl
        self.fd = None
        self.controls = None
        self._device_path = device_path
        self.init_format = formt
        self.format = formt
        self.capabilities = capabilities
        self._strmoff_force_fd_reset = False

        if kwargs and "loggerparent" in kwargs:
            self.logger = kwargs["loggerparent"].getChild(DEVICE_WRAPPER_NAME)
        else:
            self.logger = logging.getLogger(DEVICE_WRAPPER_NAME)

        if kwargs and "logging_level" in kwargs:
            self.logger.setLevel(kwargs["logging_level"])
        else:
            self.logger.setLevel(logging.INFO)
        self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Key word arguments passed to base: {}'.format(str(kwargs)))

        if kwargs and "v4l2_presets" in kwargs and isinstance(kwargs["v4l2_presets"], dict):
            self.v4l2_presets = kwargs["v4l2_presets"]
        else:
            self.v4l2_presets = {}

        if kwargs and "cleanup" in kwargs and isinstance(kwargs["cleanup"], bool):
            self._perform_cleanup = kwargs["cleanup"]
        else:
            self._perform_cleanup = True

        if kwargs and "reset" in kwargs and isinstance(kwargs["reset"], bool):
            self._do_reset = kwargs["reset"]
        else:
            self._do_reset = False
        #list of chain of classes comprising the wrapper, used for debug
        self.device_wrapper_list = []

        #set image size to a very large number, the driver will
        #default to the closest values acceptable
        fmt = self.get_fmt()
        fmt.fmt.pix.width = 10*1024
        fmt.fmt.pix.height = 10*1024
        self.defaultformat = fmt

        #used to reset device from possible previous states
        self._perform_reset = False
        self._try_reset(kwargs)
        self.device_wrapper_list.append('Base')

    def __del__(self):
        if self._perform_cleanup:
            self.cleanup()
        self.close_fd()

    def _try_reset(self, kwargs):
        try:
            if self._do_reset:
                self._perform_reset = True
                self.reset_fmt()
                self.reset_controls()
            return self._perform_reset
        except Exception as e:
            self.logger.info ("Unable to reset format on wrapper initialization, disabling reset")
            self.logger.debug ("Error: {}".format(e))
            self._perform_reset = False
            return False
        return True


    def cleanup(self):
        try:
            if self._perform_reset:
                self.reset_fmt(strmoff=True)
                self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Resetting controls...')
                self.reset_controls()
        except Exception as e:
            self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Base: In cleanup: {}'.format(str(e)))
        finally:
            try:
                self.close_fd()
            except:
                pass
            self.logger.log(LOGGING_LEVEL_FINE_GRAINED_DEBUG, 'Base wrapper cleanup completed')


    def controls_iterator(self):
        '''
        iterator that can be used in 'for' loop to
        iterate device controls
        '''
        queryctrl = v4l2.v4l2_query_ext_ctrl(id=0)
        while True:
            queryctrl.id |= v4l2.V4L2_CTRL_FLAG_NEXT_CTRL | v4l2.V4L2_CTRL_FLAG_NEXT_COMPOUND
            try:
                self._set_ioctl(v4l2.VIDIOC_QUERY_EXT_CTRL, queryctrl)
            except IOError as e:
                # no more custom controls available on this device
                assert e.errno == errno.EINVAL
                raise StopIteration
            yield copy(queryctrl)

    def list_controls(self):
        '''
        lists available controls
        '''
        if self.controls:
            return self.controls
        controls = []
        for queryctrl in self.controls_iterator():
            controls.append(copy(queryctrl))
        self.controls = controls
        return controls

    def find_ctrl(self, name):
        listctrls = self.list_controls()
        for ctrl in listctrls:
            if ctrl.name.decode('UTF-8') == name:
                return ctrl
        return None

    def query_ctrl(self, ctrlid):
        control = v4l2.v4l2_queryctrl(id=ctrlid)
        ret = self._set_ioctl(v4l2.VIDIOC_QUERYCTRL, control)
        if ret < 0:
            return None
        return control

    def get_ctrl(self, ctrlid):
        control = v4l2.v4l2_control(id=ctrlid)
        self._set_ioctl(v4l2.VIDIOC_G_CTRL, control)
        return control.value

    def set_ctrl(self, ctrl, val, strmoff=False):
        if strmoff is True:
           self._stream_ioctl_off()
        control = v4l2.v4l2_control(id=ctrl, value=ctypes.c_int32(val))
        return self._set_ioctl(v4l2.VIDIOC_S_CTRL, control)

    def get_ctrl_id(self, name):
        ctrl = self.find_ctrl(name)
        if ctrl is None:
            return None
        return ctrl.id

    def ctrl_is_readable(self, ctrl):
        if isinstance(ctrl, Number):
            ctrl = self.query_ctrl(ctrl)
        if (ctrl.type == v4l2.V4L2_CTRL_TYPE_CTRL_CLASS or
            ctrl.flags&v4l2.V4L2_CTRL_FLAG_DISABLED or
            ctrl.flags&v4l2.V4L2_CTRL_FLAG_INACTIVE or
            ctrl.flags&v4l2.V4L2_CTRL_FLAG_WRITE_ONLY):
            return False
        return True

    def ctrl_is_writable(self, ctrl):

        if isinstance(ctrl, Number):
            ctrl = self.query_ctrl(ctrl)
        if (ctrl.type == v4l2.V4L2_CTRL_TYPE_CTRL_CLASS or
            ctrl.flags&v4l2.V4L2_CTRL_FLAG_DISABLED or
            ctrl.flags&v4l2.V4L2_CTRL_FLAG_INACTIVE or
            ctrl.flags&v4l2.V4L2_CTRL_FLAG_READ_ONLY):
            #could also add volatile, since writing it has no effect
            return False
        return True

    def reset_controls(self):
        '''
        performs a full device control reset
        '''
        self._stream_ioctl_off()
        for ctrl in self.controls_iterator():
            if not self.ctrl_is_writable(ctrl):
                continue
            elif ctrl.flags&v4l2.V4L2_CTRL_FLAG_HAS_PAYLOAD:
                if ctrl.type == v4l2.V4L2_CTRL_TYPE_STRING:
                    continue
                qex = self.query_ext_ctrl(ctrl.id)
                exctrl = self.get_ext_ctrl(ctrl.id)
                if qex.type < v4l2.V4L2_CTRL_COMPOUND_TYPES:
                    for i in range(qex.elems):
                        if qex.elem_size == 4:
                            exctrl.controls[0].p_u32[i] = qex.default_value
                        elif qex.elem_size == 2:
                            exctrl.controls[0].p_16[i] = qex.default_value
                        elif qex.elem_size == 1:
                            exctrl.controls[0].p_8[i] = qex.default_value
                        else:
                            ControlError('Cannot reset control with byte size {}'.format(self.elem_size))
                    self.set_ext_ctrl(exctrl)
                    continue
                else:
                    #compound control reset goes here
                    continue
            elif (ctrl.type == v4l2.V4L2_CTRL_TYPE_BUTTON or
                 ctrl.type == v4l2.V4L2_CTRL_TYPE_CTRL_CLASS):
                continue
            #self.logger.debug('Resetting control: {}'.format(ctrl.name))
            if self.v4l2_presets and ctrl.name.decode('UTF-8') in self.v4l2_presets:
                self.set_ctrl(ctrl.id, self.v4l2_presets[ctrl.name.decode('UTF-8')])
            else:
                self.set_ctrl(ctrl.id, ctrl.default_value)

    def menu_iterator(self, queryctrl):
        '''
        Iterator that can be used in for loop for iterating over
        device query menu
        '''
        menu = v4l2.v4l2_querymenu(id=queryctrl.id)
        menu.index = queryctrl.minimum
        while menu.index <= queryctrl.maximum:
            try:
                ret = self._set_ioctl(v4l2.VIDIOC_QUERYMENU, menu)
            except IOError as e:
                # no more custom controls available on this device
                assert e.errno == errno.EINVAL
                menu.index += 1
                continue
            yield copy(menu)
            menu.index += 1

    def format_iterator(self):
        '''
        Iterator that can be used in for loop for iterating over
        device formats
        '''
        fmtdesc = v4l2.v4l2_fmtdesc()
        fmtdesc.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
        while True:
            try:
                ret = self._set_ioctl(v4l2.VIDIOC_ENUM_FMT, fmtdesc)
            except IOError as e:
                assert e.errno == errno.EINVAL
                raise StopIteration
            yield copy(fmtdesc)
            fmtdesc.index += 1

    def list_formats(self):
        formats = []
        for fmtdesc in self.format_iterator():
            formats.append(fmtdesc)
        return formats

    def get_fmt(self):
        fmt = v4l2.v4l2_format(type=v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE)
        self._set_ioctl(v4l2.VIDIOC_G_FMT, fmt)
        return fmt

    def set_fmt(self, fmt, strmoff=False):
        '''
        sets the format,
        if strmoff is True, the stream ioctl is turned off
        '''
        if strmoff is True:
            self._stream_ioctl_off()
        self._set_ioctl(v4l2.VIDIOC_S_FMT, fmt)
        return fmt

    def try_fmt(self, fmt, strmoff=False):
        if strmoff is True:
            self._stream_ioctl_off()
        self._set_ioctl(v4l2.VIDIOC_TRY_FMT, fmt)
        return fmt

    def reset_fmt(self, strmoff=False):
        '''
        resets to default format, which is the format that the device was using when the wrapper started
        setting strmoff to True disables the stream beforehand
        '''
        if strmoff == True:
            self._stream_ioctl_off()
        return self._set_ioctl(v4l2.VIDIOC_S_FMT, self.defaultformat)

    def set_fmt_size(self, width=None, height=None):
        fmt = self.get_fmt()
        if width:
            fmt.fmt.pix.width = width
        if height:
            fmt.fmt.pix.height = height
        return self.set_fmt(fmt, True)

    def get_fmt_size(self):
        fmt = self.get_fmt()
        return (fmt.fmt.pix.width,fmt.fmt.pix.height)

    def apply_format(self,width=None,height=None,pixelformat=None):
        """
        Helper function for applying a new format.
        named arguments:
        width: sets the width
        height: sets the width
        pixelformat: sets the format from the v4l2device
        if no argumets are set, this is a noop
        """

        if not width and not height and not pixelformat:
            return 0
        fmt = self.get_fmt()
        if width:
            fmt.fmt.pix.width = width
        if height:
            fmt.fmt.pix.height = height
        if pixelformat:
            fmt.fmt.pix.pixelformat = pixelformat
        return self.set_fmt(fmt, True)

    def get_capability(self):
        cp = v4l2.v4l2_capability()
        self._set_ioctl(v4l2.VIDIOC_QUERYCAP, cp)
        return cp

    def get_priority(self):
        integer = v4l2.c_int(0)
        self._set_ioctl(v4l2.VIDIOC_G_PRIORITY, integer)
        return integer

    def set_priority(self, val):
        if val<0 or val>3:
            return False
        integer = v4l2.c_int(val)
        self._set_ioctl(v4l2.VIDIOC_G_PRIORITY, integer)
        return True

    def open_fd(self, flags=os.O_RDWR):
        if self.fd:
            self.close_fd()
        self.fd = os.open(self._device_path, flags)

    def close_fd(self):
        if self.fd:
            try:
                os.close(self.fd)
            except:
                self.logger.warning('Failed to close fd with id {}'.format(self.fd))
        self.fd = None

    def _set_ioctl(self, op_code, val):
        """Sets an ioctl. If the wrapper has an open fd, we use that"""
        """Otherwise open a device for handling"""
        if self.fd:
            res = fcntl.ioctl(self.fd, op_code, val)
        else:
            fdint = None
            try:
                fdint = os.open(self._device_path, os.O_RDWR)
                res = fcntl.ioctl(fdint, op_code, val)
            finally:
                if fdint:
                    os.close(fdint)
        if (res != 0):
            enum = ctypes.get_errno()
            raise DeviceError("Failed to set ioctl '{}', error message, '{}: {}'".format(
                str (op_code), errno.errorcode[enum], os.strerror(enum)))
        return res

    def _stream_ioctl_off(self):
        '''
        used to disable streaming if enabled beforehand

        NOTE: Will close and open fd instead of STRMOFF if
        '_strmoff_force_fd_reset' is set to True
        '''

        if self._strmoff_force_fd_reset:
            try:
                self.close_fd()
            except:
                pass
            finally:
                self.open_fd()
                self._strmoff_force_fd_reset = False
        else:
            try:
                self._set_ioctl(v4l2.VIDIOC_STREAMOFF, ctypes.c_int(v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE))
            except IOError:
                pass
        return

    def print_device_info(self, outp=sys.stdout):
        '''
        prints device info
        the outp keyvalue can be set to use other output than stdout
        '''
        cp = self.capabilities
        print ('Device name:', cp.card, file=outp)
        print ('Driver name:', cp.driver, file=outp)
        print ('Driver version number:', '{}.{}.{}'.format((cp.version >> 16 & 0xFF),
                                                                  (cp.version >> 8  & 0xFF),
                                                                  (cp.version >> 0  & 0xFF)), file=outp)
        print ('Bus info:', cp.bus_info, file=outp)
        print ('Controls:', [x.name.decode('UTF-8') for x in self.list_controls()], file=outp)
        print ('Formats:', [x.description.decode('UTF-8') for x in self.list_formats()], file=outp)
        print ('Wrapper Components:', self.device_wrapper_list, file=outp)

    def _v4l2_ctrl_id_to_name(self, ctrlid):
        return _v4l2_ctrl_id_to_name_map.get(ctrlid, "Unknown")

    def pprint_ctrls(self, outp=sys.stdout):
        print (file=outp)
        for queryctrl in self.controls_iterator():
            if queryctrl.flags & v4l2.V4L2_CTRL_FLAG_DISABLED:
                continue
            elif queryctrl.type == v4l2.V4L2_CTRL_TYPE_CTRL_CLASS:
                print ('======= {}, class id: {} ======='.format(queryctrl.name.decode('UTF-8'),
                    v4l2.V4L2_CTRL_ID2CLASS(queryctrl.id)), file=outp)
            elif queryctrl.type == v4l2.V4L2_CTRL_TYPE_MENU or queryctrl.type == v4l2.V4L2_CTRL_TYPE_INTEGER_MENU:
                print ('******* menu control: {} *******'.format(queryctrl.name.decode('UTF-8')), file=outp)
                print ('type:', queryctrl.type, '({})'.format(
                    self._v4l2_ctrl_id_to_name(queryctrl.type)), file=outp)
                print ('id:', queryctrl.id, file=outp)
                print ('default value:', queryctrl.default_value, file=outp)
                print ('min val: {}, max val: {}'.format(queryctrl.minimum, queryctrl.maximum), file=outp)
                print ('menu items:', file=outp)
                for item in self.menu_iterator(queryctrl):
                    print ('-'*16, file=outp)
                    if queryctrl.type == v4l2.V4L2_CTRL_TYPE_MENU:
                        print (item.name.decode('UTF-8'), file=outp)
                    elif queryctrl.type == v4l2.V4L2_CTRL_TYPE_INTEGER_MENU:
                        print (item.value, file=outp)
                    print ('id', item.id, file=outp)
                    print ('index', item.index, file=outp)
                print ('-'*16, file=outp)
                print (file=outp)
            else:
                print ('control:', queryctrl.name.decode('UTF-8'), file=outp)
                print ('type:', queryctrl.type, '({})'.format(
                    self._v4l2_ctrl_id_to_name(queryctrl.type)), file=outp)
                print ('id:', queryctrl.id, file=outp)
                print ('default value:', queryctrl.default_value,file=outp)
                print ('min val: {}, max val: {}'.format(queryctrl.minimum, queryctrl.maximum), file=outp)
            print (file=outp)


    # extended controls

    def query_ext_ctrl(self, ctrlid):
        control = v4l2.v4l2_query_ext_ctrl(id=ctrlid)
        ret = self._set_ioctl(v4l2.VIDIOC_QUERY_EXT_CTRL, control)
        if ret < 0:
            return None
        return control

    def get_ext_ctrl(self, inp, control_class=0):
        if isinstance(inp, Number):
            qry = self.query_ext_ctrl(inp)
        elif isinstance(inp, v4l2.v4l2_queryctrl):
            qry = self.query_ext_ctrl(inp.id)
        elif isinstance(inp, v4l2.v4l2_query_ext_ctrl):
            #recall the function to make sure all data is set correctly
            qry = self.query_ext_ctrl(inp.id)
        else:
            raise DeviceError('get_ext_ctrl: Cannot handle input of type {}'.format(type(inp)))
        array = (v4l2.v4l2_ext_control*(1))()
        ctrls = v4l2.v4l2_ext_controls(ctrl_class=control_class, count=1, controls=array)
        array[0].id = qry.id
        if qry.type == v4l2.V4L2_CTRL_TYPE_STRING:
            array[0].size = qry.elem_size
            array[0].string = (' ' * (array[0].size-1) +'\0').encode("UTF-8")
        elif (qry.flags == v4l2.V4L2_CTRL_FLAG_HAS_PAYLOAD):
            if qry.type < v4l2.V4L2_CTRL_COMPOUND_TYPES:
                array[0].size = qry.elems * qry.elem_size
                buf = (ctypes.c_char * array[0].size)()
                array[0].ptr = ctypes.cast(buf, ctypes.c_void_p)
            else:
                _handle_compond_ctrls(qry, array[0])
        else:
            pass
        self._set_ioctl(v4l2.VIDIOC_G_EXT_CTRLS, ctrls)
        return ctrls

    def try_ext_ctrl(self, ctrls, control_class=0, strmoff=False):
        '''tries a set of controls using the extended api'''
        array_type = v4l2.v4l2_ext_control
        ptr_type = ctypes.POINTER(array_type)
        ctrls_type = v4l2.v4l2_ext_controls
        if isinstance(ctrls, ctrls_type):
            controls = ctrls
        elif isinstance(ctrls, ptr_type) or isinstance(ctrls, array_type):
            controls = v4l2.v4l2_ext_controls(ctrl_class=control_class, count=ctrls._length_, controls=ctrls)
        else:
            raise DeviceError('control array passed is not of type {} or {}'.format(array_type, ptr_type))
        if strmoff is True:
           self._stream_ioctl_off()
        return self._set_ioctl(v4l2.VIDIOC_S_EXT_CTRLS, controls)

    def set_ext_ctrl(self, ctrls, control_class=0, strmoff=False):
        '''sets controls using the extended api'''
        array_type = v4l2.v4l2_ext_control
        ptr_type = ctypes.POINTER(array_type)
        ctrls_type = v4l2.v4l2_ext_controls
        if isinstance(ctrls, ctrls_type):
            controls = ctrls
        elif isinstance(ctrls, ptr_type) or isinstance(ctrls, array_type):
            controls = v4l2.v4l2_ext_controls(ctrl_class=control_class, count=ctrls._length_, controls=ctrls)
        else:
            raise DeviceError('control array passed is not of type {} or {}'.format(array_type, ptr_type))
        if strmoff is True:
           self._stream_ioctl_off()
        return self._set_ioctl(v4l2.VIDIOC_S_EXT_CTRLS, controls)

    def control_class_iterator(self, ctrl_class):
        '''
        iterator that can be used in 'for' loop to
        iterate device controls of a specific control class
        '''
        ctrl_class = v4l2.V4L2_CTRL_ID2CLASS(ctrl_class)
        queryctrl = v4l2.v4l2_queryctrl(id=ctrl_class)
        while True:
            queryctrl.id |= v4l2.V4L2_CTRL_FLAG_NEXT_CTRL
            try:
                self._set_ioctl(v4l2.VIDIOC_QUERYCTRL, queryctrl)
            except IOError as e:
                # no more custom controls available on this device
                assert e.errno == errno.EINVAL
                raise StopIteration

            if v4l2.V4L2_CTRL_ID2CLASS(queryctrl.id) != ctrl_class:
                raise StopIteration

            yield copy(queryctrl)

    def get_ext_class_ctrls(self, ctrl_class, strmoff=False):
        ''' returns a v4l2_ext_controls with the control information for the entire control class'''
        ''' use the id of any control in the target control class, it will default to the control class '''

        if strmoff is True:
           self._stream_ioctl_off()

        ctrl_class = v4l2.V4L2_CTRL_ID2CLASS(ctrl_class)

        ctrl_size = 0
        ctrl_list = []
        for ctrl in self.control_class_iterator(ctrl_class):
            if (ctrl.type == v4l2.V4L2_CTRL_TYPE_CTRL_CLASS or
                ctrl.flags & v4l2.V4L2_CTRL_FLAG_DISABLED or
                ctrl.flags & v4l2.V4L2_CTRL_FLAG_INACTIVE or
                ctrl.flags & v4l2.V4L2_CTRL_FLAG_WRITE_ONLY):
                continue
            ctrl_list.append(ctrl)
            ctrl_size +=1

        array = (v4l2.v4l2_ext_control*(ctrl_size))()
        for i in range(ctrl_size):
            array[i].id = ctrl_list[i].id

        controls = v4l2.v4l2_ext_controls(ctrl_class=ctrl_class, count=ctrl_size, controls=array)
        try:
            self._set_ioctl(v4l2.VIDIOC_G_EXT_CTRLS, controls)
        except IOError as e:
            passed_check = False
            #if this exception is return it means there is a pointer that was not allocated
            #we iterate through the controls trying to fix missing pointers one by one.
            #If all pointers are allocated, the ioctl will work and we can return the values.
            #The ioctl throws and exception for every missing pointer so we have to check them
            #one by one
            if e.errno == errno.ENOSPC:
                for i in range(ctrl_size):
                    if array[i].size != 0:
                        if ctrl_list[i].type == v4l2.V4L2_CTRL_TYPE_STRING :
                            array[i].string = ctypes.addressof(ctypes.create_string_buffer(array[i].size))
                        #if pointers are implemented, additional cases have to go here
                        else:
                            raise ExtCtrlError('get_ext_class_ctrls: Unhandled control of type: {}'.format(ctrl_list[i].type))
                        try:
                            self._set_ioctl(v4l2.VIDIOC_G_EXT_CTRLS, controls)
                            passed_check = True
                        except IOError as e2:
                            if not e2.errno == errno.ENOSPC:
                                raise
                        #if the ioctl works it has populated all controls and we can return
                        if passed_check:
                            return controls

            if not passed_check:
                raise
        return controls

def _handle_compound_ctrls(qry, ext_ctrl):
    '''Internal handle for compound controls,
       this gets expanded as new controls are added
       If it starts getting large it may be moved to a
       new file'''
    if qry.type == v4l2.V4L2_CTRL_TYPE_POINT:
        ext_ctrl.p_point = v4l2.v4l2_point()
    else:
        DeviceError('Unhandled compound type with id {}'
            'for control {}'.format(qry.type, qry.name))