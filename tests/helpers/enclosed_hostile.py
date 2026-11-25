"""Starts like the helper of the Code nodes, closes itself in, and then runs hostile Python with everything of Python
at hand (as if some code had got past the check): what happens to each attempt? Used by test_code_helper.py.

    python -I enclosed_hostile.py <folder of tensela> <a file that must survive>
"""
import json
import os
import sys

sys.path.insert(0, sys.argv[1])
import numpy as np
from tensela import code_worker
from tensela.code_run import run
from tensela.data import Data
import ctypes  # loaded before, as numpy does: the worst case
out = os.fdopen(os.dup(1), "w")
target = sys.argv[2]
run("result = [point(i, 0) for i in range(3)]", {})
loaded = sorted(n for n in sys.modules if n.split(".")[0] in code_worker._NOT_IN_THE_HELPER)
put = code_worker._enclose()
still = sorted(n for n in sys.modules if n.split(".")[0] in code_worker._NOT_IN_THE_HELPER)
HOSTILE = {
 "read a file": "open('/etc/hostname').read()",
 "write a file": f"open({target!r}, 'w').write('x')",
 "os.open": f"__import__('os').open({target!r}, 64 | 1)",
 "list a folder": "os.listdir('/')",
 "remove": f"os.remove({target!r})",
 "mkdir": f"os.mkdir({target!r} + '.d')",
 "rename": f"os.rename({target!r}, {target!r} + '.2')",
 "system": "os.system('true')",
 "fork": "os.fork()",
 "exec": "os.execv('/bin/true', ['true'])",
 "spawn": "os.posix_spawn('/bin/true', ['true'], {})",
 "kill the parent": "os.kill(os.getppid(), 0)",
 "import socket": "import socket",
 "import subprocess": "import subprocess",
 "import _posixsubprocess": "import _posixsubprocess",
 "ctypes dlopen": "ctypes.CDLL(None)",
 "ctypes pythonapi": "ctypes.pythonapi.PyRun_SimpleString(b'x = 1')",
 "ctypes memory": "ctypes.string_at(id(1), 8)",
 "gc objects": "sys.modules['gc'].get_objects()" if 'gc' in sys.modules else "import gc",
 "frames": "sys._getframe()",
 "trace": "sys.settrace(lambda *a: None)",
 "raise the limit": "resource = sys.modules.get('resource'); resource.setrlimit(resource.RLIMIT_AS, (2**40, 2**40))",
 "numpy load": "np.load('/etc/hostname')",
 "numpy save": f"np.save({target!r}, np.zeros(3))",
 "numpy fromfile": "np.fromfile('/etc/hostname')",
 "numpy memmap": "np.memmap('/etc/hostname')",
 "a huge list": "x = [0] * 10 ** 10",
 "a new hook": "sys.addaudithook(lambda *a: None)",
 "plain computing": "x = sum(i * i for i in range(1000)); y = np.arange(10).sum(); compile('1+1', 'c', 'eval')",
}
results = {}
for what, code in HOSTILE.items():
    try:
        exec(code, {"os": os, "sys": sys, "ctypes": ctypes, "np": np, "__builtins__": __builtins__})
        results[what] = "RAN"
    except BaseException as error:
        results[what] = f"{type(error).__name__}: {str(error)[:50]}"
out.write(json.dumps({"put": put, "loaded": loaded, "still": still, "results": results}))
out.flush()
os._exit(0)
