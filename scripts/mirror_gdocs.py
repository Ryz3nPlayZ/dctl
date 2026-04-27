import sys
import os
import time
import json
import subprocess

def run_dctl(args):
    cmd = [sys.executable, "-m", "dctl"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except:
        return {"status": "error", "raw": result.stdout}

def mirror_to_gdocs():
    session = "agent-docs"
    
    # Read the DOCX content
    print("Reading DOCX content...")
    docx_data = run_dctl(["docx", "read", "dctl_documentation.docx"])
    text = docx_data["data"]["text"]
    lines = text.split("\n")

    print("Waiting for Google Docs to settle...")
    time.sleep(8) # Long wait for docs.new to initialize

    # Google Docs shortcuts:
    # Ctrl+Alt+0: Normal text
    # Ctrl+Alt+1: Heading 1
    
    print("Typing document content...")
    for i, line in enumerate(lines):
        if not line.strip():
            continue
            
        # If it's the first line, make it a Title/H1
        if i == 0:
            run_dctl(["browser", "key", "Ctrl+Alt+1", "--session", session])
            run_dctl(["browser", "type", line, "--session", session])
            run_dctl(["browser", "key", "Enter", "--session", session])
        elif any(line.startswith(h) for h in ["Overview", "Key Features", "Architecture", "CLI Quick Start"]):
            run_dctl(["browser", "key", "Ctrl+Alt+1", "--session", session])
            run_dctl(["browser", "type", line, "--session", session])
            run_dctl(["browser", "key", "Enter", "--session", session])
            run_dctl(["browser", "key", "Ctrl+Alt+0", "--session", session]) # Back to normal
        else:
            run_dctl(["browser", "type", line, "--session", session])
            run_dctl(["browser", "key", "Enter", "--session", session])
            
    print("Mirroring complete.")

if __name__ == "__main__":
    mirror_to_gdocs()
