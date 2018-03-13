# -*- coding: utf-8 -*-

'''Effective Voltage in TKinter window'''

from __future__ import division
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import sys, numpy as np

def mpPrint(Q, conf):
    '''effective Voltage of data passed via multiprocessing.Queue
        Args:
            conf: picoConfig object
            Q:    multiprocessing.Queue()   
    '''

    # Generator to provide data to animation
    # random consumer of Buffer Manager, receives an event copy 
    # via a Queue from package mutiprocessing

    cnt = 0
    try:
        while True:
            evNr, evTime, evData = Q.get()
            cnt+=1
            print("cnt: ", cnt, "\nevNr: ", evNr, "\nevTime: ", evTime, "\nevData: ", evData)
    except:
        print('*==* mpPrint: termination signal recieved')
        sys.exit()
