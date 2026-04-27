import json
import time
import os
from pathlib import Path
from typing import Any, Dict, List

class BenchmarkRunner:
    def __init__(self, output_dir: str = "benchmarks/reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.results = []

    def start_session(self, scenario_id: str):
        print(f"--- Starting Benchmark: {scenario_id} ---")
        return {
            "scenario": scenario_id,
            "start_time": time.time(),
            "steps": [],
            "total_bytes_received": 0,
            "errors": 0
        }

    def record_step(self, session: Dict, command: str, duration: float, response_size: int, status: str):
        step = {
            "index": len(session["steps"]),
            "command": command,
            "duration_ms": int(duration * 1000),
            "response_size_kb": round(response_size / 1024, 2),
            "status": status,
            "timestamp": time.time()
        }
        session["steps"].append(step)
        session["total_bytes_received"] += response_size
        if status == "error":
            session["errors"] += 1

    def finalize(self, session: Dict, success: bool, reason: str = ""):
        session["end_time"] = time.time()
        session["total_duration_sec"] = round(session["end_time"] - session["start_time"], 2)
        session["success"] = success
        session["failure_reason"] = reason
        
        # Calculate Efficiency Metrics
        step_count = len(session["steps"])
        session["metrics"] = {
            "avg_latency_ms": int(sum(s["duration_ms"] for s in session["steps"]) / step_count) if step_count else 0,
            "total_data_mb": round(session["total_bytes_received"] / (1024 * 1024), 2),
            "step_count": step_count,
            "compute_waste_score": self._calculate_waste(session)
        }
        
        report_path = self.output_dir / f"report_{session['scenario']}_{int(time.time())}.json"
        with open(report_path, "w") as f:
            json.dump(session, f, indent=2)
        
        print(f"Benchmark Finalized: {'SUCCESS' if success else 'FAILURE'}")
        print(f"Total Steps: {step_count} | Total Time: {session['total_duration_sec']}s")
        print(f"Report saved to: {report_path}")

    def _calculate_waste(self, session: Dict) -> float:
        # Heuristic: High data per step or high frequency of 'tree' calls suggests wasted compute
        tree_calls = len([s for s in session["steps"] if "tree" in s["command"]])
        large_responses = len([s for s in session["steps"] if s["response_size_kb"] > 500])
        return round((tree_calls * 0.5) + (large_responses * 0.3), 2)

if __name__ == "__main__":
    # Example usage for verification
    runner = BenchmarkRunner()
    sess = runner.start_session("legal_contract")
    runner.record_step(sess, "dctl list-windows", 0.1, 2048, "ok")
    runner.record_step(sess, "dctl tree --app Word", 1.2, 800000, "ok")
    runner.record_step(sess, "dctl click 'role:button AND name:Save'", 0.3, 1024, "ok")
    runner.finalize(sess, True)
