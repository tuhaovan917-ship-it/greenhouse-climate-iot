"""Console helper for the verification scripts.

The Windows console defaults to cp1252 and cannot print the Vietnamese alert
messages, so a script that prints a payload would crash with a
UnicodeEncodeError. Every script calls enableUtf8Console() before it prints.
"""

import sys


def enableUtf8Console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - old Python
            pass
