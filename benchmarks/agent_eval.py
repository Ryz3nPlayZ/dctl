import sys
import os
import time
import json
import subprocess
from benchmarks.runner import BenchmarkRunner

def run_dctl(args):
    start = time.time()
    cmd = [sys.executable, "-m", "dctl"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    duration = time.time() - start
    size = len(result.stdout)
    try:
        data = json.loads(result.stdout)
        status = data.get("status", "error")
    except:
        status = "error"
    return result.stdout, duration, size, status

def agent_self_eval():
    runner = BenchmarkRunner()
    session = runner.start_session("agent_web_search_eval")
    
    # Step 1: Start Browser
    print("Agent: Starting browser...")
    out, dur, size, status = run_dctl(["browser", "start", "--headless", "--session", "eval-session"])
    runner.record_step(session, "browser start", dur, size, status)
    
    # Step 2: Open Wikipedia
    print("Agent: Opening Wikipedia...")
    out, dur, size, status = run_dctl(["browser", "open", "https://en.wikipedia.org", "--session", "eval-session"])
    runner.record_step(session, "browser open", dur, size, status)
    
    # Step 3: Find Search Box (Wait for page load)
    time.sleep(2)
    print("Agent: Finding search box...")
    out, dur, size, status = run_dctl(["tree", "--app", "brave", "--role", "entry"])
    runner.record_step(session, "tree --role entry", dur, size, status)
    
    # Step 4: Type into Search
    print("Agent: Typing query...")
    # Based on Wikipedia's structure, we usually look for 'Search Wikipedia'
    out, dur, size, status = run_dctl(["type", "Antigravity", "--session", "eval-session"])
    runner.record_step(session, "type", dur, size, status)
    
    # Step 5: Press Enter
    print("Agent: Pressing Enter...")
    out, dur, size, status = run_dctl(["key", "Enter", "--session", "eval-session"])
    runner.record_step(session, "key Enter", dur, size, status)
    
    # Step 6: Verify Page
    time.sleep(2)
    print("Agent: Verifying result...")
    out, dur, size, status = run_dctl(["browser", "active-tab", "--session", "eval-session"])
    runner.record_step(session, "browser active-tab", dur, size, status)
    
    success = False
    try:
        data = json.loads(out)
        title = data["data"]["target"]["title"]
        print(f"Agent: Found page title: {title}")
        if "Antigravity" in title or "Search results" in title:
            success = True
    except:
        pass
        
    # Step 7: Cleanup
    run_dctl(["browser", "stop", "--session", "eval-session"])
    
    runner.finalize(session, success)

if __name__ == "__main__":
    agent_self_eval()
