"""
DevOps Butler — Main Application Entry Point
Run: python app.py [serve|deploy|analyze]
"""

import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cli.main import main

if __name__ == "__main__":
    main()
