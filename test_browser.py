"""
Quick test script for browser automation
Run: python test_browser.py
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.browser_agent.browser_client import BrowserClient
from config.logging_config import setup_logging

async def test_browser():
    """Test browser automation with AWS Console login."""
    setup_logging("INFO")
    
    client = BrowserClient()
    
    print("🌐 Testing browser automation...")
    print("📋 Task: Login to AWS Console and navigate to EKS")
    
    result = await client.execute_task(
        task_description="Log into AWS Console. Navigate to EKS. List all clusters.",
        task_type="generic",
        trace_id="test-browser",
    )
    
    print(f"\n✅ Status: {result['status']}")
    print(f"📝 Actions: {result['actions_taken']}")
    if result.get('error'):
        print(f"❌ Error: {result['error']}")
    if result.get('result'):
        print(f"📊 Result: {result['result'][:200]}")

if __name__ == "__main__":
    asyncio.run(test_browser())
