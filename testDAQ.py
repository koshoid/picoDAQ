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

# get Client Id from BufferManager (must be done in mother process)
cId_o = BM.BMregister() 
procs.append(mp.Process(target=randConsumer,
                             args=(BM, cId_o) ) )
# client Id for random consumer
cId_r = BM.BMregister() 
procs.append(mp.Process(target=obligConsumer,
                             args=(BM, cId_r) ) )

# <<< - end of inserted code
