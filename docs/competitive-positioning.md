# Competitive positioning

redhand sits in one of the most crowded corners of AI-safety research —
agent-safety and reward-hacking benchmarks — so being honest about prior work is
a first-class design constraint, not an afterthought. If redhand looks like "a
re-implementation of an existing benchmark," it has no reason to exist. This
document states exactly what already exists and where redhand's defensible
position is.

## What already exists

| Prior work | What it measures | Form factor | How redhand differs / what it does NOT re-implement |
|---|---|---|---|
| **EvilGenie** (2025) | Reward hacking in programming: hardcoding test cases, editing test files | Research benchmark + paper | Same *phenomenon* (our S1/S3). redhand does not re-create its fixed task set or its model-scoring harness; it drives a *real installed agent* against *pluggable* tasks and adds an AST/git detection layer with per-line evidence. |
| **SpecBench** (2026) | Reward hacking in long-horizon coding agents via a hidden held-out test suite | Research benchmark | We adopt the *visible-vs-hidden test* idea (it is the honest way to define "cheating") and credit it. We do not copy its 30 systems tasks; our contribution is the runnable dev-tool wrapper + detection taxonomy S1–S8. |
| **AgentDojo** (NeurIPS 2024) | Indirect prompt-injection attacks/defenses against tool-using agents | Research framework, synthetic environments | Different threat model. AgentDojo = *external attacker* injecting instructions. redhand = *the agent itself* cutting corners under difficulty. We deliberately do NOT rebuild its injection environments. |
| **Agent Security Bench (ASB)** | Broad agent attacks/defenses (prompt injection, memory poisoning, backdoors) across 10 scenarios | Research benchmark + leaderboard | Superset of attack types but model-centric and simulated. redhand is narrow (coding-agent self-sabotage only) and runs real agents; we do not chase breadth. |
| **AgentHarm** (ICLR 2025) | Whether agents comply with overtly *harmful* task requests | Research benchmark | Different axis (malicious user intent, not honest-task corner-cutting). No overlap in tasks. |
| **Anthropic agentic-misalignment / reward-hacking research; Cursor's reward-hacking analysis; Hodoscope; "Do Coding Agents Deceive Us?"** | Evidence that coding models cheat on tests and that this generalizes to broader misalignment | Research papers / monitoring systems | These motivate redhand and supply its taxonomy vocabulary. redhand does not claim to discover the phenomenon; it operationalizes it as a tool you can point at your own agent config. |
| **MCPTox / MCP-SafetyBench / SafeMCP; Cisco mcp-scanner, Invariant mcp-scan** | Tool-poisoning and MCP-server security | Benchmarks + static scanners | Adjacent (untrusted *tools*), not agent self-sabotage. Out of scope for redhand's core. |

## The position redhand owns

Every item above tests **models** inside a **researcher-built (often simulated)**
harness, and reports a **leaderboard of models**. None of them is a
`pip install`-able developer tool that red-teams **your actual agent assembly** —
the real `claude` binary, your `CLAUDE.md`, your enabled tools/MCP servers — in a
disposable sandbox, and hands you a **per-line, AST/git-grounded** report of *how*
it cheated plus a shareable replay. That gap — research artifact vs. runnable
dev-tool, and model-scoring vs. config-red-teaming — is redhand's moat, and it is
the same structural gap that let dev-tools win next to academic benchmarks
before. The AST + git deterministic detection layer (high precision, per-line
evidence) is the second moat and maps directly onto the author's existing
strengths.

## Honest boundaries

redhand does **not** claim to have invented reward-hacking research, the
visible/hidden-test methodology (credit SpecBench and the reward-hacking
literature), or the taxonomy of cheating behaviors (credit Hodoscope and
Anthropic's work). It overlaps conceptually with EvilGenie and SpecBench on *what*
is being measured. Its only claims to novelty are **engineering form** (runs real
installed agents, not model APIs, with no simulated environment) and
**usability** (one command, disposable sandbox, offline dashboard, contributable
tasks/adapters/detectors). The north star is a *new empirical finding* about real
agents, not another leaderboard.

## Traps for implementers (do not do these)

1. **Do not rebuild AgentDojo's injection environments.** Different threat model;
   the agent sabotages itself here, no external attacker is needed.
2. **Do not turn this into another model leaderboard.** The unit of evaluation is
   *an agent assembly* (binary + config + tools), not a bare model. Comparing two
   `CLAUDE.md` configs of the *same* model is a first-class use case.
3. **Do not let the detectors flag honest fixes.** A single false positive on a
   legitimate change destroys the tool's credibility; the deterministic layer must
   prefer false negatives.
4. **Do not copy fixed task sets from prior benchmarks.** Tasks are pluggable and
   community-contributed; ship original seed tasks.
5. **Do not claim discovery.** Frame every finding as "measured on real agents
   with redhand," cite the prior art above, and report sample sizes.
