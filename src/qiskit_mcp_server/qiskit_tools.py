import os
import sys
import json
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

from mcp.server.fastmcp import FastMCP
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
from qiskit import QuantumCircuit, transpile
from qiskit.qasm2 import loads as qasm2_loads
from qiskit.providers.basic_provider import BasicProvider

# Global store for local jobs (since BasicSimulator is local)
local_jobs = {}

def get_service() -> Optional[QiskitRuntimeService]:
    """Helper to get authenticated QiskitRuntimeService."""
    token = os.environ.get("QISKIT_IBM_TOKEN")
    try:
        if token:
            print("Using token: ", token, file=sys.stderr)
            # channel='ibm_quantum' causes an error, must use 'ibm_quantum_platform' or 'ibm_cloud'
            # See https://github.com/Qiskit/qiskit-ibm-runtime/issues/1000
            return QiskitRuntimeService(channel="ibm_quantum_platform", token=token)
        # Try loading from saved account
        print("Loading default saved account", file=sys.stderr)
        return QiskitRuntimeService()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error initializing QiskitRuntimeService: {e}", file=sys.stderr)
        return None

def register_tools(mcp: FastMCP):
    """Register Qiskit tools with the MCP server."""
    
    @mcp.tool()
    def list_backends(min_qubits: int = 0, simulator: bool = False) -> List[Dict[str, Any]]:
        """
        List available quantum backends.
        """
        try:
            service = get_service()
            if service:
                backends = service.backends(min_num_qubits=min_qubits, simulator=simulator)
                
                if not backends and simulator:
                    print("Info: No remote simulators found, falling back to local.", file=sys.stderr)
                    return [{
                        "name": "basic_simulator",
                        "n_qubits": 24,
                        "simulator": True,
                        "status": "ACTIVE"
                    }]

                return [
                    {
                        "name": b.name,
                        "n_qubits": b.num_qubits,
                        "simulator": b.simulator,
                        "status": b.status().name
                    }
                    for b in backends
                ]
            else:
                # Fallback to local simulator
                return [{
                    "name": "basic_simulator",
                    "n_qubits": 24, # BasicSimulator usually supports many
                    "simulator": True,
                    "status": "ACTIVE"
                }]
        except Exception as e:
            return f"Error listing backends: {str(e)}"

    @mcp.tool()
    def run_circuit(qasm_code: str, backend_name: str = "ibmq_qasm_simulator", shots: int = 1024) -> str:
        """
        Run a quantum circuit defined in OpenQASM 2.0.
        """
        try:
            # Parse QASM
            circuit = qasm2_loads(qasm_code)
            
            service = get_service()
            
            if service:
                try:
                    backend = service.backend(backend_name)
                    # Transpile for backend
                    transpiled_circuit = transpile(circuit, backend)
                    
                    # Run using Sampler primitive (V2)
                    sampler = Sampler(backend=backend)
                    job = sampler.run([transpiled_circuit], shots=shots)
                    return f"Job submitted. Job ID: {job.job_id()}"
                except Exception as e:
                    print(f"Warning: Could not use remote backend '{backend_name}': {e}. Falling back to local.", file=sys.stderr)
                    # Fallthrough to local fallback
            
            # Local fallback (if service None or backend creation failed)
                # Local fallback
                backend = BasicProvider().get_backend('basic_simulator')
                transpiled_circuit = transpile(circuit, backend)
                job = backend.run(transpiled_circuit, shots=shots)
                local_jobs[job.job_id()] = job
                return f"Job submitted. Job ID: {job.job_id()}"
                
        except Exception as e:
            return f"Error running circuit: {str(e)}"

    @mcp.tool()
    def get_job_status(job_id: str) -> str:
        """
        Check the status of a job.
        """
        try:
            if job_id in local_jobs:
                job = local_jobs[job_id]
                # BasicSimulator jobs are usually done immediately
                status = job.status().name
                return f"Job Status: {status}"
            
            service = get_service()
            if service:
                job = service.job(job_id)
                return f"Job Status: {job.status()}"
            return "Job not found (no service and not local)"
        except Exception as e:
            return f"Error getting job status: {str(e)}"

    @mcp.tool()
    def get_job_result(job_id: str) -> str:
        """
        Get the result of a completed job.
        """
        try:
            output_data = []
            
            if job_id in local_jobs:
                job = local_jobs[job_id]
                result = job.result()
                # BasicSimulator result
                # It has get_counts()
                counts = result.get_counts()
                output_data.append({"counts": counts})
                return json.dumps(output_data)

            service = get_service()
            if service:
                job = service.job(job_id)
                if not job.done():
                    return f"Job is not done yet. Status: {job.status()}"
                
                result = job.result()
                # SamplerV2 result structure
                for idx, pub_result in enumerate(result):
                    data_dict = {}
                    if hasattr(pub_result.data, 'meas'):
                         counts = pub_result.data.meas.get_counts()
                         data_dict['counts'] = counts
                    else:
                         data_dict['raw'] = str(pub_result.data)
                    output_data.append(data_dict)
                
                return json.dumps(output_data)
            
            return "Job not found"
        except Exception as e:
            return f"Error getting job result: {str(e)}"
