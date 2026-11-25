"""Tensela: parametric design an architect understands."""

import os

__version__ = "0.9.3"

# AppRun may add libraries for systems that lack them (usr/lib/fallback of the AppImage). This process already has
# them (the loader reads LD_LIBRARY_PATH when it starts); the programs Tensela opens get back the path they would
# have had.
if "TENSELA_HOST_LIBRARY_PATH" in os.environ:
    _host = os.environ.pop("TENSELA_HOST_LIBRARY_PATH")
    if _host:
        os.environ["LD_LIBRARY_PATH"] = _host
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)

