#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Dimitrios Katsaros
# @Date:   2014-12-01 14:54:37
# @Email:  patcherwork@gmail.com
# @Last Modified by:   Dimitrios Katsaros
# @Last Modified time: 2016-11-30 13:31:57

import os, re
import logging
import v4l2
import fcntl
import copy
import itertools, types

#SETS BASIC CONFIG LEVEL
#FINE GRAINED DEBUG AT LOGGING LEVEL 5

logging.basicConfig(level=logging.INFO)
THROWING_EXEPT = False

class _mdata():
    '''structure for holding all module data'''
    device_file_identifier = 'v4l2_device_'
    device_class_idetifier = 'v4l2Device'
    device_subdir    = '/_wrappers'
    device_list = []
    ignoreList = ['v4l2_device_Base.py', 'v4l2_device_template.py']


class WrapperException(Exception):
    ''' Basic wrapper exception'''
    def __init__(self, value):
        self.parameter = value
    def __str__(self):
        return repr(self.parameter)

''' private methods '''

def _init_map():
    ''' initialize the device wrapper map'''
    path = os.path.dirname(os.path.abspath(__file__)) + _mdata.device_subdir
    if not os.path.isdir(path):
        logging.debug('Device directory not found: ' + path)
        return
    for f in os.listdir(path):
        if f.startswith(_mdata.device_file_identifier) and f.endswith('.py') and f not in _mdata.ignoreList:
            m = 'v4l2wrapper.{}.{}'.format(_mdata.device_subdir[1:], f[:-3])
            try:
                m = __import__(m, globals(), locals(), ['object'], 0)
            except Exception as e:
                if THROWING_EXEPT:
                    raise e
                else:
                    logging.debug('Exception from wrapper ' + str(m) + ' : ' + str(e))
                    continue
            for cls_name in [o for o in dir(m) if o.startswith(_mdata.device_class_idetifier)]:
                cls = getattr(m, cls_name)
                if cls not in _mdata.device_list:
                    _mdata.device_list.append(cls)

def _get_device_info(device_path, pixelformat = None):
    try:
        fd = os.open(device_path, os.O_RDWR)
    except IOError:
        raise WrapperException('ERROR: Unable to open {}'.format(device_path))

    cp  = _get_capability(fd)
    if cp is -1:
        os.close(fd)
        raise WrapperException('Device is not v4l compatible')

    fmt = _get_fmt(fd)
    if pixelformat:
        fmt.fmt.pix.pixelformat = pixelformat
        fcntl.ioctl(fd, v4l2.VIDIOC_S_FMT, fmt)
        fmt = _get_fmt(fd)
        if (fmt.fmt.pix.pixelformat != pixelformat):
            fd.close()
            raise WrapperException('ERROR: Unable to  set proper format' + device_path)
    os.close(fd)
    return fmt, cp

def _get_capability(fd):
    cp = v4l2.v4l2_capability()
    fcntl.ioctl(fd, v4l2.VIDIOC_QUERYCAP, cp)
    return cp

def _get_fmt(fd):
    fmt = v4l2.v4l2_format()
    fmt.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
    fcntl.ioctl(fd, v4l2.VIDIOC_G_FMT, fmt)
    return fmt

def _add_del_to_obj(obj, cls):
    def __del__(self):
        super(self._cls, self).__del__()
    obj._cls = cls
    obj.__del__ = types.MethodType(__del__, obj)

def _find_qtec_dev(devpath='/dev/', devpattern='video(\d+)'):
  files = os.listdir(devpath)
  if not devpath.endswith('/'):
    devpath += '/'
  pattern = '^' + devpath + devpattern + '$'
  ptrn = re.compile(pattern)
  ret = []
  for f in files:
    res = ptrn.match(devpath+f)
    if res:
      ret.append((res.group(0), int(res.group(1))))
  return ret

''' public methods'''
def create_device_wrapper(device_path=None, pixelformat=None, **kwargs):
    '''create device wrappers
    If a name is given it will try and find the wrapper with the device name.
    If that wrapper fails or is not amonst the options an exception is thrown.
    if no name is given a wrapper containing the most supported functionality is created

    There are also additional keywords that are reseverd by the base wrapper:
    - The 'cleanup' keyword can be used to disable cleanup on garbage collect
    by setting it to a False value. Cleanup only happens if 'reset' is True
    - The 'reset' keyword can be used to disable auto reset of controls during startup
    by setting it to a False value
    - The 'loggerparent' keyword is used to connect a python logger to the wrapper.
    The wrapper will make its logging a child of the passed logger
    - The 'logging_level' keyword is used to set the logging level of the wrapper logging
    - The 'v4l2_presets' is a dict containing control names as keys and default values of
    the controls to be set on every reset as values. Do not that the control names are
    CASE SENSITIVE!

    Additional keyword arguments can be defined. These key words are passed
    down to underlaying wrappers and are used for certain wrappers as additional parameters'''
    if not device_path:
      devpaths = _find_qtec_dev()
      mindev = 100000
      dev = 'None'
      for name, i in devpaths:
        if mindev > i:
          mindev = i
          dev = name
      device_path = dev

    (fmt,cp) = _get_device_info(device_path, pixelformat)
    #print(fmt, cp)
    #print( fmt.fmt.pix.pixelformat)
    compatible_wrappers = []
    temp_kwargs = kwargs.copy()
    temp_kwargs['reset'] = False
    temp_kwargs['cleanup'] = False
    #_mdata.device_list=[device_path]
    #print(_mdata)
    #print("_mdata.device_list", _mdata.device_list)
    for i in _mdata.device_list:
        try:
            tmp = i((device_path,fmt,cp,temp_kwargs))
            del (tmp)
            compatible_wrappers.append(i)
        except Exception as e:
            #print('Exception from wrapper ' + str(i) + ' : ' + str(e))
            logging.debug('Exception from wrapper ' + str(i) + ' : ' + str(e))
    #print("compatible_wrappers", compatible_wrappers)
    if compatible_wrappers:
        final_wrp = copy.copy(compatible_wrappers)
        for comb in itertools.combinations(compatible_wrappers,2):
            if issubclass(*comb) and comb[1] in final_wrp:
                final_wrp.remove(comb[1])
            elif issubclass(*comb[::-1]) and comb[0] in final_wrp:
                final_wrp.remove(comb[0])
        if not final_wrp:
            raise WrapperException('Empty wrapper list left after searching for optimal wrappers')
        cls = type( 'v4l2_Wrapper',
                    tuple(final_wrp),
                    {})
        obj = cls((device_path,fmt,cp,kwargs))
        #_add_del_to_obj(obj,cls)
        return obj

    raise WrapperException('The device type detected cannot be handled. '
                           'Make sure the device is not being used by other '
                           'software')
