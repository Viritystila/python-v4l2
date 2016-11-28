''' wrapper for qtec memory
    does not work with device wrapper, used only by
    device buffer in fragmented memory cases
'''

#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: Dimitrios Katsaros
# @Date:   2014-08-05 10:50:48
# @Last Modified by:   Dimitrios Katsaros
# @Last Modified time: 2016-11-28 14:56:43

import mmap
import ctypes as ct

MEM_FILE = '/dev/qtec_mem'
MAX_MEM = 8000000 #8 MB

class qtec_mem_error(Exception):
    def __init__(self, value):
        self.parameter = value
    def __str__(self):
        return 'QTec Memory: {}'.format(repr(self.parameter))


class qtec_memory(object):
    """wrapper for Qtec memory"""


    def __init__(self):
        super(qtec_memory, self).__init__()

        self._fd = open(MEM_FILE, 'r+w+b')
        self._reserved_size = 0
        self._mmap_list = []


    def get_next_memory_frame(self, size):
        '''returns a ctypes char array mapped to qtec memory
           size is the size in bytes of the buffer'''

        if size + self._reserved_size > MAX_MEM:
            raise qtec_mem_error('Not enough memory left')

        buff = ct.c_char * size
        #print size, self._reserved_size
        mm = mmap.mmap(self._fd.fileno(), size, flags=mmap.MAP_SHARED,
            prot=(mmap.PROT_READ | mmap.PROT_WRITE), offset=self._reserved_size)
        pageno = 1
        while mmap.PAGESIZE * pageno < size:
            pageno += 1
        self._reserved_size += mmap.PAGESIZE * pageno
        self._mmap_list.append(mm)
        return buff.from_buffer(mm)


