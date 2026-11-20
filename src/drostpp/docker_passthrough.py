"""Restore the coordinator Docker endpoint for an explicitly trusted integration command."""

from __future__ import annotations

import os
import sys


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write("docker passthrough requires a command\n")
        return 2
    env = dict(os.environ)
    if "DROSTPP_REAL_DOCKER_HOST" in env:
        real_host = env.pop("DROSTPP_REAL_DOCKER_HOST")
        if real_host:
            env["DOCKER_HOST"] = real_host
        else:
            env.pop("DOCKER_HOST", None)
    os.execvpe(sys.argv[1], sys.argv[1:], env)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
