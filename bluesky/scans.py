from .run_engine import Msg
from .utils import Struct
import numpy as np


class Scan(Struct):
    """
    This is a base class for writing reusable scans.

    It provides a default entry in the logbook at the start of the scan and a
    __iter__ method.

    To create a new sub-class you need to over-ride two things:

    - a ``_gen`` method which yields the instructions of the scan.
    - optionally, a class level ``_fields`` attribute which is used to construct the init 
      signature via meta-class magic.


    If you do not use the class-level ``_fields`` and write a custom ``__init__`` (which you need
    to do if you want to have optional kwargs) you should provide an instance level ``_fields`` so
    that the logbook related messages will work.
    """
    def __iter__(self):
        yield Msg('logbook', None, self.logmsg(), **self.logdict())
        yield from self._gen()
            
    def logmsg(self):
        args = []
        for k in self._fields:
            args.append("{k}={{{k}!r}}".format(k=k))
        
        call_str = "RE({{scn_cls}}({args})".format(args=', '.join(args))

        msgs = ['Scan Class: {scn_cls}', '\n']
        for k in self._fields:
            msgs.append('{k}: {{{k}!r}}'.format(k=k))
        msgs.append('\n')
        msgs.append(call_str)
        return '\n'.join(msgs)

    def logdict(self):
        out_dict = {k: getattr(self, k) for k in self._fields}
        out_dict['scn_cls'] = self.__class__.__name__
        return out_dict

    def _gen(self):
        raise NotImplementedError("Scan is a base class, you must sub-class it and "
                                  "override this method (_gen)")

class Count(Scan):
    """
    Take one or more readings from the detectors. Do not move anything.

    Parameters
    ----------
    detectors : list
        list of 'readable' objects
    num : integer, optional
        number of readings to take; default is 1
    delay : float
        time delay between successive readings; default is 0

    Examples
    --------
    Count three detectors.

    >>> c = Count([det1, det2, det3])
    >>> RE(c)

    Count them five times with a one-second delay between readings.

    >>> c = Count([det1, det2, det3], 5, 1)
    >>> RE(c)
    """

    # This class does not actually use Struct because there are defaults.
    def __init__(self, detectors, num=1, delay=0):
        self.detectors = detectors
        self.num = num
        self.delay = delay

    def logdict(self):
        out = super().logdict()
        out['detectors'] = self.detectors
        out['num'] = self.num
        out['delay'] = self.delay
        return out

    def logmsg(self):
        base_msg = super().logmsg()
        msgs = [base_msg]
        msgs.append('detectors: {detectors!r}')
        msgs.append('num: {num}')
        msgs.append('delay: {delay}')
        return '\n'.join(msgs)

    def _gen(self):
        dets = self.detectors
        delay = self.delay
        for d in dets:
            yield Msg('configure', d)
        for i in range(self.num):
            yield Msg('checkpoint')
            yield Msg('create')
            for det in dets:
                yield Msg('trigger', det, block_group='A')
            for det in dets:
                yield Msg('wait', None, 'A')
            for det in dets:
                yield Msg('read', det)
            yield Msg('save')
            yield Msg('sleep', None, delay)
        for d in dets:
            yield Msg('deconfigure', d)


class Scan1D(Scan):
    _fields = ['motor', 'detectors', 'steps']

    def _gen(self):
        dets = self.detectors
        for d in dets:
            yield Msg('configure', d)
        for step in self._steps:
            yield Msg('checkpoint')
            yield Msg('set', self.motor, step, block_group='A')
            yield Msg('wait', None, 'A')
            yield Msg('create')
            yield Msg('read', self.motor)
            for det in dets:
                yield Msg('trigger', det, block_group='B')
            for det in dets:
                yield Msg('wait', None, 'B')
            for det in dets:
                yield Msg('read', det)
            yield Msg('save')
        for d in dets:
            yield Msg('deconfigure', d)


class Ascan(Scan1D):
    """
    Absolute scan over one variable in user-specified steps

    Parameters
    ----------
    motor : object
        any 'setable' object (motor, temp controller, etc.)
    detectors : list
        list of 'readable' objects
    steps : list
        list of positions
    """
    def _gen(self):
        self._steps = self.steps
        yield from super()._gen()


class Dscan(Scan1D):
    """
    Delta (relative) scan over one variable in user-specified steps

    Parameters
    ----------
    motor : object
        any 'setable' object (motor, temp controller, etc.)
    detectors : list
        list of 'readable' objects
    steps : list
        list of positions relative to current position
    """
    def _gen(self):
        ret = yield Msg('read', self.motor)
        if len(ret.keys()) > 1:
            raise NotImplementedError("Can't DScan this motor")
        key, = ret.keys()
        current_value = ret[key]['value']
        self._steps = self.steps + current_value
        yield from super()._gen()


class LinAscan(Scan1D):
    """
    Absolute scan over one variable in equally spaced steps

    Parameters
    ----------
    motor : object
        any 'setable' object (motor, temp controller, etc.)
    detectors : list
        list of 'readable' objects
    start : float
        starting position of motor
    stop : float
        ending position of motor
    num : int
        number of steps

    Examples
    --------
    Scan motor1 from 0 to 1 in ten steps.

    >>> my_scan = LinAscan(motor1, [det1, det2], 0, 1, 10)
    >>> RE(my_scan)
    # Adjust a Parameter and run again.
    >>> my_scan.num = 100
    >>> RE(my_scan)
    """
    _fields = ['motor', 'detectors', 'start', 'stop', 'num']

    def _gen(self):
        self._steps = np.linspace(self.start, self.stop, self.num)
        yield from super()._gen()


class LogAscan(Scan1D):
    """
    Absolute scan over one variable in log-spaced steps

    Parameters
    ----------
    motor : object
        any 'setable' object (motor, temp controller, etc.)
    detectors : list
        list of 'readable' objects
    start : float
        starting position of motor
    stop : float
        ending position of motor
    num : int
        number of steps

    Examples
    --------
    Scan motor1 from 0 to 10 in ten log-spaced steps.

    >>> my_scan = LogAscan(motor1, [det1, det2], 0, 1, 10)
    >>> RE(my_scan)
    # Adjust a Parameter and run again.
    >>> my_scan.num = 100
    >>> RE(my_scan)
    """
    _fields = ['motor', 'detectors', 'start', 'stop', 'num']

    def _gen(self):
        self._steps = np.logspace(self.start, self.stop, self.num)
        yield from super()._gen()


class LinDscan(Dscan):
    """
    Delta (relative) scan over one variable in equally spaced steps

    Parameters
    ----------
    motor : object
        any 'setable' object (motor, temp controller, etc.)
    detectors : list
        list of 'readable' objects
    start : float
        starting position of motor
    stop : float
        ending position of motor
    num : int
        number of steps

    Examples
    --------
    Scan motor1 from 0 to 1 in ten steps.

    >>> my_scan = LinDscan(motor1, [det1, det2], 0, 1, 10)
    >>> RE(my_scan)
    # Adjust a Parameter and run again.
    >>> my_scan.num = 100
    >>> RE(my_scan)
    """
    _fields = ['motor', 'detectors', 'start', 'stop', 'num']

    def _gen(self):
        self.steps = np.linspace(self.start, self.stop, self.num)
        yield from super()._gen()


class LogDscan(Dscan):
    """
    Delta (relative) scan over one variable in log-spaced steps

    Parameters
    ----------
    motor : object
        any 'setable' object (motor, temp controller, etc.)
    detectors : list
        list of 'readable' objects
    start : float
        starting position of motor
    stop : float
        ending position of motor
    num : int
        number of steps

    Examples
    --------
    Scan motor1 from 0 to 10 in ten log-spaced steps.

    >>> my_scan = LogDscan(motor1, [det1, det2], 0, 1, 10)
    >>> RE(my_scan)
    # Adjust a Parameter and run again.
    >>> my_scan.num = 100
    >>> RE(my_scan)
    """
    _fields = ['motor', 'detectors', 'start', 'stop', 'num']

    def _gen(self):
        self.steps = np.logspace(self.start, self.stop, self.num)
        yield from super()._gen()


class _AdaptiveScan(Scan1D):
    _fields = ['motor', 'detectors', 'target_field', 'start', 'stop',
               'min_step', 'max_step', 'target_delta']
    THRESHOLD = 0.8  # threshold for going backward and rescanning a region.

    def _gen(self):
        start = self.start + self._offset
        stop = self.stop + self._offset
        next_pos = start
        step = (self.max_step - self.min_step) / 2

        past_I = None
        cur_I = None
        cur_det = {}
        motor = self.motor
        dets = self.detectors
        target_field = self.target_field
        for d in dets:
            yield Msg('configure', d)
        while next_pos < stop:
            yield Msg('checkpoint')
            yield Msg('set', motor, next_pos)
            yield Msg('wait', None, 'A')
            yield Msg('create')
            yield Msg('read', motor)
            for det in dets:
                yield Msg('trigger', det, block_group='B')
            for det in dets:
                yield Msg('wait', None, 'B')
            for det in dets:
                cur_det = yield Msg('read', det)
                if target_field in cur_det:
                    cur_I = cur_det[target_field]['value']
            yield Msg('save')

            # special case first first loop
            if past_I is None:
                past_I = cur_I
                next_pos += step
                continue

            dI = np.abs(cur_I - past_I)

            slope = dI / step
            if slope:
                new_step = np.clip(self.target_delta / slope, self.min_step,
                                   self.max_step)
            else:
                new_step = np.min([step * 1.1, self.max_step])

            # if we over stepped, go back and try again
            if new_step < step * self.THRESHOLD:
                next_pos -= step
                step = new_step
            else:
                past_I = cur_I
                step = 0.2 * new_step + 0.8 * step
            next_pos += step
        for d in dets:
            yield Msg('deconfigure', d)


class AdaptiveAscan(_AdaptiveScan):
    """
    Absolute scan over one variable with adaptively tuned step size

    Parameters
    ----------
    motor : object
        any 'setable' object (motor, temp controller, etc.)
    detectors : list
        list of 'readable' objects
    target_field : string
        data field whose output is the focus of the adaptive tuning
    start : float
        starting position of motor
    stop : float
        ending position of motor
    min_step : float
        smallest step for fast-changing regions
    max_step : float
        largest step for slow-chaning regions
    target_delta : float
        desired fractional change in detector signal between steps
    """
    def _gen(self):
        self._offset = 0
        yield from super()._gen()


class AdaptiveDscan(_AdaptiveScan):
    """
    Delta (relative) scan over one variable with adaptively tuned step size

    Parameters
    ----------
    motor : object
        any 'setable' object (motor, temp controller, etc.)
    detectors : list
        list of 'readable' objects
    target_detector : obj
        detector whose output is the focus of the adaptive tuning
    start : float
        starting position of motor
    stop : float
        ending position of motor
    min_step : float
        smallest step for fast-changing regions
    max_step : float
        largest step for slow-chaning regions
    target_delta : float
        desired fractional change in detector signal between steps
    """
    def _gen(self):
        ret = yield Msg('read', self.motor)
        if len(ret.keys()) > 1:
            raise NotImplementedError("Can't DScan this motor")
        key, = ret.keys()
        current_value = ret[key]['value']
        self._offset = current_value
        yield from super()._gen()
