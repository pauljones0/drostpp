"""Module entrypoint for `python -m drostpp`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
