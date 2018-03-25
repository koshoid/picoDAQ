from __future__ import print_function, division, absolute_import, unicode_literals

import sys
import time, numpy as np
from scipy.signal import argrelmax
from scipy.interpolate import interp1d


class PulseProcessor:

    def __init__(self, bufferManager, config, consumerId, filterRateQueue = None, histogramQueue = None,
                 voltageSignalQueue = None, pulseDisplayQueue = None, consumerMode = 0, logPulses = False,
                 verbosity = 1):
        self.bufferManager = bufferManager
        self.config = config
        self.consumerId = consumerId
        self.consumerMode = consumerMode

        self.filterRateQueue = filterRateQueue
        self.histogramQueue = histogramQueue
        self.voltageSignalQueue = voltageSignalQueue
        self.pulseDisplayQueue = pulseDisplayQueue

        self.logPulses = logPulses
        self.verbosity = verbosity

    def generateTrapezoidPulse(self, timeScale, riseTime, onTime, fallTime, fallTime2 = 0, offTime = 0., riseTime2 = 0., mode = 0):
        '''
          create a single or double trapezoidal plulse,
            normalised to pulse height one
               ______
              /      \
           _ /_ _ _ _ \_ _ _ _ _ _ _
                       \__________/
            r    on  f f2   off  r2

          Args:
           rise time,
           on time,
           fall time
           off-time  for bipolar pulse
           fall time for bipolar pulse
           mode: 0 single unipolar, 1: double bipolar
        '''
        ti = [0., riseTime, riseTime + onTime, riseTime + onTime + fallTime]
        ri = [0., 1., 1., 0.]
        if mode:  # for bipolar pulse
            # normalize neg. pulse to same integral as positive part
            voltageOff = -(0.5 * (riseTime + fallTime) + onTime) / (0.5 * (fallTime2 + riseTime2) + offTime)
            ti = ti.append(riseTime + onTime + fallTime + fallTime2)
            ri = ri.append(voltageOff)
            ti = ti.append(riseTime + onTime + fallTime + fallTime2 + offTime)
            ri = ri.append(voltageOff)
            ti = ti.append(riseTime + onTime + fallTime + fallTime2 + offTime + riseTime2)
            ri = ri.append(0.)

        trapezoidInterpolator = interp1d(ti, ri, kind = 'linear', copy = False, assume_sorted = True)

        return trapezoidInterpolator(timeScale)

    def generateReferencePulse(self, dT, tauRise = 20E-9, tauOn = 12E-9, tauFall = 128E-9, pulseHeight = -0.030):
        '''
          Generates a reference pulse shape for convolution filter
          Args:
            time step
            rise time in sec
            fall-off time in sec
            pulse height in Volt
        '''
        pulseDuration = tauRise + tauOn + tauFall
        pulseDurationSamples = np.int32(pulseDuration / dT + 0.5) + 1
        timeScale = np.linspace(0, pulseDuration, pulseDurationSamples)
        referencePulse = pulseHeight * self.generateTrapezoidPulse(timeScale, tauRise, tauOn, tauFall)

        return referencePulse


    def displayPulse(self, id, pulse):
        self.putQueue(self.pulseDisplayQueue, (id, pulse))


    def putQueue(self, queue, obj):
        if queue is not None and queue.empty():
            queue.put(obj)

            return True

        return False


    def process(self):
        '''
          Find a pulse similar to a template pulse by cross-correlatation

            - implemented as an obligatory consumer, i.e.  sees all data

            - pulse detection via correlation with reference pulse;

                - detected pulses are cleaned in a second step by subtracting
                 the pulse mean (increased sensitivity to pulse shape)

            - analyis proceeds in three steps:

                1. validation of pulse on trigger channel
                2. coincidences on other channels near validated trigger pulse
                3. seach for addtional pulses on any channel
        '''

        # buffermanager must be active
        if not self.bufferManager.ACTIVE.value:
            if self.verbosity:
                print("*==* pulseFilter: Buffer Manager not active, exiting")
            sys.exit(1)

        # open a logfile
        if self.logPulses:
            datetime = time.strftime('%y%m%d-%H%M', time.gmtime())
            pulseFilterLog = open('pFilt_' + datetime + '.dat', 'w')
            print("# EvNr, EvT, Vs ...., Ts ...T",
                  file=pulseFilterLog)  # header line
            doublePulseFilterLog = open('dpFilt_' + datetime + '.dat', 'w', 1)
            print("# Nacc, Ndble, Tau, delT(iChan), ... V(iChan)",
                  file=doublePulseFilterLog)  # header line

        # retrieve configuration parameters
        dT = self.config.TSampling  # get sampling interval
        sampleOffset = 2  # precision on time resolution of pulse search
        nChannels = self.config.NChannels
        triggerChannel = -1  # trigger channel, initialized to -1
        for i, channel in enumerate(self.config.picoChannels):
            if channel == self.config.trgChan:
                triggerChannel = i
                break
        triggerSampleIndex = int(self.config.NSamples * self.config.pretrig)  # sample number of trigger point

        # set characteristics of reference pulse for convoultion pulse search
        #     unipolar pulse:
        tauRise = 20E-9       # rise time in (s)
        tauOn = 12E-9         # hold time in (s)
        tauFall = 128E-9      # fall time in (s)
        #pulseHeight = -0.030  # pulse height (V) (SiPM panels)
        pulseHeight = -0.035  # pulse height (V) (Kamiokanne)

        referencePulse = self.generateReferencePulse(dT, tauRise, tauOn, tauFall, pulseHeight)
        self.displayPulse(3, referencePulse)

        referencePulseLength = len(referencePulse)
        zeroNormalizedReferencePulse = referencePulse - referencePulse.mean()  # mean subtracted

        # calculate thresholds for correlation analysis
        pulseThreshold = np.sum(referencePulse * referencePulse)  # norm of reference pulse
        zeroNormalizedPulseThreshold = np.sum(zeroNormalizedReferencePulse * zeroNormalizedReferencePulse)  # norm of mean-subtracted reference pulse
        if self.verbosity > 1:
            self.bufferManager.prlog('*==* pulse Filter: reference pulse')
            self.bufferManager.prlog(np.array_str(referencePulse))
            self.bufferManager.prlog('  thresholds: %.2g, %2g ' % (pulseThreshold, zeroNormalizedPulseThreshold))

        # --- end initialisation

        # initialise event loop
        eventCount = 0  # events seen
        validCount = 0  # events with valid pulse shape on trigger channel
        singleCoincidenceCount = 0
        doubleCoincidenceCount = 0  # dual coincidences
        tripleCoincidenceCount = 0  # triple coincidences
        doublePulseCount = 0  # double pulses

        # arrays for quantities to be histogrammed
        noiseTriggerSignals = []  # pulse height of noise signals
        validTriggerSignals = []  # pulse height of valid triggers
        voltageSignals = []  # pulse heights non-triggering channels
        doublePulseTaus = []  # deltaT of double pulses

        # event loop
        while self.bufferManager.ACTIVE.value:
            validated = False
            accepted = False
            doublePulse = False
            event = self.bufferManager.getEvent(self.consumerId, mode = self.consumerMode)
            if event == None:
                break

            eventNumber, eventTime, eventData = event
            eventCount += 1
            if self.verbosity > 1:
                self.bufferManager.prlog('*==* pulseFilter: event Nr %i, %i events seen' % (eventNumber, eventCount))

            # find signal candidates by convoluting signal with reference pulse
            #   data structure to collect properties of selected pulses:
            pulseVoltages = [[0., 0.] for i in range(nChannels)]  # signal height in Volts
            pulseTimes = [[0., 0.] for i in range(nChannels)]     # time of valid pulse

            # 1. validate trigger pulse
            if triggerChannel >= 0:
                offset = max(0, triggerSampleIndex - int(tauRise / dT) - sampleOffset)
                cort = np.correlate(eventData[triggerChannel, 0:triggerSampleIndex + sampleOffset + referencePulseLength], referencePulse, mode = 'valid')
                cort[cort < pulseThreshold] = pulseThreshold  # set all values below threshold to threshold
                idtr = np.argmax(cort) + offset  # index of 1st maximum
                print("idtr: %i offset: %i" % (idtr, offset))
                if idtr > triggerSampleIndex + (tauRise + tauOn) / dT + sampleOffset:
                    noiseTriggerSignals.append(0.)
                    print("pulseFilter: Determined noise signal %i: " % (eventNumber))
                    print(np.array_str(eventData[triggerChannel, 0:triggerSampleIndex + sampleOffset + referencePulseLength]))
                    self.displayPulse(0, eventData[triggerChannel, 0:triggerSampleIndex + sampleOffset + referencePulseLength])
                    continue  # - while # no pulse near trigger, skip rest of event analysis
                # check pulse shape by requesting match with time-averaged pulse
                evdt = eventData[triggerChannel, idtr:idtr + referencePulseLength]
                evdtm = evdt - evdt.mean()  # center signal candidate around zero
                cc = np.sum(evdtm * zeroNormalizedReferencePulse)  # convolution with mean-corrected reference
                if cc > zeroNormalizedPulseThreshold:
                    validated = True  # valid trigger pulse found, store
                    validCount += 1
                    V = max(abs(evdt))  # signal Voltage
                    pulseVoltages[triggerChannel][0] = V
                    validTriggerSignals.append(V)
                    T = idtr * dT * 1E6  # signal time in musec
                    pulseTimes[triggerChannel][0] = T
                    tevt = T  # time of event
                    self.displayPulse(2, eventData[triggerChannel, idtr:idtr + referencePulseLength])
                else:  # no valid trigger
                    noiseTriggerSignals.append(max(abs(evdt)))
                    self.displayPulse(1, eventData[triggerChannel, idtr:idtr + referencePulseLength])
                    continue  # - while # skip rest of event analysis

            # 2. find coincidences
            print("pulseFilter: Checking for coincidence")
            Ncoinc = 1
            for iC in range(nChannels):
                if iC != triggerChannel:
                    offset = max(0, idtr - sampleOffset)  # search around trigger pulse
                    #  analyse channel to find pulse near trigger
                    cor = np.correlate(eventData[iC, offset:triggerSampleIndex + sampleOffset + referencePulseLength],
                                       referencePulse, mode='valid')
                    cor[cor < pulseThreshold] = pulseThreshold  # set all values below threshold to threshold
                    id = np.argmax(cor) + offset  # find index of (1st) maximum
                    if id > triggerSampleIndex + (tauRise + tauOn) / dT + sampleOffset:
                        print("pulseFilter: no pulse near trigger, skip:")
                        #          print(np.array_str(evData[iC, offset:idT0+idTprec+lref]))
                        continue  # - for # no pulse near trigger, skip
                    evd = eventData[iC, id:id + referencePulseLength]
                    evdm = evd - evd.mean()  # center signal candidate around zero
                    cc = np.sum(evdm * zeroNormalizedReferencePulse)  # convolution with mean-corrected reference
                    if cc > zeroNormalizedPulseThreshold:
                        Ncoinc += 1  # valid, coincident pulse
                        self.bufferManager.prlog("pulseFilter: Coincidence in channel %i" % (iC))
                        V = max(abs(evd))
                        pulseVoltages[iC][0] = V  # signal voltage
                        voltageSignals.append(V)
                        T = id * dT * 1E6  # signal time in musec
                        pulseTimes[iC][0] = T
                        tevt += T

            # check wether event should be accepted
            if (nChannels == 1 and validated) or (nChannels > 1 and Ncoinc >= 2):
                accepted = True
                singleCoincidenceCount += 1
                print("pulseFilter: Accepted event")
            else:
                print("pulseFilter: Did not accept event")
                continue  # - while

            # fix event time:
            tevt /= Ncoinc
            if Ncoinc == 2:
                doubleCoincidenceCount += 1
            elif Ncoinc == 3:
                tripleCoincidenceCount += 1

            # 3. find subsequent pulses in accepted events
            offset = idtr + referencePulseLength  # search after trigger pulse
            print("pulseFilter: Looking for double pulse")
            for iC in range(nChannels):
                cor = np.correlate(eventData[iC, offset:], referencePulse, mode='valid')
                cor[cor < pulseThreshold] = pulseThreshold  # set all values below threshold to threshold
                idmx, = argrelmax(cor) + offset  # find index of maxima in evData array
                # clean-up pulse candidates by requesting match with time-averaged pulse
                iacc = 0
                for id in idmx:
                    evd = eventData[iC, id:id + referencePulseLength]
                    evdm = evd - evd.mean()  # center signal candidate around zero
                    cc = np.sum(evdm * zeroNormalizedReferencePulse)  # convolution with mean-corrected reference
                    if cc > zeroNormalizedPulseThreshold:  # valid pulse
                        iacc += 1
                        V = max(abs(evd))  # signal Voltage
                        if iacc == 1:
                            pulseVoltages[iC][1] = V
                            pulseTimes[iC][1] = id * dT * 1E6  # signal time in musec
                        else:
                            pulseVoltages[iC].append(V)  # extend arrays if more than 1 extra pulse
                            pulseTimes[iC].append(id * dT * 1E6)
                        #     -- end loop over pulse candidates
            #   -- end for loop over channels

            #  statistics on double pulses on either channel
            delT2s = np.zeros(nChannels)
            sig2s = np.zeros(nChannels)
            sumdT2 = 0.
            N2nd = 0.
            for iC in range(nChannels):
                if pulseVoltages[iC][1] > 0.:
                    doublePulse = True
                    N2nd += 1
                    delT2s[iC] = pulseTimes[iC][-1] - tevt  # take last pulse found
                    sig2s[iC] = pulseVoltages[iC][-1]
                    sumdT2 += delT2s[iC]
            if doublePulse:
                doublePulseCount += 1
                doublePulseTaus.append(sumdT2 / N2nd)

            # eventually store results in file(s)
            # 1. all accepted events
            if self.logPulses and accepted:
                print('%i, %.2f' % (eventNumber, eventTime), end='', file=pulseFilterLog)
                for ic in range(nChannels):
                    v = pulseVoltages[ic][0]
                    t = pulseTimes[ic][0]
                    if v > 0: t -= tevt
                    print(', %.3f, %.3f' % (v, t), end='', file=pulseFilterLog)
                if doublePulse:
                    for ic in range(nChannels):
                        v = pulseVoltages[ic][1]
                        t = pulseTimes[ic][1]
                        if v > 0: t -= tevt
                        print(', %.3f, %.3f' % (v, t), end='', file=pulseFilterLog)
                    for ic in range(nChannels):
                        if len(pulseVoltages[ic]) > 2:
                            print(', %i, %.3f, %.3f' % (ic, pulseVoltages[ic][2], pulseTimes[ic][2]),
                                  end='', file=pulseFilterLog)
                print('', file=pulseFilterLog)

            # 2. double pulses
            if self.logPulses and doublePulse:
                if nChannels == 1:
                    print('%i, %i, %.4g,   %.4g, %.3g' \
                          % (singleCoincidenceCount, doublePulseCount, doublePulseTaus[-1], delT2s[0], sig2s[0]),
                          file=doublePulseFilterLog)
                elif nChannels == 2:
                    print('%i, %i, %.4g,   %.4g, %.4g,   %.3g, %.3g' \
                          % (singleCoincidenceCount, doublePulseCount, doublePulseTaus[-1],
                             delT2s[0], delT2s[1], sig2s[0], sig2s[1]),
                          file=doublePulseFilterLog)
                elif nChannels == 3:
                    print('%i, %i, %.4g,   %.4g, %.4g, %.4g,   %.3g, %.3g, %.3g' \
                          % (singleCoincidenceCount, doublePulseCount, doublePulseTaus[-1],
                             delT2s[0], delT2s[1], delT2s[2],
                             sig2s[0], sig2s[1], sig2s[2]),
                          file=doublePulseFilterLog)
            # print to screen
            if accepted and self.verbosity > 1:
                if nChannels == 1:
                    self.bufferManager.prlog('*==* pF: %i, %i, %.2f, %.3g, %.3g' \
                             % (eventCount, singleCoincidenceCount, tevt, pulseVoltages[0][0]))
                elif nChannels == 2:
                    self.bufferManager.prlog('*==* pF: %i, %i, i%, %.3g, %.3g, %.3g' \
                             % (eventCount, validCount, singleCoincidenceCount, tevt, pulseVoltages[0][0], pulseVoltages[1][0]))
                elif nChannels == 3:
                    self.bufferManager.prlog('*==* pF: %i, %i, %i, %i, %i, %.3g' \
                             % (eventCount, validCount, singleCoincidenceCount, doubleCoincidenceCount, tripleCoincidenceCount, tevt))

            if (self.verbosity and eventCount % 1000 == 0):
                self.bufferManager.prlog("*==* pF: evt %i, Nval, Nacc, Nacc2, Nacc3: %i, %i, %i, %i" \
                         % (eventCount, validCount, singleCoincidenceCount, doubleCoincidenceCount, tripleCoincidenceCount))

            if self.verbosity and doublePulse:
                s = '%i, %i, %.4g' \
                    % (singleCoincidenceCount, doublePulseCount, doublePulseTaus[-1])
                self.bufferManager.prlog('*==* double pulse: Nacc, Ndble, dT ' + s)

            # provide information necessary for RateMeter
            self.putQueue(self.filterRateQueue, (singleCoincidenceCount, eventTime))
            # provide information necessary for histograms
            if len(validTriggerSignals) and \
                    self.putQueue(self.histogramQueue,
                                  [noiseTriggerSignals, validTriggerSignals, voltageSignals, doublePulseTaus]):
                noiseTriggerSignals = []
                validTriggerSignals = []
                voltageSignals = []
                doublePulseTaus = []
            # provide information necessary for Panel Display
            self.putQueue(self.voltageSignalQueue, [pulseVoltages[iC][0] for iC in range(nChannels)])

            # break e == None

        # -- end BM.ACTIVE
        if self.logPulses:
            tag = "# pulseFilter Summary: "
            if pulseFilterLog:
                print(tag + "last evNR %i, Nval, Nacc, Nacc2, Nacc3: %i, %i, %i, %i" \
                      % (eventCount, validCount, singleCoincidenceCount, doubleCoincidenceCount, tripleCoincidenceCount),
                      file=pulseFilterLog)
                pulseFilterLog.close()

            if doublePulseFilterLog:
                print(tag + "last evNR %i, Nval, Nacc, Nacc2, Nacc3: %i, %i, %i, %i" \
                      % (eventCount, validCount, singleCoincidenceCount, doubleCoincidenceCount, tripleCoincidenceCount),
                      file=doublePulseFilterLog)
                print("#                       %i double pulses" % (doublePulseCount),
                      file=doublePulseFilterLog)
                doublePulseFilterLog.close()

        return
    # -end def pulseFilter
