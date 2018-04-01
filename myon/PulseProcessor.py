from __future__ import print_function, division, absolute_import, unicode_literals

import time, numpy as np, math
from scipy.signal import argrelmax
from scipy.interpolate import interp1d


class PulseProcessor:

    def __init__(self, bufferManager, config, consumerId, filterRateQueue=None, histogramQueue=None,
                 voltageSignalQueue=None, pulseDisplayQueue=None, consumerMode=0, logPulses=False,
                 verbosity=1):
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

        if self.logPulses:
            datetime = time.strftime('%y%m%d-%H%M', time.gmtime())
            self.pulseFilterLog = open('pulseLogs/pFilt_' + datetime + '.dat', 'w')
            print("# EvNr, EvT, Vs ...., Ts ...T",
                  file=self.pulseFilterLog)  # header line
            self.doublePulseFilterLog = open('pulseLogs/dpFilt_' + datetime + '.dat', 'w', 1)
            print("# Nacc, Ndble, Tau, delT(iChan), ... V(iChan)",
                  file=self.doublePulseFilterLog)  # header line

        # retrieve configuration parameters
        self.dT = self.config.TSampling  # get sampling interval
        self.sampleOffset = 2  # precision on time resolution of pulse search
        self.nChannels = self.config.NChannels
        self.triggerChannel = -1  # trigger channel, initialized to -1
        for i, channel in enumerate(self.config.picoChannels):
            if channel == self.config.trgChan:
                self.triggerChannel = i
                break
        self.triggerSampleIndex = int(self.config.NSamples * self.config.pretrig)  # sample number of trigger point

        # set characteristics of reference pulse for convoultion pulse search
        #     unipolar pulse:
        self.tauRise = 20E-9  # rise time in (s)
        self.tauOn = 12E-9  # hold time in (s)
        self.tauFall = 128E-9  # fall time in (s)
        # pulseHeight = -0.030  # pulse height (V) (SiPM panels)
        self.pulseHeight = -0.035  # pulse height (V) (Kamiokanne)

        self.referencePulse = self.generateReferencePulse(self.dT, self.tauRise, self.tauOn, self.tauFall, self.pulseHeight)
        self.displayPulse(3, self.referencePulse)

        self.referencePulseLength = len(self.referencePulse)
        self.zeroNormalizedReferencePulse = self.referencePulse - self.referencePulse.mean()  # mean subtracted

        # calculate thresholds for correlation analysis
        self.pulseThreshold = np.sum(self.referencePulse * self.referencePulse)  # norm of reference pulse
        self.zeroNormalizedPulseThreshold = np.sum(
            self.zeroNormalizedReferencePulse * self.zeroNormalizedReferencePulse)  # norm of mean-subtracted reference pulse
        if self.verbosity > 1:
            self.bufferManager.prlog('*==* pulse Filter: reference pulse')
            self.bufferManager.prlog(np.array_str(self.referencePulse))
            self.bufferManager.prlog(
                '  thresholds: %.2g, %2g ' % (self.pulseThreshold, self.zeroNormalizedPulseThreshold))

        self.eventCount = 0
        self.validCount = 0  # events with valid pulse shape on trigger channel
        self.coincidenceCount = 0
        self.doubleCoincidenceCount = 0
        self.tripleCoincidenceCount = 0
        self.doublePulseCount = 0

        # arrays for quantities to be histogrammed
        self.noiseTriggerSignals = []  # pulse height of noise signals
        self.validTriggerSignals = []  # pulse height of valid triggers
        self.voltageSignals = []  # pulse heights non-triggering channels
        self.doublePulseTaus = []  # deltaT of double pulses

    def generateTrapezoidPulse(self, timeScale, riseTime, onTime, fallTime, fallTime2=0, offTime=0., riseTime2=0.,
                               mode=0):
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

        trapezoidInterpolator = interp1d(ti, ri, kind='linear', copy=False, assume_sorted=True)

        return trapezoidInterpolator(timeScale)

    def generateMyonicPulse(self, timeScale, riseTime, onTime, lifeTime):
        """
            create a single pulse that looks right
        :param timeScale:
        :param riseTime:
        :param onTime:
        :param fallTime:
        :return:
        """

        ti = [0., riseTime, riseTime + onTime, riseTime + onTime + lifeTime, riseTime + onTime + 2 * lifeTime,
              riseTime + onTime + 3 * lifeTime, riseTime + onTime + 4 * lifeTime, riseTime + onTime + 5 * lifeTime, riseTime + onTime + 6 * lifeTime]
        ri = [0., 1., 1., math.exp(-1), math.exp(-2), math.exp(-3), math.exp(-4), math.exp(-5), math.exp(-6)]
        myonicInterpolator = interp1d(ti,ri, kind='linear', copy=False, assume_sorted=True)

        return myonicInterpolator(timeScale)

    def generateReferencePulse(self, dT, tauRise=20E-9, tauOn=12E-9, tauFall=128E-9, pulseHeight=-0.030):
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
        referencePulse = pulseHeight * self.generateMyonicPulse(timeScale, tauRise, tauOn, 0.3*tauFall)

        return referencePulse

    def displayPulse(self, id, pulse):
        if self.putQueue(self.pulseDisplayQueue, (id, pulse)):
            print("displayPulse: Displayed pulse")
        else:
            print("displayPulse: Dropped pulse")

    def putQueue(self, queue, obj):
        if queue is not None and queue.empty():
            queue.put(obj)

            return True

        return False

    def run(self):
        while self.bufferManager.ACTIVE.value:
            event = self.bufferManager.getEvent(self.consumerId, mode = self.consumerMode)
            if event is None:
                break

            self.process(event)

        self.close()

    def process(self, event):
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
        eventNumber, eventTime, eventData = event
        self.eventCount += 1
        if self.verbosity > 1:
            self.bufferManager.prlog('*==* PulseProcessor: event Nr %i, %i events seen' % (eventNumber, self.eventCount))

        # find signal candidates by convoluting signal with reference pulse
        #   data structure to collect properties of selected pulses:
        pulseVoltages = [[0.] for i in range(self.nChannels)]
        pulseTimes = [[0.] for i in range(self.nChannels)]

        validated, firstPeak, firstPeakVoltage = self.validateTriggerPulse(eventData)
        if self.triggerChannel >= 0 and validated is False:
            self.noiseTriggerSignals.append(firstPeakVoltage)

            return False

        self.validCount += 1
        pulseVoltages[self.triggerChannel][0] = firstPeakVoltage
        self.validTriggerSignals.append(firstPeakVoltage)
        firstPeakTime = firstPeak * self.dT * 1E6
        pulseTimes[self.triggerChannel][0] = firstPeakTime

        coincidenceCount, coincidenceVoltages, coincidenceTimes = self.findCoincidences(eventData, firstPeak)
        for channel in range(self.nChannels):
            pulseVoltages[channel][0] = coincidenceVoltages[channel]
            pulseTimes[channel][0] = coincidenceTimes[channel]
        self.voltageSignals.extend(coincidenceVoltages)
        if coincidenceCount > 1:
            firstPeakTime += np.sum(coincidenceTimes)
            firstPeakTime /= coincidenceCount
        if coincidenceCount == 2:
            self.doubleCoincidenceCount += 1
        elif coincidenceCount == 3:
            self.tripleCoincidenceCount += 1

        if self.nChannels == 1 or (self.nChannels > 1 and coincidenceCount >= 2):
            accepted = True
            self.coincidenceCount += 1
            print("PulseProcessor: Accepted event")
        else:
            print("PulseProcessor: Did not accept event")

            return False

        doublePulseCount, doublePulseVoltages, doublePulseTimes = self.findDoublePulses(eventData, firstPeak)
        hasDoublePulse = False
        doublePulseChannelsCount = 0
        lastDoublePulseDeltaTs = [0. for i in range(self.nChannels)]
        lastDoublePulseVoltages = [0. for i in range(self.nChannels)]
        for channel in range(self.nChannels):
            pulseVoltages.extend(doublePulseVoltages)
            pulseTimes.extend(doublePulseTimes)
            if doublePulseCount[channel] > 0:
                hasDoublePulse = True
                doublePulseChannelsCount += 1
                lastDoublePulseDeltaTs[channel] = pulseTimes[channel][-1] - firstPeakTime
                lastDoublePulseVoltages[channel] = pulseVoltages[channel][-1]

        if hasDoublePulse:
            self.doublePulseCount += 1
            self.doublePulseTaus.append(np.sum(lastDoublePulseDeltaTs) / doublePulseChannelsCount)

        # eventually store results in file(s)
        # 1. all accepted events
        if self.logPulses and accepted:
            print('%i, %.2f' % (eventNumber, eventTime), end='', file=self.pulseFilterLog)
            for channel in range(self.nChannels):
                v = pulseVoltages[channel][0]
                t = pulseTimes[channel][0]
                if v > 0: t -= firstPeakTime
                print(', %.3f, %.3f' % (v, t), end='', file=self.pulseFilterLog)
                if hasDoublePulse:
                    v = pulseVoltages[channel][1] if len(pulseVoltages[channel]) > 1 else 0.
                    t = pulseTimes[channel][1] if len(pulseTimes[channel]) > 1 else 0.
                    if v > 0: t -= firstPeakTime
                    print(', %.3f, %.3f' % (v, t), end='', file=self.pulseFilterLog)
                    if len(pulseVoltages[channel]) > 2:
                        print(', %i, %.3f, %.3f' % (channel, pulseVoltages[channel][2], pulseTimes[channel][2]),
                              end='', file=self.pulseFilterLog)
            print('', file=self.pulseFilterLog)

        # 2. double pulses
        if self.logPulses and hasDoublePulse:
            print("%i, %i, %.4g,   %s,   %s" % (
                self.coincidenceCount,
                self.doublePulseCount,
                self.doublePulseTaus[-1],
                ", ".join(["%.4g" % d for d in lastDoublePulseDeltaTs]),
                ", ".join(["%.3g" % s for s in lastDoublePulseVoltages])
            ), file=self.doublePulseFilterLog)
        # print to screen
        if accepted and self.verbosity > 1:
            if self.nChannels == 1:
                self.bufferManager.prlog('*==* PulseProcessor: %i, %i, %.2f, %.3g' % (
                    self.eventCount,
                    self.coincidenceCount,
                    firstPeakTime,
                    pulseVoltages[0][0]
                ))
            elif self.nChannels == 2:
                self.bufferManager.prlog('*==* PulseProcessor: %i, %i, %i, %.3g, %.3g, %.3g' % (
                     self.eventCount,
                     self.validCount,
                     self.coincidenceCount,
                     firstPeakTime,
                     pulseVoltages[0][0],
                     pulseVoltages[1][0]
                ))
            elif self.nChannels == 3:
                self.bufferManager.prlog('*==* PulseProcessor: %i, %i, %i, %i, %i, %.3g' % (
                    self.eventCount,
                    self.validCount,
                    self.coincidenceCount,
                    self.doubleCoincidenceCount,
                    self.tripleCoincidenceCount,
                    firstPeakTime
                ))

        if self.verbosity and self.eventCount % 1000 == 0:
            self.bufferManager.prlog("*==* PulseProcessor: evt %i, Nval, Nacc, Nacc2, Nacc3: %i, %i, %i, %i" % (
                self.eventCount,
                self.validCount,
                self.coincidenceCount,
                self.doubleCoincidenceCount,
                self.tripleCoincidenceCount
            ))

        if self.verbosity and hasDoublePulse:
            self.bufferManager.prlog('*==* double pulse: Nacc, Ndble, dT %i, %i, %.4g' % (
                self.coincidenceCount,
                self.doublePulseCount,
                self.doublePulseTaus[-1]
            ))

        # provide information necessary for RateMeter
        self.putQueue(self.filterRateQueue, (self.coincidenceCount, eventTime))
        # provide information necessary for histograms
        if len(self.validTriggerSignals) and self.putQueue(self.histogramQueue,
                  [self.noiseTriggerSignals, self.validTriggerSignals, self.voltageSignals, self.doublePulseTaus]):
            self.noiseTriggerSignals = []
            self.validTriggerSignals = []
            self.voltageSignals = []
            self.doublePulseTaus = []
        # provide information necessary for Panel Display
        self.putQueue(self.voltageSignalQueue, [pulseVoltages[c][0] for c in range(self.nChannels)])

        return True

    def close(self):
        if self.logPulses:
            if self.pulseFilterLog:
                print("# PulseProcessor Summary: last evNR %i, Nval, Nacc, Nacc2, Nacc3: %i, %i, %i, %i" % (
                    self.eventCount,
                    self.validCount,
                    self.coincidenceCount,
                    self.doubleCoincidenceCount,
                    self.tripleCoincidenceCount
                ), file=self.pulseFilterLog)
                self.pulseFilterLog.close()
            if self.doublePulseFilterLog:
                print("# PulseProcessor Summary: last evNR %i, Nval, Nacc, Nacc2, Nacc3: %i, %i, %i, %i" % (
                    self.eventCount,
                    self.validCount,
                    self.coincidenceCount,
                    self.doubleCoincidenceCount,
                    self.tripleCoincidenceCount
                ), file=self.doublePulseFilterLog)
                print("#                      %i double pulses" % self.doublePulseCount, file=self.doublePulseFilterLog)
                self.doublePulseFilterLog.close()

    def validateTriggerPulse(self, eventData):
        offset = max(0, self.triggerSampleIndex - int(self.tauRise / self.dT) - self.sampleOffset)
        cort = np.correlate(
            eventData[self.triggerChannel, 0:self.triggerSampleIndex + self.sampleOffset + self.referencePulseLength],
            self.referencePulse, mode='valid')
        cort[cort < self.pulseThreshold] = self.pulseThreshold  # set all values below threshold to threshold
        firstPeak = np.argmax(cort) + offset  # index of 1st maximum
        print("firstPeak: %i offset: %i" % (firstPeak, offset))
        if firstPeak > self.triggerSampleIndex + (self.tauRise + self.tauOn) / self.dT + self.sampleOffset:
            self.displayPulse(0, eventData[self.triggerChannel,
                              0:self.triggerSampleIndex + self.sampleOffset + self.referencePulseLength])

            return False, None, 0.  # - while # no pulse near trigger, skip rest of event analysis
        # check pulse shape by requesting match with time-averaged pulse
        eventDataFirstPulse = eventData[self.triggerChannel, firstPeak:firstPeak + self.referencePulseLength]
        if np.sum((eventDataFirstPulse - eventDataFirstPulse.mean()) * self.zeroNormalizedReferencePulse) \
                > self.zeroNormalizedPulseThreshold:
            self.displayPulse(2, eventData[self.triggerChannel, firstPeak:firstPeak + self.referencePulseLength])

            return True, firstPeak, max(abs(eventDataFirstPulse))
        else:
            self.displayPulse(1, eventData[self.triggerChannel, firstPeak:firstPeak + self.referencePulseLength])

            return False, None, max(abs(eventDataFirstPulse))  # - while # skip rest of event analysis

    def findCoincidences(self, eventData, peak):
        coincidenceCount = 1
        coincidenceTimes = [0. for i in range(self.nChannels)]
        coincidenceVoltages = [0. for i in range(self.nChannels)]
        for channel in range(self.nChannels):
            if channel != self.triggerChannel:
                # search around trigger pulse
                offset = max(0, peak - self.sampleOffset)
                # analyse channel to find pulse near trigger
                correlation = np.correlate(
                    eventData[channel, offset:self.triggerSampleIndex + self.sampleOffset + self.referencePulseLength],
                    self.referencePulse, mode='valid')
                correlation[correlation < self.pulseThreshold] = self.pulseThreshold
                coincidencePeak = np.argmax(correlation) + offset
                if coincidencePeak > self.triggerSampleIndex + (self.tauRise + self.tauOn) / self.dT + self.sampleOffset:
                    continue
                coincidenceEventData = eventData[channel, coincidencePeak:coincidencePeak + self.referencePulseLength]
                if np.sum((coincidenceEventData - coincidenceEventData.mean()) * self.zeroNormalizedReferencePulse) \
                        > self.zeroNormalizedPulseThreshold:
                    coincidenceCount += 1
                    self.bufferManager.prlog("PulseProcessor: Coincidence in channel %i" % (channel))
                    coincidenceVoltages[channel] = max(abs(coincidenceEventData))
                    coincidenceTimes[channel] = coincidencePeak * self.dT * 1E6

        return coincidenceCount, coincidenceVoltages, coincidenceTimes

    def findDoublePulses(self, eventData, peak):
        offset = peak + self.referencePulseLength
        doublePulseCount = [0 for i in range(self.nChannels)]
        doublePulseVoltages = [[] for i in range(self.nChannels)]
        doublePulseTimes = [[] for i in range(self.nChannels)]
        for channel in range(self.nChannels):
            correlation = np.correlate(eventData[channel, offset:], self.referencePulse, mode='valid')
            correlation[correlation < self.pulseThreshold] = self.pulseThreshold
            for pulseIndex in (argrelmax(correlation)[0] + offset):
                pulseEventData = eventData[channel, pulseIndex:pulseIndex + self.referencePulseLength]
                if np.sum((pulseEventData - pulseEventData.mean()) * self.zeroNormalizedReferencePulse) \
                        > self.zeroNormalizedPulseThreshold:
                    doublePulseCount[channel] += 1
                    doublePulseVoltages[channel].append(max(abs(pulseEventData)))
                    doublePulseTimes[channel].append(pulseIndex * self.dT * 1E6)

        return doublePulseCount, doublePulseVoltages, doublePulseTimes
