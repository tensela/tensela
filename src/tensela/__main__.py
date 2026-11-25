"""`python -m tensela project.tela`: the same as the `tensela` command, in the language of the computer."""

import sys

from .cli import run

sys.exit(run())
