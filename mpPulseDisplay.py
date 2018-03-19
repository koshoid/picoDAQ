import sys
import numpy as np
import matplotlib.pyplot as plt
import traceback as trace
from collections import deque

def mpPulseDisplay(Q, conf):
    '''Oscilloscpe display of data passed via multiprocessing.Queue
      Args:
        conf: picoConfig object
        Q:    multiprocessing.Queue()   
    '''
    axes=[]
    colors=[]
    data=[]
    fig=plt.figure(1,figsize=(10.,10.))
    axes.append(fig.add_subplot(3,1,1))
    axes.append(fig.add_subplot(3,1,2))
    axes.append(fig.add_subplot(3,1,3))
#    axes.append(fig.add_subplot(4,1,4))
    axes[0].set_xlabel("ns")
    axes[1].set_xlabel("ns")
    axes[2].set_xlabel("ns")
#    axes[3].set_xlabel("ns")
    axes[0].set_ylabel("noise pulse")
    axes[1].set_ylabel("rejected pulse")
    axes[2].set_ylabel("accepted pulse")
#    axes[3].set_ylabel("ref pulse")
#FIXME: This should not be fixed and the timescale should be correct
    samples=100
    ts=np.arange(0,samples,1)
    axes[0].set_xlim(0.,samples)
    axes[1].set_xlim(0.,samples)
    axes[2].set_xlim(0.,samples)
#    axes[3].set_xlim(0.,samples)
    axes[0].set_ylim(-0.05,0.)
    axes[1].set_ylim(-0.05,0.)
    axes[2].set_ylim(-0.05,0.)
#    axes[3].set_ylim(-0.05,0.)
#    colors=['blue','red','green']
    colors.append(['#4e79a7','#6c8fb6','#89a6c4','#a7bcd3','#c4d2e2','#e2e9f0'])
    colors.append(['#e15759','#e67375','#eb8f90','#f0abac','#f5c7c8','#fae3e3'])
    colors.append(['#59a14f','#75b16c','#90c08a','#acd0a7','#c8e0c4','#e3efe2'])
    data.append(deque([],6))
    data.append(deque([],6))
    data.append(deque([],6))




#    axes[0].plot(ts,ts)
#    axes[1].plot(ts,ts)
#    axes[2].plot(ts,ts)
    refdata=[]
    plt.show(block=False)

    cnt=0

    try:
        while True:
            eventType, evData = Q.get()
            print("PulseDisplay received Queue element")
            if eventType==3:
                if evData.size<samples:
                    refdata=np.append(evData,np.zeros(samples-evData.size))
                else:
                    refdata=evData[:samples]
                continue
            cnt+=1
            if evData.size<samples:
                data[eventType].appendleft(np.append(evData,np.zeros(samples-evData.size)))
            else:
                data[eventType].appendleft(evData[:samples])

            axes[eventType].lines=[]

            for d,c,z in zip(data[eventType],colors[eventType],range(6,1,-1)):
                axes[eventType].plot(ts,d,c,zorder=z)
            
            if refdata != []:
                axes[eventType].plot(ts,refdata,'orange')
            plt.show(block=False)
            plt.pause(0.01)
    except:
        print('*==* mpPulseDisplay: termination signal received')
        trace.print_exc()
        sys.exit()

