import asyncio
import argparse
import json
import math
import random
from fractions import Fraction
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# QASM for Shor's algorithm (Period Finding)
# Note: Generating a full general Shor's circuit is complex. 
# For this example, we will implement the specific circuit for N=15, a=7 (a common example).
# This finds the period of f(x) = 7^x mod 15.
# The period should be 4.

def get_shor_circuit_qasm(n: int, a: int) -> str:
    """
    Returns the QASM string for Shor's algorithm specific to N=15, a=7.
    """
    import os
    qasm_path = "shor_15_7.qasm"
    if os.path.exists(qasm_path):
        with open(qasm_path, "r") as f:
            return f.read()
    else:
        # Fallback (old incorrect one, or raise error)
        # Raising error is better to ensure correctness
        raise FileNotFoundError(f"Generated QASM file {qasm_path} not found. Please run generate_shor_qasm.py first.")

def get_factors(n: int, phase: float) -> tuple[Optional[int], Optional[int]]:
    """
    Calculate factors from the phase.
    """
    if phase == 0:
        return None, None
        
    frac = Fraction(phase).limit_denominator(n)
    r = frac.denominator
    
    if r % 2 != 0:
        return None, None
        
    guess = int(math.pow(7, r/2)) # using a=7
    
    f1 = math.gcd(guess - 1, n)
    f2 = math.gcd(guess + 1, n)
    
    if f1 == 1 or f1 == n:
        return None, None
    if f2 == 1 or f2 == n:
        return None, None
        
    return f1, f2

async def run_shor_mcp(n: int = 15, a: int = 7):
    print(f"Running Shor's Algorithm for N={n}, a={a} via MCP...")
    
    # Start the MCP server as a subprocess
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "qiskit_mcp_server.main"],
        env=None # Inherit env (important for QISKIT_IBM_TOKEN)
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()
            
            # List backends to verify connection
            backends_result = await session.call_tool("list_backends", arguments={"simulator": True})
            # backends_result is a CallToolResult. content is a list of TextContent or ImageContent.
            # FastMCP tools return JSON string or direct text.
            # Let's inspect the first content item.
            if not backends_result.content:
                print("No content in list_backends response")
                return
            
            backends_text = backends_result.content[0].text
            try:
                backends = json.loads(backends_text)
                print(f"Available backends: {[b['name'] for b in backends]}")
            except (json.JSONDecodeError, TypeError):
                # It might be that the tool returned a python list directly if FastMCP handles it, 
                # but usually it's text over the wire. 
                # If it's already a list (unlikely over stdio without parsing), use it.
                # Actually, mcp python SDK might deserialize it?
                # Let's print raw text to be sure if it fails again, but json.loads is the safe bet for complex types.
                print(f"Raw backends response: {backends_text}")

            # Generate Circuit
            try:
                qasm = get_shor_circuit_qasm(n, a)
            except FileNotFoundError as e: # Changed ValueError to FileNotFoundError
                print(e)
                return

            # Run Circuit
            print("Submitting circuit...")
        
            try:
                import qiskit.qasm2
                qc = qiskit.qasm2.loads(qasm)
                print("\nCircuit Diagram:")
                print(qc.draw(output='text'))
                print("\n")
            except Exception as e:
                print(f"Could not visualize circuit: {e}")

            job_result = await session.call_tool("run_circuit", arguments={
                "qasm_code": qasm,
                "backend_name": "ibmq_qasm_simulator", # Or aer_simulator if local
                "shots": 1024
            })
            
            if not job_result.content:
                print("No content in run_circuit response")
                return
            job_response = job_result.content[0].text
            print(job_response)
            
            # Extract Job ID
            # Expected format: "Job submitted. Job ID: <id>"
            if "Job ID: " not in job_response:
                print("Failed to get Job ID")
                return
                
            job_id = job_response.split("Job ID: ")[1].strip()
            
            # Poll for results
            print(f"Waiting for job {job_id}...")
            while True:
                status_result = await session.call_tool("get_job_status", arguments={"job_id": job_id})
                status_response = status_result.content[0].text
                print(status_response)
                if "DONE" in status_response or "COMPLETED" in status_response: # Check exact status string
                    break
                if "ERROR" in status_result.content[0].text or "CANCELLED" in status_result.content[0].text:
                    print("Job failed or cancelled.")
                    return
                await asyncio.sleep(2)
            
            # Get Results
            result_tool_output = await session.call_tool("get_job_result", arguments={"job_id": job_id})
            result_json = result_tool_output.content[0].text
            try:
                results = json.loads(result_json)
                # We expect a list of results (one per pub), we took the first one
                if not results:
                    print("No results returned.")
                    return
                
                counts = results[0].get("counts", {})
                print(f"Counts: {counts}")
                
                # Analyze results (improved)
                # Sort by count descending
                sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
                
                print("\nAnalyzing top measurements to find factors:")
                found_factors = False
                
                # Check top 5 or fewer
                for bitstring, count in sorted_counts[:5]:
                    measured_int = int(bitstring, 2)
                    phase = measured_int / (2**4)
                    
                    print(f"  Measurement: {bitstring} (int: {measured_int}), Count: {count}, Phase: {phase}")
                    
                    if phase == 0:
                        print("    -> Phase 0.0 is trivial. Skipping.")
                        continue
                        
                    f1, f2 = get_factors(n, phase)
                    if f1 and f2:
                        print(f"    -> SUCCESS! Factors of {n} are {f1} and {f2}")
                        found_factors = True
                        break
                    else:
                         print("    -> Could not determine factors from this phase.")
                
                if not found_factors:
                    print("\nCould not determine factors from the significant measurements. Try running again.")
                    
            except json.JSONDecodeError:
                print(f"Failed to parse result JSON: {result_json}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shor's Algorithm via MCP")
    parser.add_argument("--number", type=int, default=15, help="Number to factor (default 15)")
    args = parser.parse_args()
    
    asyncio.run(run_shor_mcp(args.number))
