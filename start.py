#!/usr/bin/env python3
"""
Simple startup script for DevOps Butler
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    from ui.server import start_server
    
    # Get port from environment (for cloud platforms)
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"Starting DevOps Butler on {host}:{port}")
    start_server(host=host, port=port)
