#!/usr/bin/env python
"""
FileMind Launcher — Sets up PYTHONPATH and runs commands.
Usage: python launch.py [command] [args]
"""
import sys
import os

# Ensure the filemind package directory is on the path
FM_DIR = os.path.dirname(os.path.abspath(__file__))
if FM_DIR not in sys.path:
    sys.path.insert(0, FM_DIR)

# Set environment variable so child processes know
os.environ['PYTHONPATH'] = FM_DIR

from run import main
main()