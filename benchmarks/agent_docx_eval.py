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

def agent_docx_eval():
    runner = BenchmarkRunner()
    session = runner.start_session("agent_docx_edit_eval")
    doc_path = "eval_test.docx"
    
    # Step 1: Create DOCX
    print("Agent: Creating document...")
    # Since we don't have a 'create' command specifically, we'll use docx_files directly or just touch it
    # Actually, docx_files.append creates it if it doesn't exist? No, it expects it.
    # We'll use python-docx to create an empty one first.
    from docx import Document
    Document().save(doc_path)
    
    # Step 2: Append text
    print("Agent: Appending text...")
    out, dur, size, status = run_dctl(["docx", "append", doc_path, "Hello from the Agent!"])
    runner.record_step(session, "docx append", dur, size, status)
    
    # Step 3: Add a heading
    print("Agent: Adding heading...")
    out, dur, size, status = run_dctl(["docx", "append", doc_path, "Technical Evaluation", "--style", "Heading 1"])
    runner.record_step(session, "docx append --style", dur, size, status)
    
    # Step 4: Read it back
    print("Agent: Reading document...")
    out, dur, size, status = run_dctl(["docx", "read", doc_path])
    runner.record_step(session, "docx read", dur, size, status)
    
    success = False
    try:
        data = json.loads(out)
        text = data["data"]["text"]
        print(f"Agent: Read text: {text}")
        if "Hello from the Agent!" in text and "Technical Evaluation" in text:
            success = True
    except:
        pass
        
    runner.finalize(session, success)

if __name__ == "__main__":
    agent_docx_eval()
