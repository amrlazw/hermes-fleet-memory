#!/usr/bin/env python3
"""
Setup script for hermes-fleet-memory.
Dual-mode: acts as standard packaging setup() when called by pip/build tools,
or launches fleet_wizard when executed directly by users or autonomous agents.
"""
import sys

from setuptools import setup

BUILD_COMMANDS = {
    "egg_info", "dist_info", "build", "build_ext", "build_py", "build_clib",
    "build_scripts", "bdist", "bdist_wheel", "bdist_egg", "install", "develop",
    "sdist", "clean", "--help", "-h", "--version"
}

if __name__ == "__main__":
    # If run directly by user or agent with wizard flags, dispatch to fleet_wizard
    if len(sys.argv) == 1 or (len(sys.argv) > 1 and sys.argv[1] not in BUILD_COMMANDS and not sys.argv[1].startswith("-b")):
        try:
            from fleet_wizard import main
            main()
        except ImportError:
            setup()
    else:
        setup()
