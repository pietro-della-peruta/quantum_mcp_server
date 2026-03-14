# Qiskit MCP Server

An MCP server that provides tools for interacting with IBM Quantum using Qiskit.

## Tools

- `list_backends`: List available quantum backends.
- `run_circuit`: Run a quantum circuit.
- `get_job_status`: Check the status of a job.
- `get_job_result`: Get the result of a job.

## Configuration

Set the `QISKIT_IBM_TOKEN` environment variable with your IBM Quantum API token.

## Usage

### Shor's Algorithm Example

Run `shor_example.py` passing the number to factorize and the chosen base as positional command-line arguments:

```bash
python shor_example.py <N> <a>
```

- **N** – the integer to factorize (supported: `15`, `21`)
- **a** – the base for modular exponentiation; must be coprime with N

#### Supported (N, a) pairs

| N   | Valid values for a                          |
|-----|---------------------------------------------|
| 15  | 2, 4, 7, 8, 11, 13                         |
| 21  | 2, 4, 5, 8, 10, 11, 13, 16, 17, 19, 20    |

#### Examples

```bash
# Factorize 15 using base 7
python shor_example.py 15 7

# Factorize 21 using base 4
python shor_example.py 21 4
```

The QASM circuit is auto-generated on first run and cached as `shor_<N>_<a>.qasm`.
You can also pre-generate circuits with:

```bash
python generate_shor_qasm.py <N> <a>
```
