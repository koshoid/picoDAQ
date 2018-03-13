# -*- coding: utf-8 -*-
# code fragment  testDAQ.py to run inside runDAQ.py
'''
  code fragment to embed user code (in exampleComsumers.py) into
   script runDAQ.py
'''

# ->>> code from here inserted as 'testDAQ.py' in runDAQ.py

# import analysis code as library
from exampleConsumers import *
from mpProcessPulse import *
from examples.pulseFilter import *

#thrds.append(threading.Thread(target=randConsumer,                             args=(BM,) ) )
#thrds.append(threading.Thread(target=obligConsumer,                             args=(BM,) ) )
thrds.append(threading.Thread(target=pulseFilter, args=(BM,PSconf), kwargs={'fileout':True}))

ProcessPulseidx, ProcessPulsempQ = BM.BMregister_mpQ()
procs.append(mp.Process(name='ProcessPulse', target = mpProcessPulse,args=(ProcessPulsempQ, PSconf)))



# <<< - end of inserted code
