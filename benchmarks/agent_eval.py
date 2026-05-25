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

    # Step 3: Snapshot page to understand structure
    print("Agent: Snapshotting page...")
    out, dur, size, status = run_dctl(["browser", "wait-selector", "active", "#searchInput", "--session", "eval-session", "--timeout", "10"])
    runner.record_step(session, "browser wait-selector #searchInput", dur, size, status)

    # Step 4: Type into search via browser CDP
    print("Agent: Typing query...")
    out, dur, size, status = run_dctl(["browser", "type", "active", "Antigravity", "--selector", "#searchInput", "--clear", "--session", "eval-session"])
    runner.record_step(session, "browser type search", dur, size, status)

    # Step 5: Press Enter via browser CDP
    print("Agent: Pressing Enter...")
    out, dur, size, status = run_dctl(["browser", "press", "active", "Enter", "--session", "eval-session"])
    runner.record_step(session, "browser press Enter", dur, size, status)

    # Step 6: Wait for navigation and verify page
    print("Agent: Waiting for results...")
    out, dur, size, status = run_dctl(["browser", "wait-url", "active", "Antigravity", "--session", "eval-session", "--timeout", "10"])
    runner.record_step(session, "browser wait-url Antigravity", dur, size, status)

    success = False
    try:
        data = json.loads(out)
        url = data.get("data", {}).get("url", "")
        print(f"Agent: Landed on: {url}")
        if "Antigravity" in url:
            success = True
    except:
        pass

    # Step 7: Cleanup
    run_dctl(["browser", "stop", "--session", "eval-session"])

    runner.finalize(session, success)

if __name__ == "__main__":
    agent_self_eval()
