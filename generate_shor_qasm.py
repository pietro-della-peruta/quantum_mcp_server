"""
Generalized Shor's Algorithm QASM Circuit Generator.

Generates OpenQASM 2.0 circuits for Shor's period-finding algorithm
for supported values of N (15, 21) and any valid coprime base 'a'.

The circuit uses:
  - counting qubits for the Quantum Phase Estimation (QFT)
  - target qubits for modular exponentiation via permutation unitaries

Usage:
    python generate_shor_qasm.py <N> <a>
"""

import argparse
import math
import os
import numpy as np

from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
from qiskit.circuit.library import QFT, UnitaryGate


# Supported values of N for circuit generation
SUPPORTED_N = {15, 21}


def validate_inputs(n: int, a: int) -> None:
    """
    Validate that N is supported and that 'a' is a valid base
    (1 < a < n and gcd(a, n) == 1).
    """
    if n not in SUPPORTED_N:
        raise ValueError(f"N={n} is not supported. Supported values: {sorted(SUPPORTED_N)}")
    if a <= 1 or a >= n:
        raise ValueError(f"'a' must satisfy 1 < a < N. Got a={a}, N={n}")
    if math.gcd(a, n) != 1:
        raise ValueError(
            f"'a' must be coprime with N. Got a={a}, N={n}, gcd={math.gcd(a, n)}"
        )


def get_num_counting_qubits(n: int) -> int:
    """
    Return the number of counting qubits for phase estimation.

    Uses 2 * ceil(log2(n)) to ensure sufficient resolution for
    period detection via continued fractions. This is the standard
    textbook recommendation for Shor's algorithm.
    """
    return 2 * math.ceil(math.log2(n))


def build_modular_permutation_matrix(a_power_mod: int, n: int, num_target_qubits: int) -> np.ndarray:
    """
    Build a unitary permutation matrix for the operation x -> (a_power_mod * x) mod n.

    For states 0..n-1 the permutation is (a_power_mod * x) mod n.
    States n..2^num_target_qubits - 1 are mapped to themselves (identity).

    Args:
        a_power_mod: the value a^(2^k) mod n for a given counting qubit
        n: the number to factorize
        num_target_qubits: number of qubits in the target register
    Returns:
        A 2^num_target_qubits × 2^num_target_qubits unitary permutation matrix
    """
    dim = 2 ** num_target_qubits
    perm = list(range(dim))

    # Apply (a_power_mod * x) mod n for valid states 0..n-1
    for x in range(n):
        perm[x] = (a_power_mod * x) % n

    # States >= n are fixed points (identity) — already set by list(range(dim))

    # Build the permutation matrix: M[perm[i], i] = 1
    matrix = np.zeros((dim, dim))
    for i in range(dim):
        matrix[perm[i], i] = 1

    return matrix


def generate_shor_qasm(n: int, a: int) -> str:
    """
    Generate the OpenQASM 2.0 string for Shor's period-finding circuit.

    Uses Quantum Phase Estimation with controlled modular exponentiation
    unitaries built from permutation matrices.

    Args:
        n: the number to factorize (must be in SUPPORTED_N)
        a: the base for modular exponentiation (must be coprime with n)
    Returns:
        The QASM string for the circuit
    """
    # Validate inputs
    validate_inputs(n, a)

    # Number of qubits for the target register (enough to represent 0..n-1)
    num_target_qubits = math.ceil(math.log2(n))
    # Number of counting qubits: use 2x target qubits for reliable period detection
    num_counting_qubits = get_num_counting_qubits(n)

    print(f"Building circuit: {num_counting_qubits} counting qubits, {num_target_qubits} target qubits")

    # Create registers
    c = QuantumRegister(num_counting_qubits, 'c')      # counting (phase estimation)
    tgt = QuantumRegister(num_target_qubits, 'tgt')     # target (modular arithmetic)
    meas = ClassicalRegister(num_counting_qubits, 'meas')
    qc = QuantumCircuit(c, tgt, meas)

    # Step 1: Put counting qubits in superposition
    qc.h(c)

    # Step 2: Initialize target register to |1⟩ (eigenstate of the modular multiplication)
    qc.x(tgt[0])

    # Step 3: Apply controlled-U^(2^k) for each counting qubit k
    # U^(2^k) implements multiplication by a^(2^k) mod n
    non_identity_count = 0
    for k in range(num_counting_qubits):
        # Compute a^(2^k) mod n using Python's modular exponentiation
        a_power = pow(a, 2 ** k, n)

        # If a^(2^k) mod n == 1, U is the identity → skip this qubit
        if a_power == 1:
            continue

        non_identity_count += 1
        # Build the permutation unitary for this power
        matrix = build_modular_permutation_matrix(a_power, n, num_target_qubits)
        u_gate = UnitaryGate(matrix, label=f"{a}^{2**k} mod {n}")

        # Make it a controlled gate (controlled by counting qubit k)
        cu_gate = u_gate.control(1)
        qc.append(cu_gate, [c[k]] + list(tgt))

    print(f"  {non_identity_count} non-identity controlled unitaries applied")

    # Step 4: Apply inverse QFT to counting register
    qc.append(QFT(num_counting_qubits, inverse=True).to_gate(), c)

    # Step 5: Measure counting qubits
    qc.measure(c, meas)

    # Transpile to standard basis gates for broad QASM compatibility
    print("  Transpiling to basis gates (this may take a moment)...")
    qc_transpiled = transpile(
        qc,
        basis_gates=['u3', 'cx', 'h', 'x', 'measure'],
        optimization_level=3
    )

    import qiskit.qasm2
    return qiskit.qasm2.dumps(qc_transpiled)


def generate_and_save(n: int, a: int) -> str:
    """
    Generate the QASM circuit for (n, a) and save it to shor_{n}_{a}.qasm.

    Args:
        n: the number to factorize
        a: the base for modular exponentiation
    Returns:
        The path to the saved QASM file
    """
    qasm_str = generate_shor_qasm(n, a)

    # Save to file in the same directory as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filename = f"shor_{n}_{a}.qasm"
    filepath = os.path.join(script_dir, filename)

    with open(filepath, "w") as f:
        f.write(qasm_str)

    print(f"QASM circuit saved to {filepath}")
    return filepath


if __name__ == "__main__":
    # CLI: python generate_shor_qasm.py <N> <a>
    parser = argparse.ArgumentParser(
        description="Generate Shor's algorithm QASM circuit for a given (N, a) pair"
    )
    parser.add_argument("N", type=int, help="Number to factorize (15 or 21)")
    parser.add_argument("a", type=int, help="Base for modular exponentiation, must be coprime with N")
    args = parser.parse_args()

    generate_and_save(args.N, args.a)
