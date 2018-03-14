# -*- coding: utf-8 -*-

from __future__ import division, absolute_import, print_function, unicode_literals

import sys, numpy as np, time, traceback as trace

def mpProcessPulse(BM, conf, cId):
    '''effective Voltage of data passed via multiprocessing.Queue
        Args:
            conf: picoConfig object
            Q:    multiprocessing.Queue()   
    '''

    # Generator to provide data to animation
    # random consumer of Buffer Manager, receives an event copy 
    # via a Queue from package mutiprocessing

    np.set_printoptions(threshold=20000,linewidth=5)
    cnt = 0
    if not BM.ACTIVE.value: sys.exit(1)
# register with Buffer Manager
    mode = 0    # obligatory consumer, data in evdata transferred as pointer
    evcnt=0
    while BM.ACTIVE.value:
        e = BM.getEvent(cId, mode=mode)
        if e != None:
            evNr, evtime, evData = e
            evcnt+=1
            cnt+=1
#            filename="eventlog_" + time.strftime("%Y-%m-%dT%H-%M-%S",time.gmtime()) + "-" + str(evNr)
#            logfile=open(filename, "w")
#            s="#cnt: " + str(cnt) + "\n#evNr: " +str(evNr) + "\n#evTime: " + str(evTime) + "\n"
#            logfile.write(s)
#            s=str(evData) + "\n"
#            logfile.write(s)
#            logfile.close()
            if ((evData[1,251] < -0.04) and (evData[2,251] > -0.01)):
                print("Accepting pulse in coincidence filter with A: " + str(evData[0,251]) + " B: " + str(evData[1,251]) + " C: " + str(evData[2,251]))
#                filename="pulselog_" + time.strftime("%Y-%m-%dT%H-%M-%S",time.gmtime()) + "-" + str(evNr)
#                pulsefile=open(filename, "w")
#                s="#cnt: " + str(cnt) + "\n#evNr: " +str(evNr) + "\n#evTime: " + str(evTime) + "\n"
#                pulsefile.write(s)
#                s=str(evData) + "\n"
#                pulsefile.write(s)
#                pulsefile.close()
                
            else:
                print("Rejecting pulse in coincidence filter with A: " + str(evData[0,250]) + " B: " + str(evData[1,250]) + " C: " + str(evData[2,250]))
#                filename="rejectlog_" + time.strftime("%Y-%m-%dT%H-%M-%S",time.gmtime()) + "-" + str(evNr)
#                rejectfile=open(filename, "w")
#                s="#cnt: " + str(cnt) + "\n#evNr: " +str(evNr) + "\n#evTime: " + str(evTime) + "\n"
#                rejectfile.write(s)
#                s=str(evData) + "\n"
#                rejectfile.write(s)
#                rejectfile.close()
    print("ProcessPulse exiting")
    sys.exit()
