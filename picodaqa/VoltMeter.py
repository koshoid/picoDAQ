# -*- coding: utf-8 -*-
from __future__ import division
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import time, numpy as np

import matplotlib
matplotlib.use('wxagg') # set backend (qt5 not running as thread in background)
#matplotlib.use('tkagg') # set backend (qt5 not running as thread in background)
import matplotlib.pyplot as plt, matplotlib.animation as anim

class VoltMeter(object):
  ''' Bar graph display of average over samples '''

   def __init__(self, Wtime, conf):
   # Args: Wtime: waiting time between updates
           conf: Configuration of channels
    # collect relevant configuration parameters
    self.Wtime = Wtime    # time in ms between samplings
    self.Npoints = 120  # number of points for history
    self.bwidth = 0.5   # width of bars

    self.NChannels = conf.NChannels
    self.CRanges = conf.CRanges     # channel voltage ranges (hw settings)
    self.ChanColors = conf.ChanColors

    

   # data structures needed throughout the class
    self.ix = np.linspace(-self.Npoints+1, 0, self.Npoints) # history plot
    self.ind = self.bwidth + np.arange(self.NChannels) # bar position for voltages
  # 
    self.V = np.empty(self.NChannels)
    self.stdV = np.empty(self.NChannels)
    self.Vhist = np.zeros( [self.NChannels, self.Npoints] )
    self.stdVhist = np.zeros( [self.NChannels, self.Npoints] )

# set up a figure to plot actual voltage and samplings from Picoscope
    fig = plt.figure("Voltmeter", figsize=(4., 6.) )
    fig.subplots_adjust(left=0.2, bottom=0.08, right=0.8, top=0.95,
                  wspace=None, hspace=.25)
    axes=[]
  # history plot
    axes.append(plt.subplot2grid((7,1),(5,0), rowspan=2) )
    axes.append(axes[0].twinx())
    axes[0].set_ylim(-self.CRanges[0], self.CRanges[0])
    axes[1].set_ylim(-self.CRanges[1], self.CRanges[1])
    axes[0].set_xlabel('History')
    axes[0].set_ylabel('Chan A (V)', color=self.ChanColors[0])
    axes[1].set_ylabel('Chan B (V)', color=self.ChanColors[1])
  # barchart
    axes.append(plt.subplot2grid((7,1),(1,0), rowspan=4) )
    axbar1=axes[2]
    axbar1.set_frame_on(False)
    axbar2=axbar1.twinx()
    axbar2.set_frame_on(False)
    axbar1.get_xaxis().set_visible(False)
    axbar1.set_xlim(0., self.NChannels)
    axbar1.axvline(0, color = self.ChanColors[0])
    axbar1.axvline(self.NChannels, color = self.ChanColors[1])
    axbar1.set_ylim(-self.CRanges[0], self.CRanges[0])
    axbar1.axhline(0., color='k', linestyle='-', lw=2, alpha=0.5)
    axbar2.set_ylim(-self.CRanges[1], self.CRanges[1])
    axbar1.set_ylabel('Chan A (V)', color = self.ChanColors[0])
    axbar2.set_ylabel('Chan B (V)', color = self.ChanColors[1])
  # Voltage in Text format
    axes.append(plt.subplot2grid((7,1),(0,0)) )
    axtxt=axes[3]
    axtxt.set_frame_on(False)
    axtxt.get_xaxis().set_visible(False)
    axtxt.get_yaxis().set_visible(False)
    axtxt.set_title('Picoscope as Voltmeter', size='xx-large')

    self.fig = fig
    self.axes = axes
    self.axbar1 = axbar1
    self.axbar2 = axbar2
# -- end def grVMeterIni

  def init(self):
  # initialize objects to be animated

  # a bar graph for the actual voltages
#    self.bgraph = self.axes[0].bar(ind, np.zeros(self.NChannels), self.bwidth,
#                           align='center', color='grey', alpha=0.5)
    self.bgraph1, = self.axbar1.bar(self.ind[0], 0. , self.bwidth,
                         align='center', color=ChanColors[0], alpha=0.5) 
    self.bgraph2, = self.axbar2.bar(self.ind[1], 0. , self.bwidth,
                         align='center', color=ChanColors[1], alpha=0.5) 
  # history graphs
    self.graphs=()
    for i, C in enumerate(picoChannels):
      g,= self.axes[i].plot(self.ix, np.zeros(self.Npoints), color=ChanColors[i])
      self.graphs += (g,)
    self.animtxt = self.axes[3].text(0.01, 0.05 , ' ',
              transform=self.axes[3].transAxes,
              size='large', color='darkblue')

    self.t0=time.time() # remember start time

    return (self.bgraph1,) + (self.bgraph2,) + self.graphs + (self.animtxt,)  
# -- end VoltMeter.init()

  def __call__( self, (n, evTime, evData) ):
    if n == 0:
      return self.init()

    k=n%self.Npoints
    txt_t='Time  %.1fs' %(evTime-self.t0)            
    txt=[]
    for i, C in enumerate(picoChannels):
      self.V[i] = evData[i].mean()
      self.Vhist[i, k] = self.V[i]
      self.stdV[i] = evData[i].std()
      self.stdVhist[i, k] = self.stdV[i]
    # update history graph
      if n>1: # !!! fix to avoid permanent display of first object in blit mode
        self.graphs[i].set_data(self.ix,
          np.concatenate((self.Vhist[i, k+1:], self.Vhist[i, :k+1]), axis=0) )
      else:
        self.graphs[i].set_data(self.ix, np.zeros(self.Npoints))
      txt.append('  %s:   %.3gV +/-%.2gV' % (C, self.Vhist[i,k], 
                                               self.stdVhist[i,k]) )
    # update bar chart
#      for r, v in zip(bgraph, V):
#          r.set_height(v)
    if n>1: # !!! fix to avoid permanent display of first object in blit mode
      self.bgraph1.set_height(self.V[0])
      self.bgraph2.set_height(self.V[1])
    else:  
      self.bgraph1.set_height(0.)
      self.bgraph2.set_height(0.)
    self.animtxt.set_text(txt_t + '\n' + txt[0] + '\n' + txt[1])
#
    return (self.bgraph1,) + (self.bgraph2,) + self.graphs + (self.animtxt,)
#- -end def Voltmeter.__call__
#-end class VoltMeter
