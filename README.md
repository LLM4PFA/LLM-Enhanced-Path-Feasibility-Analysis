# Agents as Neuro-Symbolic Reasoners: Path Feasibility Reasoning for Precise Static Bug Detection

we propose PATHAGENT, an agent-driven framework for fine-grained path feasibility analysis. PATHAGENT decomposes complex inter-procedural analysis into localized symbolic range reasoning sub-tasks, and employs an on-demand contextual exploration strategy to adaptively retrieve only the necessary code context. These designs enable precise path feasibility reasoning and effectively reduce false positives reported by static bug analyzers. 

## Benchmark

We construct a new benchmark [SAFP-Bench-C](./benchmark/), which includes false positives and real bugs reported by state-of-the-art static analyzers on real-world large-scale software systems.
**Bug Types.** we target five representative categories of critical bugs: Null- 756 Pointer-Dereference (NPD), Use-after-Free (UAF), Buffer-Overflow 757 (BOF), Divided-by-Zero (DBZ), and Use-before-Initialization (UBI). 
**Target Projects.** We select the recent versions of three large-scale and well-maintained C/C++ open-source projects for scanning, including the Linux kernel (v6.9.6), OpenSSL (v3.4.0), and 761 Libav (v12.3) . 
**Static Analyzers.** We use three state-of-the-art and widely-adopted 763 static analyzers: CodeQL, Infer, and CppCheck.
**Data statistics.** The final benchmark SAFP-Bench-C contains 443 warnings, of which 47 are real bugs and 396 are false positives.  Following Table presents the detailed statistics of SAFP-Bench-C.

![Data Statistics](./Data%20statistics.jpg) 

## Result

[LLMPFA result](./results/llmpfa_result/) present the overall performance of our appoarch LLMPFA, including comparsion among different vulnerability types, static analyzers, target projects and backbone LLMs. 

[LLMDFA result](./results/llmdfa_result/) and [LLM4SA result](./results/llmsa_result/) respectively present the overall performance of the baseline methods LLMDFA and LLM4SA.
