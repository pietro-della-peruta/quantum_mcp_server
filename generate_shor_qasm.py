
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
from qiskit.circuit.library import QFT
import numpy as np

def c_amod15(a, power):
    """Controlled multiplication by a^power mod 15"""
    if a not in [2,7,8,11,13]:
        raise ValueError("'a' must be 2,7,8,11 or 13")
    U = QuantumCircuit(4)        
    for _ in range(power):
        if a == 2:
            U.swap(0,1)
            U.swap(1,2)
            U.swap(2,3)
        if a == 7:
            # 7x mod 15
            # 1->7, 7->4, 4->13, 13->1
            # 0001 -> 0111 -> 0100 -> 1101 -> 0001
            # This can be implemented as:
            # Swap(0,1), Swap(1,2), Swap(2,3) -> gives 2x (same as a=2)
            # then X gates?
            # Actually, standard implementation for a=7:
            # 1. SWAP(0,1)
            # 2. SWAP(1,2)
            # 3. SWAP(2,3)
            # 4. X(0), X(1), X(2), X(3)
            # Let's verify: 
            # 1 (0001) -> (shift left) 2 (0010) -> (inv) 1101 (13). WRONG.
            # Let's use the known gate sequence for a=7 from Qiskit textbook
            # For a=7, it is 13 = 1101, 7=0111, ...
            # Implementation for 7:
            # SWAP(2,3)
            # SWAP(1,2)
            # SWAP(0,1)
            # X(0)
            # X(1)
            # X(2)
            # X(3)
            # No, that's just guessing.
            
            # Let's rely on the property that 7 = -8 mod 15 = 7.
            # 7x = x * 7.
            # Since we only iterate 4 states.
            pass
            
    # Since I cannot easily derive the sequence for 7 from scratch without risk,
    # I will just define the permutation matrix and transpile it!
    # Valid states: 1, 7, 4, 13
    # 0001, 0111, 0100, 1101
    # Full permutation on 16 states?
    # We can treat others as identity or mapped arbitrarily since we only start at 1.
    pass

def generate_shor_15_7():
    # 4 counting qubits, 4 work qubits
    c = QuantumRegister(4, 'c')
    tgt = QuantumRegister(4, 'tgt')
    meas = ClassicalRegister(4, 'meas')
    qc = QuantumCircuit(c, tgt, meas)

    # Initialize counting qubits
    qc.h(c)

    # Initialize target qubit tgt[0] to |1> (eigenstate of unitary U)
    qc.x(tgt[0])

    # Apply controlled-U operations
    # U = 7^x mod 15
    # U^1 controlled by c[0]
    # U^2 controlled by c[1]
    # U^4 controlled by c[2] (Identity)
    # U^8 controlled by c[3] (Identity)

    # Unitary for 7:
    # 1->7, 7->4, 4->13, 13->1
    # 0001 -> 0111 -> 0100 -> 1101
    
    # We will build U=7 via matrix for simplicity and correctness in generation
    # But QASM 2.0 loads might not like arbitrary unitaries if not decomposed.
    # Qiskit transpile will decompose it.
    
    # Permutation map for a=7
    # We must ensure it's a bijection on 0..15.
    # 7x mod 15 is bijection on 0..14. 
    # For 15 (1111), we explicitly map it to 15.
    perm = list(range(16))
    for i in range(15): # 0 to 14
        perm[i] = (7 * i) % 15
    perm[15] = 15 # Fix point
    
    matrix = np.zeros((16, 16))
    for i in range(16):
        matrix[perm[i], i] = 1
        
    from qiskit.circuit.library import UnitaryGate
    u7_gate = UnitaryGate(matrix, label="7x mod 15")
    cu7 = u7_gate.control(1)
    
    qc.append(cu7, [c[0]] + list(tgt)) # U^1
    
    # U^2 = 7^2 = 49 = 4 mod 15
    # 4x mod 15
    perm4 = list(range(16))
    for i in range(15):
        perm4[i] = (4 * i) % 15
    perm4[15] = 15
    
    matrix4 = np.zeros((16, 16))
    for i in range(16):
        matrix4[perm4[i], i] = 1
    u4_gate = UnitaryGate(matrix4, label="4x mod 15")
    cu4 = u4_gate.control(1)
    
    qc.append(cu4, [c[1]] + list(tgt)) # U^2
    
    # U^4 = 7^4 = 1 mod 15 => Identity. Skip c[2]
    # U^8 = 1 mod 15 => Identity. Skip c[3]

    # Inverse QFT
    qc.append(QFT(4, inverse=True).to_gate(), c)

    # Measure
    qc.measure(c, meas)
    
    # Transpile to basis gates (u3, cx) so QASM is standard and supported by qelib1.inc
    qc_transpiled = transpile(qc, basis_gates=['u3', 'cx', 'h', 'x', 'measure'], optimization_level=3)
    
    import qiskit.qasm2
    print(qiskit.qasm2.dumps(qc_transpiled))

if __name__ == "__main__":
    generate_shor_15_7()
