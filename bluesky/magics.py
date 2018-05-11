# These are experimental IPython magics, providing quick shortcuts for simple
# tasks. None of these save any data.

# To use, run this in an IPython shell:
# ip = get_ipython()
# ip.register_magics(BlueskyMagics)

import asyncio
import warnings
from bluesky.utils import ProgressBarManager
from bluesky import RunEngine, RunEngineInterrupted
from IPython.core.magic import Magics, magics_class, line_magic
from traitlets import MetaHasTraits
import numpy as np
import collections
from operator import attrgetter
from . import plans as bp
from . import plan_stubs as bps

try:
    # cytools is a drop-in replacement for toolz, implemented in Cython
    from cytools import partition
except ImportError:
    from toolz import partition

# This is temporarily here to allow for warnings to be printed
# we changed positioners to a property but since we never instantiate
# the class we need to add this
class MetaclassForClassProperties(MetaHasTraits, type):
    @property
    def positioners(self):
        if self._positioners:
            warnings.warn("BlueskyMagics.positioners is deprecated. "
                          "Please use the newer labels feature.")
        return self._positioners

    @positioners.setter
    def positioners(self, val):
        warnings.warn("BlueskyMagics.positioners is deprecated. "
                      "Please use the newer labels feature.")
        self._positioners = val

    @property
    def detectors(self):
        if self._detectors:
            warnings.warn("BlueskyMagics.detectors is deprecated. "
                          "Please use the newer labels feature.")
        return self._detectors

    @detectors.setter
    def detectors(self, val):
        warnings.warn("BlueskyMagics.detectors is deprecated. "
                      "Please use the newer labels feature.")
        self._detectors = val

    _positioners = []
    _detectors = []

@magics_class
class BlueskyMagics(Magics, metaclass=MetaclassForClassProperties):
    """
    IPython magics for bluesky.

    To install:

    >>> ip = get_ipython()
    >>> ip.register_magics(BlueskyMagics)

    Optionally configure default detectors and positioners by setting
    the class attributes:

    * ``BlueskyMagics.detectors``
    * ``BlueskyMagics.positioners``

    For more advanced configuration, access the magic's RunEngine instance and
    ProgressBarManager instance:

    * ``BlueskyMagics.RE``
    * ``BlueskyMagics.pbar_manager``
    """
    RE = RunEngine({}, loop=asyncio.new_event_loop())
    pbar_manager = ProgressBarManager()

    def _ensure_idle(self):
        if self.RE.state != 'idle':
            print('The RunEngine invoked by magics cannot be resumed.')
            print('Aborting...')
            self.RE.abort()

    @line_magic
    def mov(self, line):
        if len(line.split()) % 2 != 0:
            raise TypeError("Wrong parameters. Expected: "
                            "%mov motor position (or several pairs like that)")
        args = []
        for motor, pos in partition(2, line.split()):
            args.append(eval(motor, self.shell.user_ns))
            args.append(eval(pos, self.shell.user_ns))
        plan = bps.mv(*args)
        self.RE.waiting_hook = self.pbar_manager
        try:
            self.RE(plan)
        except RunEngineInterrupted:
            ...
        self.RE.waiting_hook = None
        self._ensure_idle()
        return None

    @line_magic
    def movr(self, line):
        if len(line.split()) % 2 != 0:
            raise TypeError("Wrong parameters. Expected: "
                            "%mov motor position (or several pairs like that)")
        args = []
        for motor, pos in partition(2, line.split()):
            args.append(eval(motor, self.shell.user_ns))
            args.append(eval(pos, self.shell.user_ns))
        plan = bps.mvr(*args)
        self.RE.waiting_hook = self.pbar_manager
        try:
            self.RE(plan)
        except RunEngineInterrupted:
            ...
        self.RE.waiting_hook = None
        self._ensure_idle()
        return None


    @line_magic
    def ct(self, line):
        # If the deprecated BlueskyMagics.detectors list is non-empty, it has
        # been configured by the user, and we must revert to the old behavior.
        if type(self).detectors:
            if line.strip():
                dets = eval(line, self.shell.user_ns)
            else:
                dets = type(self).detectors
        else:
            # new behaviour
            devices_dict = get_labeled_devices(user_ns=self.shell.user_ns)
            if line.strip():
                # User has provided a white list of labels like
                # %ct label1 label2
                labels = line.strip().split()
            else:
                labels = ['detectors']
            dets = []
            for label in labels:
                dets.extend(obj for _, obj in devices_dict.get(label, []))
        plan = bp.count(dets)
        print("[This data will not be saved. "
              "Use the RunEngine to collect data.]")
        try:
            self.RE(plan, _ct_callback)
        except RunEngineInterrupted:
            ...
        self._ensure_idle()
        return None


    FMT_PREC = 6


    @line_magic
    def wa(self, line):
        "List positioner info. 'wa' stands for 'where all'."
        # If the deprecated BlueskyMagics.positioners list is non-empty, it has
        # been configured by the user, and we must revert to the old behavior.
        if type(self).positioners:
            if line.strip():
                positioners = eval(line, self.shell.user_ns)
            else:
                positioners = type(self).positioners
            if len(positioners) > 0:
                _print_positioners(positioners, precision=self.FMT_PREC)
        else:
            # new behaviour
            devices_dict = get_labeled_devices(user_ns=self.shell.user_ns)
            if line.strip():
                # User has provided a white list of labels like
                # %wa label1 label2
                labels = line.strip().split()
            else:
                # Show all labels.
                labels = list(devices_dict.keys())
            for label in labels:
                print(label)
                try:
                    devices = devices_dict[label]
                except KeyError:
                    print('<no matches for this label>')
                    continue
                # ignore the first key
                if are_positioners(devices):
                    positioners = [positioner[1] for positioner in devices_dict[label]]
                    _print_positioners(positioners, precision=self.FMT_PREC,
                                       prefix=" "*8)
                else:
                    _print_devices(devices, prefix=" "*8)

def _print_devices(devices, prefix=""):
    cols = ["Python name", "Ophyd Name"]
    print(prefix + "{:20s} \t {:20s}".format(*cols))
    print(prefix + "="*40)
    for name, obj in devices:
        print(prefix + "{:20s} \t {:20s}".format(name, str(obj.name)))

def are_positioners(devs):
    # only true if all are positioners
    # takes ((name, dev),...) tuple
    return all(is_positioner(obj) for _, obj in devs)

def is_positioner(dev):
    return hasattr(dev, 'position')

def _print_positioners(positioners, sort=True, precision=6, prefix=""):
    '''
        This will take a list of positioners and try to print them.

        Parameters
        ----------
        positioners : list
            list of positioners

        sort : bool, optional
            whether or not to sort the list

        precision: int, optional
            The precision to use for numbers
    '''
    # sort first
    if sort:
        positioners = sorted(set(positioners), key=attrgetter('name'))

    values = []
    for p in positioners:
        try:
            values.append(p.position)
        except Exception as exc:
            values.append(exc)

    headers = ['Positioner', 'Value', 'Low Limit', 'High Limit', 'Offset']
    LINE_FMT = prefix + '{: <30} {: <11} {: <11} {: <11} {: <11}'
    lines = []
    lines.append(LINE_FMT.format(*headers))
    for p, v in zip(positioners, values):
        if not isinstance(v, Exception):
            try:
                prec = p.precision
            except Exception:
                prec = precision
            value = np.round(v, decimals=prec)
            try:
                low_limit, high_limit = p.limits
            except Exception as exc:
                low_limit = high_limit = exc.__class__.__name__
            else:
                low_limit = np.round(low_limit, decimals=prec)
                high_limit = np.round(high_limit, decimals=prec)
            try:
                offset = p.user_offset.get()
            except Exception as exc:
                offset = exc.__class__.__name__
            else:
                offset = np.round(offset, decimals=prec)
        else:
            value = v.__class__.__name__  # e.g. 'DisconnectedError'
            low_limit = high_limit = offset = ''

        lines.append(LINE_FMT.format(p.name, value, low_limit, high_limit,
                                     offset))
    print('\n'.join(lines))


def get_labeled_devices(user_ns=None, maxdepth=6):
    ''' Returns dict of labels mapped to devices with that label

        Parameters
        ----------
        user_ns : dict, optional
            The namespace to search on
            Default is to grab the namespace of the ipython shell.

        maxdepth: int, optional
            max recursion depth

        Returns
        -------
            A dictionary of (name, ophydobject) tuple indexed by device label.

        Examples
        --------
        Read devices labeled as motors:
            objs = get_labeled_devices()
            my_motors = objs['motors']
    '''
    # could be set but lists are more common for users
    obj_list = collections.defaultdict(list)

    if maxdepth <= 0:
        warnings.warn("Recursion limit exceeded")
        return obj_list

    if user_ns is None:
        user_ns = get_ipython().user_ns

    for key, obj in user_ns.items():
        # ignore objects beginning with "_"
        # (mainly for ipython stored objs from command line
        # return of commands)
        # also check its a subclass of desired classes
        if not key.startswith("_"):
            if is_parent(obj):
                labels = getattr(obj, '_ophyd_labels_', set())
                obj_list.update(get_labeled_devices(user_ns=obj.__dict__,
                                                    maxdepth=maxdepth-1,))
            else:
                if hasattr(obj, '_ophyd_labels_'):
                    # don't inherit parent labels
                    labels = obj._ophyd_labels_
                    for label in labels:
                        obj_list[label].append((key, obj))

    # Convert from defaultdict to normal dict before returning.
    return dict(obj_list)


def is_parent(dev):
    # return whether a node is a parent
    # should not have component_names, or if yes, should be empty
    # read_attrs needed to check it's an instance and not class itself
    return (isinstance(dev, type) and
            len(getattr(dev, 'component_names', [])) > 0)


def get_children(dev):
    children = list()
    if hasattr(dev, 'component_names') and len(dev.component_names) > 0:
        for comp_name in dev.component_names:
            children.append(getattr(dev, comp_name))
    return children


def _ct_callback(name, doc):
    if name != 'event':
        return
    for k, v in doc['data'].items():
        print('{: <30} {}'.format(k, v))
