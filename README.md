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
path_agent/
  pipeline.py                        Path feasibility analysis pipeline
  models.py                          Model interfaces
  prompts.py                         Prompt templates
  tool_schema.py                     Function lookup tool schema
  utils/
    conditions.py                    C/C++ condition extraction
    functions.py                     Call parsing, parameter mapping, and function lookup
    function_index.py                C/C++ project function indexing
    io.py                            JSON, cache, and filesystem utilities
exm_inputs/
  call_context.json                  Call chains and function context
run.py                               Default settings, input validation, and execution
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
| `exm_inputs/call_context.json` | Function call chains and context aligned with each warning |
| `exm_inputs/dereference_index.json` | Dereference statements, line numbers, and file paths for function parameters |

Default input paths and analysis settings are defined in `DEFAULT_CONFIG` in `run.py`; no separate configuration file is required. Call context must align with the warning records in order. Path constraints are extracted from function source code during analysis. To analyze another dataset, provide matching input files and the corresponding project source code.

**`dereference_index.json` is currently missing and must be supplied for complete inter-procedural dereference lookup.**

## Usage

Validate the configuration and inputs, then analyze a single warning or the full range:

```bash
.venv/bin/python run.py check
.venv/bin/python run.py run --start 0 --end 1
.venv/bin/python run.py run --start 0 --end 70
```

Ranges use zero-based indices with an inclusive start and an exclusive end. By default, the runner analyzes one warning. Use `--output` to specify a new output directory. For another dataset, edit `DEFAULT_CONFIG` in `run.py` or supply an external JSON configuration with `--config`.

To check the pipeline without a dereference index, explicitly allow an empty index:

```bash
.venv/bin/python run.py run --start 0 --end 70 --allow-missing-dereferences
```

In this mode, a missing inter-procedural lookup may return `True` (a feasible path) directly. Such outputs do not represent complete inter-procedural analysis.

Analysis results and function caches are written to `output/<timestamp>/`. Existing directories are never overwritten. Console output is not saved as a log, and runtime artifacts are excluded from Git.
