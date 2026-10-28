# Agents as Neuro-Symbolic Reasoners: Path Feasibility Reasoning for Precise Static Bug Detection

PATHAGENT is an agent-driven framework for fine-grained path feasibility analysis. It decomposes inter-procedural analysis into localized symbolic range reasoning tasks and retrieves code context on demand to identify infeasible paths and reduce false positives reported by static analyzers.

## Benchmark

[SAFP-Bench-C](./benchmark/) contains 443 warnings from the Linux kernel (v6.9.6), OpenSSL (v3.4.0), and Libav (v12.3), reported by CodeQL, Infer, and CppCheck. It includes 47 real bugs and 396 false positives across five bug types:

- Null-Pointer Dereference (NPD)
- Use-After-Free (UAF)
- Buffer Overflow (BOF)
- Division by Zero (DBZ)
- Use Before Initialization (UBI)

![Data Statistics](./Data%20statistics.jpg)

## Results

- [PATHAGENT results](./results/llmpfa_result/): results across target projects, static analyzers, and backbone models.
- [LLMDFA results](./results/llmdfa_result/)
- [LLM4SA results](./results/llmsa_result/)

## Project Structure

```text
benchmark/                           Warning datasets
results/                             Paper experiment results
llm4pfa/
  analysis/
    pipeline.py                      Path feasibility analysis pipeline
    conditions.py                    C/C++ condition extraction
    call_utils.py                    Call parsing, parameter mapping, and dereference lookup
  llm/
    models.py                        Model interfaces
    prompts.py                       Prompt templates
    tool_schema.py                   Function lookup tool schema
  source/
    lookup.py                        Function source lookup
    index.py                         C/C++ project function indexing
  utils/
    data.py                          JSON data and cache I/O
    paths.py                         Filesystem helpers
  configs/linux-codeql-npd.json       Linux/CodeQL/NPD configuration
  data/linux-codeql-npd/              Context, constraints, and dereference index
run.py                               Input validation and execution
requirements.txt                     Python dependencies
.env.example                         Model service and source path settings
```

## Installation and Configuration

Use Python 3.10 or later. From the project root, run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp -n .env.example .env
```

Edit `.env` to set:

- `OPENAI_API_KEY`: API key for the model service.
- `OPENAI_BASE_URL`: Endpoint compatible with OpenAI Chat Completions.
- `OPENAI_MODEL`: Model name; defaults to `gpt-4o-mini`.
- `PFA_SOURCE_ROOT`: Absolute path to the Linux 6.9.6 source directory.

The target project's source code can reside outside this repository. `.env` is excluded from Git.

## Input Data

The default configuration analyzes 70 Linux/CodeQL null-pointer warnings and requires the following files:

| File | Contents |
|---|---|
| `benchmark/NPD/codeql/codeql_kernel69_nullpointer.json` | Warning locations, variables, function source code, and evaluation labels |
| `llm4pfa/data/linux-codeql-npd/context.json` | Function call chains and context aligned with each warning |
| `llm4pfa/data/linux-codeql-npd/constraints.json` | Target conditions and early-exit constraints |
| `llm4pfa/data/linux-codeql-npd/dereferences.json` | Dereference statements, line numbers, and file paths for function parameters |

Input paths are defined in `llm4pfa/configs/linux-codeql-npd.json`. Context and constraints must align with the warning records in order. To analyze another dataset, provide matching input files and the corresponding project source code.

**`dereferences.json` is currently missing and must be supplied for complete inter-procedural dereference lookup.**

## Usage

Validate the configuration and inputs, then analyze a single warning or the full range:

```bash
.venv/bin/python run.py check
.venv/bin/python run.py run --start 0 --end 1
.venv/bin/python run.py run --start 0 --end 70
```

Ranges use zero-based indices with an inclusive start and an exclusive end. By default, the runner analyzes one warning. Use `--config` to select another configuration and `--output` to specify a new output directory.

To check the pipeline without a dereference index, explicitly allow an empty index:

```bash
.venv/bin/python run.py run --start 0 --end 70 --allow-missing-dereferences
```

In this mode, a missing inter-procedural lookup may return `True` (a feasible path) directly. Such outputs do not represent complete inter-procedural analysis.

Analysis results and function caches are written to `output/<timestamp>/`. Existing directories are never overwritten. Console output is not saved as a log, and runtime artifacts are excluded from Git.
