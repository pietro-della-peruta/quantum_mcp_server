"""
Shor's Algorithm Client via MCP.

Runs Shor's period-finding algorithm for supported N values (15, 21)
by communicating with a Qiskit MCP server. The QASM circuit is
auto-generated if not already cached on disk.

Usage:
    python shor_example.py <N> <a>
"""

import asyncio
import argparse
import json
import math
import os
from fractions import Fraction
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Import the counting-qubit function to stay in sync with the generator
from generate_shor_qasm import get_num_counting_qubits, SUPPORTED_N


def get_shor_circuit_qasm(n: int, a: int) -> str:
    """
    Load or auto-generate the QASM circuit for Shor's algorithm with (n, a).

    First looks for a cached file shor_{n}_{a}.qasm in the script directory.
    If not found, generates it using generate_shor_qasm.py.

    Args:
        n: the number to factorize
        a: the base for modular exponentiation
    Returns:
        The QASM string for the circuit
    """
    # Build path to the expected QASM file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    qasm_path = os.path.join(script_dir, f"shor_{n}_{a}.qasm")

    # If cached file exists, load it
    if os.path.exists(qasm_path):
        print(f"Loading cached QASM circuit from {qasm_path}")
        with open(qasm_path, "r") as f:
            return f.read()

    # Otherwise, generate the circuit dynamically
    print(f"No cached circuit found. Generating QASM for N={n}, a={a}...")
    from generate_shor_qasm import generate_and_save
    generate_and_save(n, a)

    # Now load the freshly generated file
    with open(qasm_path, "r") as f:
        return f.read()


def get_cf_convergent_denominators(numerator: int, denominator: int, max_denom: int) -> list[int]:
    """
    Compute all convergent denominators of the fraction numerator/denominator
    using the continued fraction expansion.

    The continued fraction method is the standard classical post-processing
    step in Shor's algorithm for extracting the period from the measured phase.

    Args:
        numerator: numerator of the phase fraction (measured integer)
        denominator: denominator (2^num_counting_qubits)
        max_denom: maximum denominator to consider (typically N)
    Returns:
        List of unique candidate denominators (potential periods) ≤ max_denom
    """
    p, q = numerator, denominator
    candidates = set()

    # Extract continued fraction terms [a0; a1, a2, ...]
    cf_terms = []
    while q > 0:
        cf_terms.append(p // q)
        p, q = q, p % q

    # Compute convergents h_k / k_k from CF terms
    # h_{-1} = 1, h_0 = a_0 ; k_{-1} = 0, k_0 = 1
    h_prev, h_curr = 1, cf_terms[0] if cf_terms else 0
    k_prev, k_curr = 0, 1

    # First convergent: a_0 / 1
    if 2 <= k_curr <= max_denom:
        candidates.add(k_curr)

    # Remaining convergents
    for i in range(1, len(cf_terms)):
        h_new = cf_terms[i] * h_curr + h_prev
        k_new = cf_terms[i] * k_curr + k_prev
        h_prev, h_curr = h_curr, h_new
        k_prev, k_curr = k_curr, k_new

        if 2 <= k_curr <= max_denom:
            candidates.add(k_curr)

    # Also try small multiples of each candidate (the true period
    # could be a multiple of a convergent denominator)
    base_candidates = list(candidates)
    for r in base_candidates:
        for mult in range(2, max_denom // r + 1):
            candidates.add(r * mult)

    return sorted(candidates)


def try_factor_with_period(n: int, a: int, r: int) -> tuple[Optional[int], Optional[int]]:
    """
    Attempt to extract factors of n given a candidate period r.

    Uses the identity: if a^r ≡ 1 (mod n) and r is even,
    then gcd(a^(r/2) ± 1, n) may yield non-trivial factors.

    Args:
        n: the number to factorize
        a: the base used in modular exponentiation
        r: candidate period to test
    Returns:
        (f1, f2) if non-trivial factors found, else (None, None)
    """
    # Period must be even for the factoring identity to work
    if r % 2 != 0:
        return None, None

    # Compute a^(r/2) mod n
    half_power = pow(a, r // 2, n)

    # If a^(r/2) ≡ -1 (mod n), factors are trivial — skip
    if half_power == n - 1:
        return None, None

    # Compute candidate factors
    f1 = math.gcd(half_power - 1, n)
    f2 = math.gcd(half_power + 1, n)

    # Check for non-trivial factors
    if 1 < f1 < n and 1 < f2 < n:
        return f1, f2

    return None, None


def get_factors(n: int, measured_int: int, num_counting_qubits: int, a: int) -> tuple[Optional[int], Optional[int]]:
    """
    Extract factors of n from a QPE measurement using continued fractions.

    Computes all convergents of the continued fraction expansion of
    measured_int / 2^num_counting_qubits, then tries each candidate
    period (and its multiples) to find non-trivial factors.

    Args:
        n: the number to factorize
        measured_int: the integer value from the QPE measurement
        num_counting_qubits: number of counting qubits used
        a: the base used in modular exponentiation
    Returns:
        (f1, f2) if factors found, else (None, None)
    """
    # Trivial measurement gives no information
    if measured_int == 0:
        return None, None

    # Get all candidate periods from the continued fraction convergents
    total_levels = 2 ** num_counting_qubits
    candidates = get_cf_convergent_denominators(measured_int, total_levels, n)

    # Try each candidate period
    for r in candidates:
        # Verify that a^r ≡ 1 (mod n) — confirms this is the actual period
        if pow(a, r, n) != 1:
            continue

        f1, f2 = try_factor_with_period(n, a, r)
        if f1 is not None:
            return f1, f2

    return None, None


async def run_shor_mcp(n: int, a: int):
    """
    Run Shor's algorithm for the given (n, a) pair via the MCP server.

    Connects to the Qiskit MCP server, submits the circuit, waits for
    results, and analyzes the measurements to extract factors.

    Args:
        n: the number to factorize
        a: the base for modular exponentiation
    """
    print(f"Running Shor's Algorithm for N={n}, a={a} via MCP...")

    # Determine number of counting qubits (must match the circuit)
    num_counting_qubits = get_num_counting_qubits(n)
    print(f"Using {num_counting_qubits} counting qubits ({2**num_counting_qubits} phase levels)")

    # Start the MCP server as a subprocess
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "qiskit_mcp_server.main"],
        env=None  # Inherit env (important for QISKIT_IBM_TOKEN)
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize session with the MCP server
            await session.initialize()

            # List backends to verify connection
            backends_result = await session.call_tool("list_backends", arguments={"simulator": True})
            if not backends_result.content:
                print("No content in list_backends response")
                return

            backends_text = backends_result.content[0].text
            try:
                backends = json.loads(backends_text)
                print(f"Available backends: {[b['name'] for b in backends]}")
            except (json.JSONDecodeError, TypeError):
                print(f"Raw backends response: {backends_text}")

            # Load or generate the QASM circuit
            try:
                qasm = get_shor_circuit_qasm(n, a)
            except (FileNotFoundError, ValueError) as e:
                print(f"Error: {e}")
                return

            # Visualize the circuit (optional, for debugging)
            print("Submitting circuit...")
            try:
                import qiskit.qasm2
                qc = qiskit.qasm2.loads(qasm)
                print("\nCircuit Diagram:")
                print(qc.draw(output='text'))
                print("\n")
            except Exception as e:
                print(f"Could not visualize circuit: {e}")

            # Submit the circuit to the backend
            job_result = await session.call_tool("run_circuit", arguments={
                "qasm_code": qasm,
                "backend_name": "ibmq_qasm_simulator",
                "shots": 2048
            })

            if not job_result.content:
                print("No content in run_circuit response")
                return
            job_response = job_result.content[0].text
            print(job_response)

            # Extract the Job ID from the response
            if "Job ID: " not in job_response:
                print("Failed to get Job ID")
                return

            job_id = job_response.split("Job ID: ")[1].strip()

            # Poll for job completion
            print(f"Waiting for job {job_id}...")
            while True:
                status_result = await session.call_tool("get_job_status", arguments={"job_id": job_id})
                status_response = status_result.content[0].text
                print(status_response)
                if "DONE" in status_response or "COMPLETED" in status_response:
                    break
                if "ERROR" in status_result.content[0].text or "CANCELLED" in status_result.content[0].text:
                    print("Job failed or cancelled.")
                    return
                await asyncio.sleep(2)

            # Retrieve and analyze results
            result_tool_output = await session.call_tool("get_job_result", arguments={"job_id": job_id})
            result_json = result_tool_output.content[0].text
            try:
                results = json.loads(result_json)
                if not results:
                    print("No results returned.")
                    return

                counts = results[0].get("counts", {})
                print(f"Counts: {counts}")

                # Sort measurements by frequency (most common first)
                sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)

                print(f"\nAnalyzing top measurements to find factors (N={n}, a={a}):")
                found_factors = False

                # Examine the top 10 measurements for better chances
                for bitstring, count in sorted_counts[:10]:
                    measured_int = int(bitstring, 2)
                    phase = measured_int / (2 ** num_counting_qubits)

                    print(f"  Measurement: {bitstring} (int: {measured_int}), Count: {count}, Phase: {phase:.6f}")

                    if measured_int == 0:
                        print("    -> Phase 0.0 is trivial. Skipping.")
                        continue

                    # Try to extract factors using all convergents
                    f1, f2 = get_factors(n, measured_int, num_counting_qubits, a)
                    if f1 and f2:
                        print(f"    -> SUCCESS! Factors of {n} are {f1} and {f2}")
                        found_factors = True
                        break
                    else:
                        print("    -> Could not determine factors from this phase.")

                if not found_factors:
                    # Provide actionable guidance
                    print(f"\nCould not determine factors from the significant measurements.")
                    # Check if the period of a mod n is odd (inherently unfactorable)
                    r = 1
                    while pow(a, r, n) != 1 and r <= n:
                        r += 1
                    if r % 2 != 0:
                        print(f"NOTE: a={a} has period r={r} (odd) for N={n}.")
                        print(f"  Shor's algorithm requires an even period. Try a different value of 'a'.")
                        # Suggest good values
                        good_values = []
                        for candidate_a in range(2, n):
                            if math.gcd(candidate_a, n) != 1:
                                continue
                            # Find period
                            cr = 1
                            while pow(candidate_a, cr, n) != 1 and cr <= n:
                                cr += 1
                            # Check even period and non-trivial factors
                            if cr % 2 == 0 and pow(candidate_a, cr // 2, n) != n - 1:
                                good_values.append(candidate_a)
                        if good_values:
                            print(f"  Recommended values of 'a' for N={n}: {good_values}")
                    else:
                        print("Try running again (quantum measurements are probabilistic).")

            except json.JSONDecodeError:
                print(f"Failed to parse result JSON: {result_json}")


if __name__ == "__main__":
    # Parse command-line arguments: N (number to factorize) and a (base)
    parser = argparse.ArgumentParser(description="Shor's Algorithm via MCP")
    parser.add_argument("N", type=int, help="Number to factorize (e.g. 15 or 21)")
    parser.add_argument("a", type=int, help="Base for modular exponentiation, must be coprime with N (e.g. 7)")
    args = parser.parse_args()

    # Validate inputs before running
    if args.N not in SUPPORTED_N:
        print(f"Error: N={args.N} is not supported. Supported values: {sorted(SUPPORTED_N)}")
        exit(1)

    if args.a <= 1 or args.a >= args.N:
        print(f"Error: 'a' must satisfy 1 < a < N. Got a={args.a}, N={args.N}")
        exit(1)

    if math.gcd(args.a, args.N) != 1:
        print(f"Error: a={args.a} is not coprime with N={args.N} (gcd={math.gcd(args.a, args.N)})")
        print("Choose a different value of 'a' that shares no common factors with N.")
        exit(1)

    asyncio.run(run_shor_mcp(args.N, args.a))
