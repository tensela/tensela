"""The memory while computing (Linux): a cap on what the computation may reserve, so that a huge reservation fails at
once instead of filling the RAM until the system closes the program; and giving back to the system what was freed.

Used by the window and by the process that computes (calculator.py)."""
from __future__ import annotations

import sys


def return_memory() -> None:
    """On Linux, the memory already freed goes back to the system (glibc keeps it; with several threads, a lot)."""
    if sys.platform.startswith("linux"):
        try:
            import ctypes
            import gc
            gc.collect()                             # first, what was only held in cycles
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except (OSError, AttributeError):
            pass


def _from_proc(file: str, key: str) -> int:
    """A value in kB from /proc (MemAvailable of /proc/meminfo, VmSize of /proc/self/status); 0 if it is not there."""
    try:
        for line in open(file):
            if line.startswith(key + ":"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def memory_cap(put: bool) -> None:
    """On Linux, while computing: the program cannot reserve more than the computer's free memory (with a margin). A
    huge reservation fails at once («it does not fit in memory») instead of filling the RAM until the system closes the
    program."""
    if not sys.platform.startswith("linux"):
        return
    import resource
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    cap = hard
    if put:
        free, current = _from_proc("/proc/meminfo", "MemAvailable"), _from_proc("/proc/self/status", "VmSize")
        if free and current:
            cap = current + int(free * 0.6)
            if hard != resource.RLIM_INFINITY:
                cap = min(cap, hard)
    try:
        resource.setrlimit(resource.RLIMIT_AS, (cap, hard))
    except (ValueError, OSError):
        pass
