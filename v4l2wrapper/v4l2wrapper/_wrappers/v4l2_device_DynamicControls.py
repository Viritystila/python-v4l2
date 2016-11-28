'''
    Dynamic controls

    An extension of v4l2DeviceBase aimed to automate
    the creation and handling of all underlaying
    device controls (might also handle other parts of v4l)

'''

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Dimitrios Katsaros
# @Date:   2014-12-01 14:54:37
# @Email:  patcherwork@gmail.com
# @Last Modified by:   Dimitrios Katsaros
# @Last Modified time: 2016-11-30 13:36:41

import v4l2
import ctypes
from v4l2wrapper._wrappers.v4l2_device_Base import (
    v4l2DeviceBase, LOGGING_LEVEL_FINE_GRAINED_DEBUG)
import re
import keyword, weakref

_mdata = {
    'GET_CTRL_PREFEX':'get_ctrl_',
    'SET_CTRL_PREFEX':'set_ctrl_',
    'TURN_ON_PREFEX':'turn_on_ctrl_',
    'TURN_OFF_PREFEX':'turn_off_ctrl_',
    'SWITCH_PREFEX':'switch_ctrl_',
    'SELECT_PREFEX':'select_',
    'FIRE_PREFEX':'activate_',
    'ARRAY_PREFEX':'array_ctrl_',
    'POINT_PREFEX':'point_ctrl_',
}

# converts device names into correct format for fuction names
clean = lambda varStr: re.sub('\W|^(?=\d)','_', varStr).lower()

class ControlError(Exception):
    def __init__(self, value):
        self.parameter = value
    def __str__(self):
        return repr(self.parameter)

class BaseControl(object):
    '''
    A class reprisenting one custom control
    Contains all required information for correct
    handling
    '''
    def __init__(self, queryctrl, wref):
        self.wref = wref
        self.id = queryctrl.id
        self.type = queryctrl.type
        self.name = queryctrl.name.decode('UTF-8')
        self.minimum = queryctrl.minimum
        self.maximum = queryctrl.maximum
        self.step = queryctrl.step
        self.default = queryctrl.default_value
        self.flags = queryctrl.flags

    def set_to_default(self):
        if (  self.flags & v4l2.V4L2_CTRL_FLAG_DISABLED or
              self.flags & v4l2.V4L2_CTRL_FLAG_INACTIVE or
              self.flags & v4l2.V4L2_CTRL_FLAG_READ_ONLY):
            return
        dev = self.wref()
        if dev:
            dev.set_ctrl(self.id, self.default, strmoff=True)

class BooleanControl(BaseControl):

    def __init__(self, queryctrl, wref):
        super(BooleanControl, self).__init__(queryctrl, wref)
        self.val = 0
        dev = self.wref()
        if dev:
            self.val = dev.get_ctrl(self.id)

    def turn_on(self):
        if self.flags & v4l2.V4L2_CTRL_FLAG_READ_ONLY:
            raise ControlError('Attempted to turn on read only control {}'.format(self.name))
        dev = self.wref()
        if dev:
            dev.set_ctrl(self.id, 1, strmoff=True)
            self.val = 1

    def turn_off(self):
        if self.flags & v4l2.V4L2_CTRL_FLAG_READ_ONLY:
            raise ControlError('Attempted to turn off read only control {}'.format(self.name))
        dev = self.wref()
        if dev:
            dev.set_ctrl(self.id, 0, strmoff=True)
            self.val = 0

    def switch_val(self):
        dev = self.wref()
        if dev:
            dev.set_ctrl(self.id, not self.val, strmoff=True)

class ButtonControl(BaseControl):

    def __init__(self, queryctrl, dev):
        super(ButtonControl, self).__init__(queryctrl, dev)

    def press_button(self):
        dev = self.wref()
        if dev:
            dev.set_ctrl(self.id, 0, strmoff=True)

class MenuControl(BaseControl):

    def __init__(self, queryctrl, wref):
        super(MenuControl, self).__init__(queryctrl, wref)

        self.menuitems = []
        def runfunc(weakref, menuid, menukey):
            dev = weakref()
            if dev:
                dev.set_ctrl(menuid, menukey, strmoff=True)
        menufun = lambda wref, menuid, menukey: lambda: runfunc(wref, menuid, menukey)

        dev = wref()
        for item in dev.menu_iterator(queryctrl):
            mname = clean(item.name.decode('UTF-8'))
            self.menuitems.append((mname, menufun(wref, queryctrl.id, item.index)))

class IntegerMenuControl(BaseControl):

    def __init__(self, queryctrl, wref):
        super(IntegerMenuControl, self).__init__(queryctrl, wref)

        self.menuitems = []
        def runfunc(weakref, menuid, menukey):
            dev = weakref()
            if dev:
                dev.set_ctrl(menuid, menukey, strmoff=True)
        menufun = lambda wref, menuid, menukey: lambda: runfunc(wref, menuid, menukey)

        dev = wref()
        for item in dev.menu_iterator(queryctrl):
            mname = str(item.value)
            self.menuitems.append((mname, menufun(wref, queryctrl.id, item.index)))

class IntegerControl(BaseControl):

    def __init__(self, queryctrl, dev):
        super(IntegerControl, self).__init__(queryctrl, dev)

    def set_value(self, val):
        if not isinstance(val, int):
            '''
            decided to throw exception here since casting ints is more probable
            to cause overflows
            '''
            raise ControlError('Attempted to write non int value {}'
                            'to int control {}'.format(val, self.name))
        elif self.flags & v4l2.V4L2_CTRL_FLAG_READ_ONLY:
            raise ControlError('Attempted to write value {} to read only control {}'.format(
                                        val, self.name))
        elif val < self.minimum or val > self.maximum:
            raise ControlError('Value {} is not within the range [{}, {}] for control {}'.format(
                                        val, self.minimum, self.maximum, self.name))
        dev = self.wref()
        if dev:
            return dev.set_ctrl(self.id, val, strmoff=True)
        else:
            return 0

    def get_value(self):
        if self.flags & v4l2.V4L2_CTRL_FLAG_WRITE_ONLY:
            raise ControlError('Attempted to read value from write only control {}'.format(
                                        self.name))
        dev = self.wref()
        if dev:
            return dev.get_ctrl(self.id)
        return 0

class Integer64Control(BaseControl):

    def __init__(self, queryctrl, dev):
        super(Integer64Control, self).__init__(queryctrl, dev)

    def set_value(self, val):
        if self.flags & v4l2.V4L2_CTRL_FLAG_READ_ONLY:
            raise ControlError('Attempted to write value {} to read only control {}'.format(
                                        val, self.name))
        elif not isinstance(val, ctypes.c_int64):
            self.logger.warning('Attempted to write value {}'
                            'to int64 control {}, will cast to int64'.format(
                                        val, self.name))
            val = ctypes.c_int64(val)
        dev = self.wref()
        if dev:
            return dev.set_ctrl(self.id, val, strmoff=True)
        return 0

    def get_value(self):
        if self.flags & v4l2.V4L2_CTRL_FLAG_WRITE_ONLY:
            raise ControlError('Attempted to read value from write only control {}'.format(
                                        self.name))
        dev = self.wref()
        if dev:
            return dev.get_ctrl(self.id)
        return 0

#### EXTENDED CONTROLS ####

class BaseExtCtrl(object):
    '''
    A class reprisenting one custom extended control
    Contains all required information for correct
    handling
    '''
    def __init__(self, queryctrl, wref):
        self.wref = wref
        self.id = queryctrl.id
        self.type = queryctrl.type
        self.name = queryctrl.name.decode('UTF-8')
        self.minimum = queryctrl.minimum
        self.maximum = queryctrl.maximum
        self.step = queryctrl.step
        self.default = queryctrl.default_value
        self.flags = queryctrl.flags
        self.elem_size = queryctrl.elem_size
        self.elems = queryctrl.elems
        self.nr_of_dims = queryctrl.nr_of_dims
        self.dims = queryctrl.dims

    def set_to_default(self):
        if (  self.flags & v4l2.V4L2_CTRL_FLAG_DISABLED or
              self.flags & v4l2.V4L2_CTRL_FLAG_INACTIVE or
              self.flags & v4l2.V4L2_CTRL_FLAG_READ_ONLY or
              self.type == v4l2.V4L2_CTRL_TYPE_STRING):
            return
        dev = self.wref()
        if not dev:
            return

        ctrl = dev.get_ext_ctrl(self.id)

        if self.type < v4l2.V4L2_CTRL_COMPOUND_TYPES:
            for i in xrange(self.elems):
                try:
                    _write_to_array_pos(ctrl.controls[0], i, self.elem_size, self.default)
                except ControlError:
                    ControlError('Cannot reset control with byte size {}'.format(self.elem_size))
            dev.set_ext_ctrl(ctrl)
        else:
            #compound resets should go here
            pass

class ArrayControl(BaseExtCtrl):
    def __init__(self, queryctrl, wref):
        super(ArrayControl, self).__init__(queryctrl, wref)

    def __len__(self):
        return self.elems

    def __setitem__(self, index, value):

        dev = self.wref()
        if not dev:
            return
        if isinstance(index, tuple):
            raise ControlError('multi-dimentional indexing not supported')
        elif value < self.minimum or value > self.maximum:
            raise ControlError('Value {} is not within the range [{}, {}] for control {}'.format(
                                        value, self.minimum, self.maximum, self.name))
        elif isinstance(index, int):
            if index < 0 or index >= self.elems:
                raise ControlError('Index {} is not within the range [{}, {}] for control {}'.format(
                                        index, 0, self.elems, self.name))

        ctrl = dev.get_ext_ctrl(self.id)
        if ctrl.error_idx != 0:
            raise ControlError('Exception raised from get control {}, error code {}'.format(
                                        self.name, ctrl.error_idx))

        if isinstance(index, slice):
            if index.start == None and index.stop == None and index.step == None:
                for i in xrange(self.elems):
                    _write_to_array_pos(ctrl.controls[0], i, self.elem_size, value)
            else:
                raise ControlError('Index slicing not yet supported for Array Controls')
        else:
            _write_to_array_pos(ctrl.controls[0], index, self.elem_size, value)

        dev.set_ext_ctrl(ctrl)

    def __getitem__(self, index):

        if isinstance(index, slice):
            raise ControlError('Index slicing not yet supported for Array Controls')
        elif isinstance(index, tuple):
            raise ControlError('multi-dimentional indexing not supported')
        elif not isinstance(index, int):
            raise ControlError('Non integer indexing not supported')
        elif index < 0 or index >= self.elems:
            raise ControlError('Index {} is not within the range [{}, {}] for control {}'.format(
                                        index, 0, self.elems, self.name))
        dev = self.wref()
        if not dev:
            return 0
        ctrl = dev.get_ext_ctrl(self.id)
        if ctrl.error_idx != 0:
            raise ControlError('Exception raised from get control {}, error code {}'.format(
                                        self.name, ctrl.error_idx))

        return _get_from_array_pos(ctrl.controls[0], index, self.elem_size)


    def get_value(self):
        dev = self.wref()
        if not dev:
            return
        if not dev.ctrl_is_readable(self.id):
            raise ControlError('Attempted to read value from write only control {}'.format(
                                        self.name))
        ctrl = dev.get_ext_ctrl(self.id)
        if ctrl.error_idx != 0:
            raise ControlError('Exception raised from get control {}, error code {}'.format(
                                        self.name, ctrl.error_idx))
        return ctrl.controls[0]

#helper functions for array types

def _write_to_array_pos(array, index, elem_size, value):
    if elem_size == 4:
        array.p_u32[index] = value
    elif elem_size == 2:
        array.p_16[index] = value
    elif elem_size == 1:
        array.p_8[index] = value
    else:
        ControlError('Cannot handle control with byte size {}'.format(self.elem_size))

def _get_from_array_pos(array, index, elem_size):
    if elem_size == 4:
        return array.p_u32[index]
    elif elem_size == 2:
        return array.p_16[index]
    elif elem_size == 1:
        return array.p_8[index]
    else:
        ControlError('Cannot handle control with byte size {}'.format(self.elem_size))


class StringControl(BaseExtCtrl):

    def __init__(self, queryctrl, wref):
        super(StringControl, self).__init__(queryctrl, wref)

    def set_value(self, val):
        dev = self.wref()
        if not dev:
            return
        if self.flags & v4l2.V4L2_CTRL_FLAG_READ_ONLY:
            raise ControlError('Attempted to write value {} to read only control {}'.format(
                                        val, self.name))
        elif len(val) < self.minimum or len(val) > self.maximum:
            raise ControlError('Value {} is not within the range [{}, {}] for control {}'.format(
                                        val, self.minimum, self.maximum, self.name))
        elif not isinstance(val, basestring):
            self.logger.warning('Attempted to write non string value {}'
                            'to string control {}, will cast to string'.format(
                                        val, self.name))
            val = str(val)
        ctrl = dev.get_ext_ctrl(self.id)
        if val[-1]!='\0':
            val = val + '\0'
        if len(val) > self.elem_size:
            val = val[:-(val-self.elem_size+1)]
            val = val + '\0'

        ctrl.controls[0].string = val
        return dev.set_ext_ctrl(ctrl)

    def get_value(self):
        dev = self.wref()
        if not dev:
            return
        if self.flags & v4l2.V4L2_CTRL_FLAG_WRITE_ONLY:
            raise ControlError('Attempted to read value from write only control {}'.format(
                                        self.name))
        return dev.get_ext_ctrl(self.id).controls[0].string


# base for compound controls
class CompoundCtrl(BaseExtCtrl):
    def __init__(self, queryctrl, wref):
        super(CompoundCtrl, self).__init__(queryctrl, wref)

# compound controls get added here

class PointControl(BaseExtCtrl):
    def __init__(self, queryctrl, wref):
        super(PointControl, self).__init__(queryctrl, wref)

    def get_value(self):
        dev = self.wref()
        if not dev:
            return
        return dev.get_value(self.id).controls[0]

    #point controls are not intended to be set
    #def set_value(self):

class v4l2DeviceDynamicControls(v4l2DeviceBase):
    '''
    An extension of the v4l2DeviceBase class, aimed to dynamicly
    create and provide an interface for the v4l2 controls, automating
    all handling of controls.
    '''
    def __init__(self, tup):
        super(v4l2DeviceDynamicControls, self).__init__(tup)
        self._controls = {}
        for ctrl in self.controls_iterator():

            if ( ctrl.flags & v4l2.V4L2_CTRL_FLAG_DISABLED or
                 ctrl.type == v4l2.V4L2_CTRL_TYPE_CTRL_CLASS ):
                self.logger.debug('Control \'{}\' either disabled or '
                              'control class, continuing'.format(ctrl.name.decode('UTF-8')))
                continue

            formname = clean(ctrl.name.decode('UTF-8'))
            if keyword.iskeyword(formname):
                raise ControlError('Formatted device name is a keyword: {}'.format(formname))
            if (ctrl.flags & v4l2.V4L2_CTRL_FLAG_HAS_PAYLOAD):
                qex = self.query_ext_ctrl(ctrl.id)
                if ctrl.type == v4l2.V4L2_CTRL_TYPE_STRING:
                    cls = StringControl(qex, weakref.ref(self))
                    if ctrl.flags & v4l2.V4L2_CTRL_FLAG_WRITE_ONLY:
                        setattr(self, _mdata['SET_CTRL_PREFEX'] + formname, cls.set_value)
                    elif ctrl.flags & v4l2.V4L2_CTRL_FLAG_READ_ONLY:
                        setattr(self, _mdata['GET_CTRL_PREFEX'] + formname, cls.get_value)
                    else:
                        setattr(self, _mdata['SET_CTRL_PREFEX'] + formname, cls.set_value)
                        setattr(self, _mdata['GET_CTRL_PREFEX'] + formname, cls.get_value)
                elif qex.type >= v4l2.V4L2_CTRL_COMPOUND_TYPES:
                    if qex.type == v4l2.V4L2_CTRL_TYPE_POINT:
                        cls = PointControl(qex, weakref.ref(self))
                        setattr(self, _mdata['POINT_PREFEX'] + formname, cls)
                    else:
                        #skip if control not implemented
                        continue
                #if not a compound then its an array
                else:
                    cls = ArrayControl(qex, weakref.ref(self))
                    setattr(self, _mdata['ARRAY_PREFEX'] + formname, cls)
            elif ctrl.type == v4l2.V4L2_CTRL_TYPE_INTEGER:
                cls = IntegerControl(ctrl, weakref.ref(self))
                if ctrl.flags & v4l2.V4L2_CTRL_FLAG_WRITE_ONLY:
                    setattr(self, _mdata['SET_CTRL_PREFEX'] + formname, cls.set_value)
                elif ctrl.flags & v4l2.V4L2_CTRL_FLAG_READ_ONLY:
                    setattr(self, _mdata['GET_CTRL_PREFEX'] + formname, cls.get_value)
                else:
                    setattr(self, _mdata['SET_CTRL_PREFEX'] + formname, cls.set_value)
                    setattr(self, _mdata['GET_CTRL_PREFEX'] + formname, cls.get_value)
            elif ctrl.type == v4l2.V4L2_CTRL_TYPE_BOOLEAN:
                cls = BooleanControl(ctrl, weakref.ref(self))
                if ctrl.flags & v4l2.V4L2_CTRL_FLAG_READ_ONLY:
                    pass
                else:
                    setattr(self, _mdata['TURN_ON_PREFEX'] + formname, cls.turn_on)
                    setattr(self, _mdata['TURN_OFF_PREFEX'] + formname, cls.turn_off)
                    setattr(self, _mdata['SWITCH_PREFEX'] + formname, cls.switch_val)
            elif ctrl.type == v4l2.V4L2_CTRL_TYPE_MENU:
                cls = MenuControl(ctrl, weakref.ref(self))
                for (itmname, func) in cls.menuitems:
                    setattr(self, _mdata['SELECT_PREFEX']+formname+'_'+itmname, func)
            elif ctrl.type == v4l2.V4L2_CTRL_TYPE_INTEGER_MENU:
                cls = IntegerMenuControl(ctrl, weakref.ref(self))
                for (itmname, func) in cls.menuitems:
                    setattr(self, _mdata['SELECT_PREFEX']+formname+'_'+itmname, func)
            elif ctrl.type == v4l2.V4L2_CTRL_TYPE_BUTTON:
                cls = ButtonControl(ctrl, weakref.ref(self))
                if ctrl.flags & v4l2.V4L2_CTRL_FLAG_READ_ONLY:
                    pass
                else:
                    setattr(self, _mdata['FIRE_PREFEX'] + formname, cls.press_button)
            elif ctrl.type == v4l2.V4L2_CTRL_TYPE_INTEGER64:
                cls = Integer64Control(ctrl, weakref.ref(self))
                if ctrl.flags & v4l2.V4L2_CTRL_FLAG_WRITE_ONLY:
                    setattr(self, _mdata['SET_CTRL_PREFEX'] + formname, cls.set_value)
                elif ctrl.flags & v4l2.V4L2_CTRL_FLAG_READ_ONLY:
                    setattr(self, _mdata['GET_CTRL_PREFEX'] + formname, cls.get_value)
                else:
                    setattr(self, _mdata['SET_CTRL_PREFEX'] + formname, cls.set_value)
                    setattr(self, _mdata['GET_CTRL_PREFEX'] + formname, cls.get_value)
            else:
                self.logger.debug('Unknown control type {}, continuing'.format(ctrl.type))
                continue
            self._controls[ctrl.name.decode('UTF-8').lower()] = cls
            self._controls[ctrl.id] = cls
        self.device_wrapper_list.append('Dynamic Controls')

    def cleanup(self):
        super(v4l2DeviceDynamicControls, self).cleanup()

    def find_dynamic_control(self, ident):
        '''perform search for dynamic control. Can be control id or string(case insensitive)'''
        try:
            if isinstance(ident, str):
                return self._controls[ident.lower()]
            elif isinstance(ident, int):
                return self._controls[ident]
            else:
                raise KeyError('Unable to find control with identifier of type {}'.format(type(ident)))
        except KeyError:
            raise KeyError('Unable to find dynamic control with key \'{}\''.format(str(ident)))
