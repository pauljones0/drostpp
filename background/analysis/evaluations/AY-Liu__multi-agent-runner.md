# AY-Liu/multi-agent-runner architecture, orchestration, and reliability evaluation

## 1. Snapshot, scope, and elapsed-time evidence.

The checkout was at `e2fe272625e4d5aeafaa18e317b8c1c5e2da38bd` on `main`. The Git tree was `b6000b40e262c1485e9c02ec5b4bae6e12a673d8`, with commit subject *docs: clarify demo workflow and design principles*. The initial UTC timestamp was **2026-11-19 17:08:42.974860834 UTC**. At that check, Git reported zero tracked or untracked changes, and a separate ignored-status check was also empty. At **2026-11-19 17:38:51.132921533 UTC**, the same HEAD and tree were present. Porcelain output including ignored and untracked entries, the tracked-file diff, and the staged diff were empty. A byte-and-mode comparison against the Git tree covered all 44 tracked files. Both temporary labs had been removed. The UTC interval was **1808.158 seconds** (**30.136 minutes**) of investigation, experiment execution and analysis, and report verification. The checkout commands are in §9.

The evaluation covers the local orchestration loop, decision protocol, process and state ownership, adapter behavior, recovery, and operability. The project describes itself as experimental and expects users to supply authenticated local CLIs. The evaluation used deterministic local substitutes for both CLIs. An archived copy of the pin and per-case directories under the evaluation workspace supplied all runtime files. The experiments had a private PID and network namespace, a cleared environment, a system-only executable path plus test fixtures, and no mounted user home. No live provider, login, credential, remote Git operation, or external service was used. [README.md:6](repos/AY-Liu__multi-agent-runner/README.md:6), [README.md:97](repos/AY-Liu__multi-agent-runner/README.md:97), [README.md:257](repos/AY-Liu__multi-agent-runner/README.md:257).

The protocol enumerates nine headings. Sections 1–9 retain those titles, and the tenth contains the requested priorities and acceptance criteria. [Evaluation protocol](./README.md:6).

| UTC checkpoints | Active work |
| --- | --- |
| 17:08–17:12 | Verified the pin and cleanliness, read the protocol and core scripts, prepared an offline archive, ran both stock test suites and syntax checks, and started the natural heartbeat and backoff measurements. |
| 17:12–17:17 | Traced both public entry flows and isolated the pipe EOF artifact, decision fallback, nonzero exits, false success, worker process scope, and startup publication gap. |
| 17:17–17:24 | Compared direct and public recovery, tested provider handoff and archive provenance, held a real foreground wake, and exercised concurrency, state-write interruption, retry budgets, transport normalization, and process arguments. |
| 17:24–17:30 | Measured compatibility versus streaming progress, exercised the real timeout stop action, checked shell option effects, and isolated live-worker restart, spawn rejection, and writes after reset. |
| 17:30–17:38 | Rebuilt and executed the report's test blocks from a fresh archive, ran the shipped-demo and unfaulted scheduling controls, traced the bundled helper coverage, repeated the pipe-backed timing, and verified the report and checkout. |

**Assessment.** The harness makes a small team easy to model and inspect. In the controlled normal path, both adapters processed two role creations, two overlapping workers, one native worker resume, and a final artifact after the harness returned completion evidence. The system loses correctness when a file from a prior wake or attempt is treated as current, when a CLI or launcher exits on an unexpected branch, or when more than one process can write the same local state. This is a viable orchestration prototype for a trusted operator and short runs. Job ownership, decision freshness, and attempt provenance need stronger guarantees before an operator can leave prolonged or resumable work unattended. [scripts/harness.sh:92](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:92), [scripts/harness.sh:154](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:154), [scripts/wake_leader.sh:223](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:223), [scripts/launch_subagent.sh:54](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:54), [scripts/lib.sh:717](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:717).

## 2. Core architecture and end-to-end control/data flow.

~~~~mermaid
flowchart LR
    U["Leader instructions, inbox, and notes"] --> W["Synchronous leader wake"]
    P["Poll workers and collect outcomes"] -->|completion or timer| W
    S["Agent status and Markdown"] --> W
    W --> D["state/decisions/latest.json"]
    D --> E["Decision executor"]
    E -->|asynchronous launch or resume| C["Worker wrapper and provider CLI"]
    C --> R["Raw result, compatibility JSON, and exit files"]
    R --> P
    P --> S
    E -->|done| F["Completion sentinel"]
~~~~

1. **Entry and runtime.** `run.sh` locates the checkout from the script path, preselects the provider from CLI or environment, sources the shared library and adapter, checks that `leader.md`, `inbox.md`, and the provider executable exist, and applies Codex effort defaults. Every mode invokes `stop.sh` first. Harness mode enters the polling loop, once mode performs one wake and executable decision pass, and reset deletes generated state and recreates its directory layout. The library resolves the runtime directories, accepts the older `CLAW_*` aliases, sources the caller's Bash initialization when present, and uses Bash strict options. [run.sh:11](repos/AY-Liu__multi-agent-runner/run.sh:11), [run.sh:28](repos/AY-Liu__multi-agent-runner/run.sh:28), [run.sh:61](repos/AY-Liu__multi-agent-runner/run.sh:61), [run.sh:76](repos/AY-Liu__multi-agent-runner/run.sh:76), [scripts/lib.sh:6](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:6), [scripts/lib.sh:38](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:38), [scripts/lib.sh:56](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:56).
2. **Reconcile and wake.** Harness initialization overwrites the loop's own bookkeeping and inspects the previous agent directories. A recorded alive PID can retain `running` on direct harness entry. For a dead or missing PID it tries to recover valid nonempty normalized output, marks invalid output `error`, and falls back to `idle` when no normalized result exists. The harness chooses an initial or restart motive based on any recovered or preexisting terminal worker, then performs a foreground leader wake. Later it scans running workers, batches any observed completions, and wakes on those completions or on a timeout measured since the last completed leader wake. The five-second sleep spaces turns between work, and the threshold is strictly greater than 180 seconds. [scripts/harness.sh:16](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:16), [scripts/harness.sh:23](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:23), [scripts/harness.sh:92](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:92), [scripts/harness.sh:130](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:130), [scripts/harness.sh:154](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:154), [scripts/harness.sh:196](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:196), [scripts/harness.sh:245](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:245).
3. **Plan in prose, act through JSON.** Each leader wake constructs a single prompt from `leader.md`, the embedded contract and action schema, the wake reason, optional notes, a worker-by-worker status and Markdown snippet, the entire `inbox.md`, and paths and time. A leader can split and sequence work, refine a role, continue a provider session, wait, stop a worker, write artifacts directly, and decide whether the task is complete. The demo expresses its three-role fan-out, review gate, and synthesis policy entirely in Markdown. The wake runs against the chosen provider in resume mode, saves a session and a result, then looks for a direct decision in `state/decisions/latest.json`. It attempts output extraction if the file or its timestamp is absent. [scripts/wake_leader.sh:31](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:31), [scripts/wake_leader.sh:63](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:63), [scripts/wake_leader.sh:112](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:112), [scripts/wake_leader.sh:206](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:206), [scripts/wake_leader.sh:223](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:223), [examples/mini-escape-room/leader.md:29](repos/AY-Liu__multi-agent-runner/examples/mini-escape-room/leader.md:29).
4. **Dispatch.** The executor reads task metadata and logs the leader message. A textually true `done` sets the global sentinel and returns before the action loop. Otherwise, an inline Python program walks the action list in order. It creates role files synchronously, materializes worker instructions with `tempfile.mkstemp`, and spawns one shell launcher per launch or resume. The launcher prepends the role if present, resolves effort, sets state and an instruction summary, then forks a worker wrapper. It publishes the wrapper PID to two representations. The wrapper calls the provider synchronously, writes an exit-code file if it reaches the next command, and runs a separate monitor during the call. Dispatcher subprocess output is sent to `DEVNULL` so it does not hold the decision logging pipe open. `wait` is a no-op. The action loop has no persistent acknowledgement or child handle. [scripts/execute_decisions.sh:24](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:24), [scripts/execute_decisions.sh:34](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:34), [scripts/execute_decisions.sh:53](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:53), [scripts/execute_decisions.sh:74](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:74), [scripts/execute_decisions.sh:98](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:98), [scripts/launch_subagent.sh:25](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:25), [scripts/launch_subagent.sh:54](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:54), [scripts/launch_subagent.sh:65](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:65), [scripts/launch_subagent.sh:103](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:103).
5. **Execute and normalize.** Codex receives `-C`, `exec` or `exec resume`, JSONL transport, an output-last-message filename, and resolved effort. Its converter derives a session, last encountered agent message, error flag, turn count, and cost when the expected cost field is present. Claude receives `-p --output-format json`, optional native resume, and a model label from the retry wrapper. Its transport already occupies `latest.json`. A worker's wrapper PID disappearing triggers collection. The harness archives normalized JSON and, for Codex, raw JSONL, saves session pointers, derives Markdown if no nonempty Markdown exists, sets terminal status from the normalized error flag, and removes the PID file. On the next wake the leader sees the projected status and a short Markdown prefix and can inspect full artifacts. [providers/codex/provider.sh:32](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:32), [providers/codex/provider.sh:76](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:76), [scripts/codex_jsonl_to_compat.py:64](repos/AY-Liu__multi-agent-runner/scripts/codex_jsonl_to_compat.py:64), [providers/claude/provider.sh:28](repos/AY-Liu__multi-agent-runner/providers/claude/provider.sh:28), [scripts/lib.sh:220](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:220), [scripts/lib.sh:689](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:689), [scripts/lib.sh:717](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:717), [scripts/harness.sh:103](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:103).
6. **Stop and continue.** The harness exits when it sees `state/done`. The leader prompt expects the model to wait for required workers and stop unneeded ones before declaring completion. The public stop script walks PID files, attempts TERM on the corresponding group and PID, rewrites status, then uses a process-list heuristic for strays. Sessions, artifacts and most state survive a soft stop. A public restart starts with that same stop operation, then performs the initial wake with the current inbox and state. The old done sentinel survives this path. [leader.md:106](repos/AY-Liu__multi-agent-runner/leader.md:106), [scripts/harness.sh:215](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:215), [stop.sh:23](repos/AY-Liu__multi-agent-runner/stop.sh:23), [stop.sh:46](repos/AY-Liu__multi-agent-runner/stop.sh:46), [run.sh:76](repos/AY-Liu__multi-agent-runner/run.sh:76), [README.md:35](repos/AY-Liu__multi-agent-runner/README.md:35).

| Boundary | Data and ownership in this implementation | Source |
| --- | --- | --- |
| User → leader | Root Markdown is reread wholesale. It supplies task policy, follow-up input, and optional notes. User inbox messages have no consumed offset or per-message state. | [scripts/wake_leader.sh:112](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:112), [scripts/wake_leader.sh:128](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:128), [scripts/wake_leader.sh:141](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:141) |
| Leader → launcher | Single mutable JSON decision, a role file per name, and temporary instruction materialization. Problems within a batch can leave earlier actions applied. | [scripts/lib.sh:368](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:368), [scripts/execute_decisions.sh:43](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:43), [scripts/execute_decisions.sh:58](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:58) |
| Supervisor → agent | Directory name, mutable `status.json`, separate numeric `pid`, transient wrapper, and provider invocation. Directories represent agent identities that can be used for multiple requests. | [scripts/lib.sh:363](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:363), [scripts/lib.sh:657](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:657), [scripts/launch_subagent.sh:54](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:54), [scripts/launch_subagent.sh:103](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:103) |
| Provider → collector | Raw or compatibility files, stderr, exit-code file, Markdown, and second-resolution archive names. A worker result and a session pointer are projected separately. | [scripts/launch_subagent.sh:94](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:94), [providers/codex/provider.sh:76](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:76), [scripts/lib.sh:637](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:637), [scripts/lib.sh:717](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:717) |
| Agent → next wake | The file projection and completion reason are the main feedback channels. An agent can also put artifacts in the shared workspace for a leader or peer to read. | [scripts/wake_leader.sh:31](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:31), [scripts/wake_leader.sh:147](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:147), [scripts/harness.sh:130](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:130) |

The relevant recovery states are `idle` and `running` at launch, then `done` or `error` at collection. Public stop goes from `running` to `idle` and clears the JSON PID, while completion deletes the separate claim file but retains the last PID in JSON. Bootstrap takes an additional set of apparent terminal transitions based on a distinct content predicate. There is no durable state for `queued`, `starting`, `retrying`, `cancel requested`, `cancelled`, or `interrupted`. In particular, idle after restart can indicate that a prior process was signaled, that a dead PID file existed, or that no compatible result was present. [scripts/lib.sh:657](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:657), [scripts/lib.sh:677](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:677), [scripts/lib.sh:747](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:747), [scripts/stop_state.py:15](repos/AY-Liu__multi-agent-runner/scripts/stop_state.py:15), [scripts/harness.sh:43](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:43).

## 3. Why the design works and its governing invariants.

- **The leader owns intent and the harness owns enactment.** The model chooses roles and dependencies; the executor has a small vocabulary for effects. For the demo policy, a single ordered `create_role → launch` pair ensures the prompt file is visible to its launcher, while independent subprocesses let unrelated workers overlap. The dispatcher's pipe redirection lets the harness regain control before workers finish. Each later leader turn begins with available result context and can decide whether to retry, refine, or synthesize. [scripts/wake_leader.sh:63](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:63), [scripts/execute_decisions.sh:58](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:58), [scripts/execute_decisions.sh:80](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:80), [examples/mini-escape-room/leader.md:31](repos/AY-Liu__multi-agent-runner/examples/mini-escape-room/leader.md:31).
- **A single harness loop serializes its own leader calls.** A wake blocks this loop until the leader returns. This keeps one loop from issuing interleaved decisions and gives a simple completion-batching point. A new loop can overwrite the JSON guard, and the guard is a separate read and write. A single supervisor per checkout is an assumed operating condition. [scripts/harness.sh:23](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:23), [scripts/harness.sh:154](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:154), [scripts/harness.sh:226](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:226).
- **A stable name is the join key.** Role, instruction summary, status, wrapper, compatibility output, history, and session files join through a shared path. For a cooperative leader that creates a unique role/name and issues a second request only after the first result is collected, state is easy to inspect and resume. One unfinished request per name, publication of the PID with the running state, and a result owned by that PID are essential operational invariants. Separate unconstrained file writes leave all three open to races. [scripts/lib.sh:363](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:363), [scripts/lib.sh:657](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:657), [scripts/launch_subagent.sh:25](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:25), [scripts/launch_subagent.sh:54](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:54), [scripts/launch_subagent.sh:103](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:103).
- **A current, actionable decision must belong to the wake that produced it.** The API is easy to use because every wake has a familiar decision path. The safe operating assumption is that the leader finishes a complete JSON write for every wake before returning, that its actions are executed once, and that it declares done only after the required workers finish. The code checks timestamp presence, reads metadata and actions independently, and accepts the sentinel. Wake identity, apply status, schema validity, and drained workers are outside that check. [scripts/wake_leader.sh:67](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:67), [scripts/wake_leader.sh:223](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:223), [scripts/execute_decisions.sh:24](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:24), [scripts/execute_decisions.sh:34](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:34), [leader.md:106](repos/AY-Liu__multi-agent-runner/leader.md:106).
- **Provider-native sessions preserve depth and local summaries provide portability.** A provider-scoped session wins, a legacy session is accepted only if classified as the same provider, and a switch without a usable current session can append a bounded handoff and start fresh. This is effective for a clean A-to-B switch with correctly attributed artifacts. Stable provider ownership and an accurate summary of what actually happened are required for a trustworthy handoff. [scripts/lib.sh:394](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:394), [scripts/lib.sh:497](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:497), [scripts/lib.sh:524](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:524), [scripts/lib.sh:588](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:588), [providers/codex/provider.sh:51](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:51), [providers/claude/provider.sh:40](repos/AY-Liu__multi-agent-runner/providers/claude/provider.sh:40).
- **Polling provides a recovery opportunity once control returns.** Completion coalescing and periodic wakes give simple progress without an external broker. The 180-second threshold is a scheduling trigger for the next wake. It never interrupts an in-flight leader call. Recoverability depends on the provider yielding and the wrapper and filesystem projections surviving in a consistent state. [scripts/harness.sh:130](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:130), [scripts/harness.sh:154](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:154), [scripts/harness.sh:226](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:226), [scripts/lib.sh:242](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:242), [scripts/lib.sh:298](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:298).

## 4. What it does well and poorly, with source evidence.

### Decisions, scheduling, and completion

- The project keeps deployment small and avoids a database, server, API key manager, or workflow DSL. Runtime artifacts expose intermediate data directly. The two adapters reuse the same decisions and collection loop, and provider differences are recognizable at call sites. The healthy fake-provider runs demonstrated actual overlapping workers, two completion callbacks, and native resume without forcing provider-specific action shapes. [README.md:12](repos/AY-Liu__multi-agent-runner/README.md:12), [README.md:97](repos/AY-Liu__multi-agent-runner/README.md:97), [scripts/execute_decisions.sh:58](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:58), [scripts/harness.sh:215](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:215), [providers/claude/provider.sh:28](repos/AY-Liu__multi-agent-runner/providers/claude/provider.sh:28), [providers/codex/provider.sh:32](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:32).
- A timestamped old decision can be applied again if the next provider call succeeds without writing a new decision. The fallback checks for a nonempty timestamp without comparing it to the wake. With the old file removed, a valid fenced decision reaches the extraction branch and is still replaced. The Python `except:` catches its own `sys.exit(0)`, and execution falls through to the empty decision write. In the isolated control, the same new role action worked when written directly. A logging claim of extraction can therefore coexist with an empty applied decision. [scripts/wake_leader.sh:223](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:223), [scripts/wake_leader.sh:239](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:239), [scripts/wake_leader.sh:260](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:260), [scripts/execute_decisions.sh:42](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:42).
- The prompt schema is advisory. Top-level done handling precedes launch and stop actions. The action executor mutates disk and starts processes before knowing the whole batch is valid, and allows unknown kinds to become informational messages. An integer role prompt raised a `TypeError` after an earlier role had been created and after truncating the invalid action's existing role file. That leaves the current decision and a partially applied prefix. `task_status` is printed on done and has no independently enforced blocked or failed transition. [scripts/wake_leader.sh:77](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:77), [scripts/execute_decisions.sh:24](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:24), [scripts/execute_decisions.sh:34](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:34), [scripts/execute_decisions.sh:53](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:53), [scripts/execute_decisions.sh:65](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:65), [scripts/execute_decisions.sh:116](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:116).
- A completed task's sentinel survives a normal rerun. The next leader reads the follow-up and can launch a worker, after which the harness exits on the old marker before collecting any completions. Clearing the sentinel in the disposable test let a subsequent follow-up complete. A fresh `done:true` decision also let an active worker outlive the supervisor and ignored the stop action in the same decision. The default's prompt-only completion safeguards do not enforce this lifecycle. [README.md:35](repos/AY-Liu__multi-agent-runner/README.md:35), [run.sh:93](repos/AY-Liu__multi-agent-runner/run.sh:93), [scripts/harness.sh:209](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:209), [scripts/harness.sh:215](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:215), [scripts/execute_decisions.sh:34](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:34), [leader.md:106](repos/AY-Liu__multi-agent-runner/leader.md:106).

### Process supervision and retry

- Worker startup overlaps, but `running` is published before the PID file and the harness treats that transient observation as completion. A gated scheduling control made the collector mark the worker `error` before its provider started. The worker subsequently wrote a good result and a new PID file that the loop ignored because the status was already terminal. A stable name can be launched more than once and the Popen handles are discarded. A live PID is only a liveness hint and has no per-attempt start identity, lease, or reaping relationship with the scheduler. [scripts/execute_decisions.sh:74](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:74), [scripts/launch_subagent.sh:54](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:54), [scripts/launch_subagent.sh:103](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:103), [scripts/harness.sh:92](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:92).
- A successful decision process is also weaker than a successful launch. The executor created an instruction file and returned the “Decisions executed” log for a request with an empty agent name. The launcher rejected it, leaving neither worker status nor provider call. Calling that launcher directly with the same empty name returned 1 and printed usage. The parent discards the only immediate error and has no reconciliation for an early launch failure. [scripts/execute_decisions.sh:58](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:58), [scripts/execute_decisions.sh:74](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:74), [scripts/launch_subagent.sh:16](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:16).
- The decision-level stop derives the agent path from the parent of `prompts/roles`, which is `prompts`; the actual registry is at the checkout's root. The normal-layout stop action made no change and returned success. The public stop did find the tracked wrapper and provider, but their actual process group was owned by the launcher and the wrapper PID was a different number. Process-list cleanup hit the provider through its argv and missed an isolated child with no checkout path in its argv. A TERM-resistant provider also continued after the public stop had removed its PID file and reported `idle`. [scripts/lib.sh:11](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:11), [scripts/execute_decisions.sh:98](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:98), [scripts/launch_subagent.sh:65](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:65), [scripts/launch_subagent.sh:103](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:103), [stop.sh:25](repos/AY-Liu__multi-agent-runner/stop.sh:25), [stop.sh:46](repos/AY-Liu__multi-agent-runner/stop.sh:46).
- The retry helpers normally run under `errexit`. A nonzero provider command exits the wrapper before the next `rc=$?` and before normalization, classifier, and exit recording. A failed leader call likewise aborts the harness before clearing its running guard or printing the warning. Identical synthetic failures did retry when the adapter call was placed in a shell conditional. A Claude rate-limit payload with CLI status 0 also reached the public retry path and showed the intended Opus-to-Sonnet fallback with a real 30-second backoff. [scripts/lib.sh:38](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:38), [scripts/lib.sh:242](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:242), [scripts/lib.sh:290](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:290), [scripts/wake_leader.sh:204](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:204), [scripts/harness.sh:154](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:154).
- Exit code, normalized provider error and completion state can disagree. Both adapters produced `done` in a worker control where the fake CLI wrote a success-shaped payload followed by exit 42. Codex collection used its default exit 0 because the exit record was missing. A prior Codex success also masked a failed resume with a fresh raw failure event, because the old nonempty compatibility JSON prevented re-normalization. Supplying a recognizable failure event or error flag in a fresh case produced `error`, so the result depends on data shape and file freshness. [scripts/lib.sh:298](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:298), [scripts/launch_subagent.sh:94](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:94), [providers/codex/provider.sh:76](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:76), [scripts/lib.sh:717](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:717).
- The leader and worker spinners are human progress aids. TERM stops the Bash spinner while its current sleep may survive. In a direct measurement, the successful top-level process returned in 0.415 s and output EOF arrived at 10.091 s. The only other holder of its output pipe was the orphaned `sleep 10`. This matters to shell pipelines and callers that wait for stream EOF. The worker launch redirection avoids holding the dispatcher log pipe, while its own monitor can still leave a short-lived sleeper. [scripts/wake_leader.sh:179](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:179), [scripts/wake_leader.sh:200](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:200), [scripts/launch_subagent.sh:68](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:68), [scripts/execute_decisions.sh:93](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:93).

### Persistence, sessions, and workspace

- Provider-scoped and legacy aliases keep older directories usable. The normal A-to-B handoff appends readable context and keeps a foreign session ID out of native resume arguments if provenance is correct. On A-to-B-to-A, an existing A ID takes precedence and leaves B's newer narrative out of the return prompt. Worker handoff also reads the instruction summary after the launcher has already replaced it, so it can present the new request as the previous one. This makes handoff a lossy compatibility device. [scripts/lib.sh:477](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:477), [scripts/lib.sh:497](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:497), [scripts/lib.sh:524](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:524), [scripts/lib.sh:588](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:588), [scripts/launch_subagent.sh:54](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:54).
- Files make recovery inspectable and modular, but ordinary public restart resets a dead PID's recorded `running` status before recovery can inspect the output. Direct bootstrap reconciled a valid payload with a dead PID and distinguished empty from malformed normalized output. It classified raw-only Codex results `idle` even when the converter could recover them. Recovery can also save a previous Claude session ID as Codex because it applies the new runner's adapter to the old result. The resume command then accepts that mislabeled pointer. [run.sh:93](repos/AY-Liu__multi-agent-runner/run.sh:93), [stop.sh:25](repos/AY-Liu__multi-agent-runner/stop.sh:25), [scripts/stop_state.py:15](repos/AY-Liu__multi-agent-runner/scripts/stop_state.py:15), [scripts/harness.sh:34](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:34), [scripts/lib.sh:637](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:637), [scripts/lib.sh:717](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:717).
- Claude success updates `latest.json` but can leave `output.md` at the first run because shared extraction respects any nonempty Markdown and the adapter never writes a new one itself. In the two-run smoke test, `latest.json` and the archive recorded “alpha resumed,” while the Markdown and subsequent leader snippet still said “alpha first.” The shared display contract gives one filename two roles, provider-written final output and collector-owned projection. [providers/claude/provider.sh:28](repos/AY-Liu__multi-agent-runner/providers/claude/provider.sh:28), [providers/claude/provider.sh:57](repos/AY-Liu__multi-agent-runner/providers/claude/provider.sh:57), [scripts/lib.sh:689](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:689), [scripts/wake_leader.sh:49](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:49).
- Root-scoped paths make local cooperation convenient. Both adapters explicitly request non-interactive permissive CLI permissions, and the leader and workers share writable project artifacts by design. Role prompts set scope as prose. The harness defines no per-agent workspace, file ownership or capability policy, and appends worker and prior-provider text to the leader or handoff prompt as plain content. Claude also inherits process CWD, whereas Codex receives a root option. This boundary suits a trusted local project. Its capabilities and working directory need explicit contracts for controlled multi-workspace use. [README.md:257](repos/AY-Liu__multi-agent-runner/README.md:257), [scripts/lib.sh:8](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:8), [scripts/wake_leader.sh:49](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:49), [scripts/lib.sh:608](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:608), [providers/codex/provider.sh:50](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:50), [providers/claude/provider.sh:37](repos/AY-Liu__multi-agent-runner/providers/claude/provider.sh:37), [scripts/lib.sh:250](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:250).

## 5. Core-code quality: decomposition, state, concurrency, errors, types, tests, observability, extensibility, and maintainability.

| Dimension | Evaluation | Source |
| --- | --- | --- |
| Decomposition | Wake, dispatch, launch, poll, stop and provider adapters are legible process boundaries. The shared library couples environment setup, paths, logging, monitoring, retry, JSON I/O, session migration, state, and collection. Several Python fragments live in Bash strings or heredocs, making their exception semantics and cross-stage effects easy to miss. | [scripts/lib.sh:6](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:6), [scripts/lib.sh:170](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:170), [scripts/lib.sh:329](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:329), [scripts/lib.sh:394](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:394), [scripts/lib.sh:717](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:717), [scripts/wake_leader.sh:229](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:229) |
| State and types | Small JSON is readable and avoids new runtime dependencies. It has no checked schema version at the process boundary. Reads flatten missing, null and parse failure, and writes re-open a live file for truncation. Type conversion is inferred from the spelling of a shell argument. Multiple writes make one state transition, and PID JSON can stay populated after the PID file is removed. | [scripts/lib.sh:331](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:331), [scripts/lib.sh:344](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:344), [scripts/lib.sh:657](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:657), [scripts/lib.sh:677](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:677), [scripts/lib.sh:747](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:747) |
| Concurrency and resources | One foreground leader offers a simple serial decision point and concurrent workers are inexpensive to start at small scale. A slow foreground wake blocks collection. There is no ownership lock, admission queue, worker or provider concurrency budget, deadline, or retention policy in the loop. Requests and periodic scans grow with the agent roster. | [scripts/execute_decisions.sh:58](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:58), [scripts/execute_decisions.sh:96](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:96), [scripts/harness.sh:92](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:92), [scripts/harness.sh:154](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:154), [scripts/harness.sh:245](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:245), [scripts/wake_leader.sh:31](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:31) |
| Error model | Pure Python retry and effort functions are small and testable. The live path mixes process exits, application errors, best-effort files, bare catch-all handlers, and shell control context. It can abort on a missing session ID from a zero-exit CLI, or proceed with a missing exit record and classify stale output. | [scripts/codex_effort.py:13](repos/AY-Liu__multi-agent-runner/scripts/codex_effort.py:13), [scripts/codex_retry_policy.py:34](repos/AY-Liu__multi-agent-runner/scripts/codex_retry_policy.py:34), [scripts/lib.sh:290](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:290), [scripts/lib.sh:637](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:637), [scripts/wake_leader.sh:206](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:206), [scripts/wake_leader.sh:246](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:246) |
| Observability | UTC harness and progress logs, stderr, raw Codex transport, status, and compatibility archives make a small run easy to inspect. Multi-stage states lack correlation IDs and attempt history. The completion reason captures log stdout as data, while the periodic status reports normalized JSON size and does not necessarily reflect raw CLI progress. The Claude stream processor is standalone. The adapter uses one JSON result. | [scripts/lib.sh:86](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:86), [scripts/harness.sh:106](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:106), [scripts/harness.sh:226](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:226), [scripts/harness.sh:249](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:249), [scripts/stream_processor.py:3](repos/AY-Liu__multi-agent-runner/scripts/stream_processor.py:3), [providers/claude/provider.sh:37](repos/AY-Liu__multi-agent-runner/providers/claude/provider.sh:37) |
| Extension | An adapter supplies CLI discovery, defaults and banner, effort resolution, raw path, execution, normalization, and archive hooks. Claude stages can be no-ops where their format already meets the common envelope. Provider allowlisting and session inference name the two supported implementations explicitly, with retry logic still in the library. Role templates are references and dynamic roles are plain files. | [scripts/lib.sh:20](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:20), [scripts/lib.sh:394](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:394), [providers/codex/provider.sh:3](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:3), [providers/claude/provider.sh:61](repos/AY-Liu__multi-agent-runner/providers/claude/provider.sh:61), [scripts/wake_leader.sh:101](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:101), [CONTRIBUTING.md:14](repos/AY-Liu__multi-agent-runner/CONTRIBUTING.md:14) |
| Tests and maintenance | The 22 local tests cover valuable narrow contracts, particularly effort, parsing, retry classification, Claude fallback, reset, and handoff. The existing fallback stubs return 0 with an application error. They do not exercise a full live-loop retry with nonzero CLI status. The checkout's documented invocation and robust continuation need executable-path integration coverage. | [README.md:243](repos/AY-Liu__multi-agent-runner/README.md:243), [tests/test_claude_retry.py:35](repos/AY-Liu__multi-agent-runner/tests/test_claude_retry.py:35), [tests/test_claude_retry.py:58](repos/AY-Liu__multi-agent-runner/tests/test_claude_retry.py:58), [tests/test_provider_session_handoff.py:57](repos/AY-Liu__multi-agent-runner/tests/test_provider_session_handoff.py:57), [tests/test_reset.py:39](repos/AY-Liu__multi-agent-runner/tests/test_reset.py:39) |

The resource costs follow the file and process model. The leader's status section performs four Python reads per agent, adds its 200-character instruction projection and first 500 output bytes, and passes the full constructed prompt as one argument. Codex reads its transport to build a list of decoded events, then its retry policy reads the raw stream again when being called. The monitor loads the stderr file before picking and truncating the last line. The explicit per-agent snippets keep small rosters readable, but they leave aggregate context size, raw transport size, history retention, and per-attempt read cost unconstrained. [scripts/wake_leader.sh:31](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:31), [scripts/wake_leader.sh:167](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:167), [scripts/codex_jsonl_to_compat.py:16](repos/AY-Liu__multi-agent-runner/scripts/codex_jsonl_to_compat.py:16), [scripts/codex_retry_policy.py:66](repos/AY-Liu__multi-agent-runner/scripts/codex_retry_policy.py:66), [scripts/lib.sh:111](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:111).

## 6. Executed tests/experiments and their limitations.

### Bundled suite, invocation, and environment

| Check | Executed result |
| --- | --- |
| `python3 -m unittest discover -v -s tests -p 'test_*.py'` with system Python 3.14.8 | **22/22 passed**, 0.460 s reported by unittest. It includes subprocess integration for reset, provider choice, monitor helpers, provider handoff, and Claude fallback, plus pure effort, compatibility parser, retry policy, and stop-state tests. |
| Same discovery with mounted Python 3.12.16 | **22/22 passed**, 0.398 s reported by unittest. The child PATH placed 3.12 first. |
| Per-file `bash -n` and in-memory Python `compile()` | **9/9 shell files and 14/14 Python files passed**. GNU Bash 5.3.20 on Linux x86_64. |
| README's direct shell entry | Both `./run.sh --once` and `./stop.sh` returned **126**, permission denied. Git tracks both as `100644`. Explicit `bash run.sh` and `bash stop.sh` ran the same sources in the controls below. |
| Sandbox baseline | Private PID namespace with bubblewrap as PID 1, empty network route table, unset HOME, no mounted user home or login profile, and no Codex or Claude executable on the system-only PATH before installing case substitutes. |

The unit command matches the published test command. The per-file shell loop is broader than the published multi-file invocation, which parses the first positional script. The suite ran from an archive bind-mounted read-only, with test-created files under the isolated scratch mount. [README.md:20](repos/AY-Liu__multi-agent-runner/README.md:20), [README.md:243](repos/AY-Liu__multi-agent-runner/README.md:243), [CONTRIBUTING.md:5](repos/AY-Liu__multi-agent-runner/CONTRIBUTING.md:5).

A transparent stdlib `sys.settrace` repeat of the stock suite passed the 22 tests and recorded these observed/executable source-line counts for standalone helpers: effort 23/23, compatibility converter 57/110, Codex retry classifier 42/67, stop-state helper 15/21, and stream processor 0/116. Denominators come from compiled code line tables. This observation excludes inline Python and Bash and gives no branch-coverage measure. In particular, the stock tests import the converter and classifier without exercising their CLI mains in the Codex orchestration path. [tests/test_codex_jsonl_to_compat.py:10](repos/AY-Liu__multi-agent-runner/tests/test_codex_jsonl_to_compat.py:10), [tests/test_codex_retry_policy.py:10](repos/AY-Liu__multi-agent-runner/tests/test_codex_retry_policy.py:10), [scripts/codex_jsonl_to_compat.py:124](repos/AY-Liu__multi-agent-runner/scripts/codex_jsonl_to_compat.py:124), [scripts/codex_retry_policy.py:75](repos/AY-Liu__multi-agent-runner/scripts/codex_retry_policy.py:75).

### Focused controls

The scripts in §9 implement the exact fixture and case invocations. The status numbers in the table are the underlying program exit codes, as observed by the test controls.

| Control | Result and source |
| --- | --- |
| `flow.py codex` and `flow.py claude` | Each yielded three leader calls, two workers concurrently live, one native worker resume, two alpha archives and one final artifact. Completion wakes were 5.676/5.521 s apart with Codex and 5.653/5.472 s with Claude in the file-backed runs. Codex action effort arrived low/medium/high. Claude stayed on Opus and ignored the effort fields. Both retained three 0600 temporary instruction files in their test temp root. Claude's resumed JSON and Markdown disagreed. [scripts/execute_decisions.sh:74](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:74), [scripts/harness.sh:226](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:226), [scripts/lib.sh:689](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:689). |
| `schedule_probe.py example` | Used the checked-in demo's leader and inbox input in a disposable copy. The first prompt included both inputs, all three named groups overlapped at low effort, the next prompt included all three outputs, and the expected artifact path was written by the scripted leader. This validates the workflow shape and output routing. [README.md:54](repos/AY-Liu__multi-agent-runner/README.md:54), [examples/mini-escape-room/leader.md:29](repos/AY-Liu__multi-agent-runner/examples/mini-escape-room/leader.md:29), [examples/mini-escape-room/leader.md:47](repos/AY-Liu__multi-agent-runner/examples/mini-escape-room/leader.md:47). |
| `natural.py heartbeat` | Empty work under a wait decision caused the second leader call after **181.436 s**, native resume of `codex-leader-1`, tick count 36 and a log reason of 182 seconds since last wake. End-to-end pipe EOF was 191.528 s. [scripts/harness.sh:16](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:16), [scripts/harness.sh:139](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:139), [scripts/harness.sh:270](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:270). |
| `natural.py claude` and `provider_edges.py budget codex\|claude` | A Claude 429 application error at exit 0 reached Sonnet with **30.029 s** between CLI starts. Only the final JSON was archived. The intercepted-sleep controls each performed 13 calls with backoffs `[30,60,90,120,150,180,210,240,270,300,300,300]`, totaling 2,250 requested seconds, with a configured success on attempt 13. Claude made 1 Opus and 12 Sonnet calls. [scripts/lib.sh:242](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:242), [scripts/lib.sh:267](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:267), [scripts/lib.sh:298](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:298). |
| `flow.py decisions` | Wake 2 with a new fenced decision replayed the old timestamped direct action. Removing or corrupting the old JSON allowed extraction, but the same wake then logged the empty fallback and applied no actions. Direct JSON for the identical action worked. A malformed three-action batch returned 1 after applying its first action, truncating the second role, and leaving the third unexecuted. Reproduced under 3.12 and 3.14. [scripts/wake_leader.sh:226](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:226), [scripts/wake_leader.sh:246](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:246), [scripts/execute_decisions.sh:65](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:65). |
| `flow.py continuation` and `flow.py early_done` | The previous marker survived the second run even though the leader had seen the new inbox input and issued a nonterminal launch. The harness returned 0, the worker was still alive, and its later artifact landed with state `running`. Clearing the old marker let a subsequent run produce a collected result and final artifact. With a fresh done decision, a still-live worker also survived and the colocated stop action was skipped. [run.sh:93](repos/AY-Liu__multi-agent-runner/run.sh:93), [scripts/harness.sh:209](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:209), [scripts/harness.sh:218](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:218), [scripts/execute_decisions.sh:34](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:34). |
| `failure.py retry codex\|claude` | Exit 42 plus an explicit 429 fixture gave one CLI invocation, no retry or exit record, and `leader_running=true` with null last-wake time. The attempted wake warning was absent. A conditional call through each original adapter gave two invocations and the expected success. Reproduced under 3.12 and 3.14. [scripts/lib.sh:41](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:41), [scripts/lib.sh:250](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:250), [scripts/lib.sh:302](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:302), [scripts/harness.sh:165](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:165). |
| `failure.py worker_exit codex\|claude` and `failure.py stale_worker` | Exit 42 and success-shaped output gave `done` with no exit record in both adapters. Fresh explicit failure output gave `error`. A clean exit gave `done` and exit record 0. After an earlier Codex success, exit 42 with a new failure event left the old result, old exit 0, old session, two archives of “old success,” and status `done`. [scripts/launch_subagent.sh:94](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:94), [providers/codex/provider.sh:76](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:76), [scripts/lib.sh:735](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:735). |
| `failure.py no_session`, `recovery.py empty_session`, and `contracts.py errinherit` | Both leaders returned 1 on a completed decision with valid compatibility JSON and no ID, although the provider exit was 0. Bootstrap archived analogous worker content and then stopped before leader startup. Adding only an ID let it finish. A running worker with no ID was collected in default Bash but aborted the poll with `inherit_errexit` enabled, leaving the PID claim, `running` state, and only one leader call. [scripts/lib.sh:650](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:650), [scripts/lib.sh:735](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:735), [scripts/wake_leader.sh:213](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:213), [scripts/harness.sh:71](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:71), [scripts/harness.sh:226](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:226). |
| `provider_edges.py false_hit` and `provider_edges.py normalization` | A success at exit 0 with “please generate output” on Claude stderr retried as a rate limit. “please compose output” took one call. Codex accepted a draft from `item.started` over supplied final Markdown, reported zero cost with token-only usage, and differed between nested and top-level error shapes. It skipped malformed UTF-8-compatible lines but both helper CLIs raised errors on invalid UTF-8. [scripts/lib.sh:186](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:186), [scripts/lib.sh:209](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:209), [scripts/codex_jsonl_to_compat.py:16](repos/AY-Liu__multi-agent-runner/scripts/codex_jsonl_to_compat.py:16), [scripts/codex_jsonl_to_compat.py:83](repos/AY-Liu__multi-agent-runner/scripts/codex_jsonl_to_compat.py:83), [scripts/codex_retry_policy.py:34](repos/AY-Liu__multi-agent-runner/scripts/codex_retry_policy.py:34). |
| `malformed.py status_matrix` | A Claude compatibility object with no fields was classified as done and produced Markdown `{}`. A success with ID but no text also reached done. A literal string `"false"` in the error field was truthy and reached error. A JSON array produced an error projection and no exit record. The controls held a normal worker launch and replaced only the payload. [scripts/lib.sh:192](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:192), [scripts/lib.sh:689](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:689), [scripts/lib.sh:738](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:738). |
| `processes.py stop`, `processes.py term_resistant`, and `observability.py stop_on_timeout` | Direct stop action returned 0 with no stop message and no state change. Global stop removed the PID record, reported idle, and found the ordinary provider but missed the provider's harmless sleep child. A TERM-resistant provider wrote a new result after stop returned. With a real periodic wake at 182.031 s, a leader-issued stop also left its worker live and tracked until the fixture was released. [scripts/execute_decisions.sh:98](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:98), [stop.sh:25](repos/AY-Liu__multi-agent-runner/stop.sh:25), [stop.sh:46](repos/AY-Liu__multi-agent-runner/stop.sh:46). |
| `processes.py pipe_eof` and `concurrency.py term_parent` | A completed leader returned 0 in **0.415 s**, with EOF at **10.091 s** and only orphaned `sleep 10` holding the write end. TERM sent to the entry PID alone returned -15 while the harness and provider remained alive and subsequently completed the task. [scripts/wake_leader.sh:179](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:179), [scripts/wake_leader.sh:200](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:200), [run.sh:93](repos/AY-Liu__multi-agent-runner/run.sh:93). |
| `start_gap.py forced\|baseline` | Blocking the launcher after it published `running` and before PID creation yielded terminal `error` and a leftover PID file despite a good later result. The baseline recovered the same result as `done` and removed the PID. A witness worker completed in both. [scripts/launch_subagent.sh:54](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:54), [scripts/launch_subagent.sh:103](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:103), [scripts/harness.sh:103](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:103). |
| `schedule_probe.py sample` | Twenty independent unfaulted launch cases, at most four concurrently, used the ordinary launcher and a short fake CLI success. All 20 reached done with no logged missing-PID gap. Paired with the gated case, this establishes the possible failure path and the positive baseline under this workload. [scripts/launch_subagent.sh:54](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:54), [scripts/harness.sh:103](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:103). |
| `concurrency.py duplicate`, `concurrent_boot`, and `admission` | Same-name launch and resume both ran, with the latter starting fresh because there was no stored session. The tracked second attempt was archived and marked done while the earlier one was still live. On release, the earlier result overwrote the latest output while the session and archive still referred to the second. A gated interleaving allowed two concurrent public supervisors and two live leaders for a single root. A separate 24-name batch launched all 24 concurrently before its gate release, with 24 PID claims and 24 instruction files. [scripts/execute_decisions.sh:74](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:74), [scripts/launch_subagent.sh:94](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:94), [scripts/launch_subagent.sh:103](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:103), [scripts/harness.sh:154](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:154). |
| `concurrency.py state_writes` and `zombie` | Under controlled overlapping writes, a confirmed PID value of 72 reverted to 51 when a delayed read-modify-write committed. After a simulated crash between truncation and serialization, the status was zero bytes, the reader returned blank and exit 0, and the next write created only a PID. An unreaped recorded zombie was retained as running at bootstrap until reaped. [scripts/lib.sh:331](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:331), [scripts/lib.sh:344](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:344), [scripts/harness.sh:43](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:43). |
| `recovery.py reconciliation direct\|public\|public-no-pid` | Public restart with dead PID files mapped all six to idle and archived nothing. Direct start and public start with missing PID files agreed on the fixture partition: valid normalized output done, malformed, result-less, and content-only normalized results error, raw-only and absent normalized output idle. A standalone conversion of the raw-only fixture returned valid result text. [run.sh:93](repos/AY-Liu__multi-agent-runner/run.sh:93), [stop.sh:25](repos/AY-Liu__multi-agent-runner/stop.sh:25), [scripts/stop_state.py:15](repos/AY-Liu__multi-agent-runner/scripts/stop_state.py:15), [scripts/harness.sh:53](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:53). |
| `recovery.py foreign` and `corrupt_stop` | Public Codex restart wrote `claude-prior-id` to `session_id.codex` from an interrupted Claude result, then passed that ID to fake Codex resume. A malformed status in the first stop iteration removed that PID file, exited 1, and left both a later PID claim and the leader guard untouched. A valid status with the same other inputs allowed stop to clear them. [scripts/harness.sh:69](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:69), [scripts/lib.sh:637](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:637), [stop.sh:39](repos/AY-Liu__multi-agent-runner/stop.sh:39), [scripts/stop_state.py:11](repos/AY-Liu__multi-agent-runner/scripts/stop_state.py:11). |
| `restart_live.py active direct\|public` | Killed just the live supervisor with SIGKILL and verified shell exit 137 while the original worker and wrapper remained live. Direct harness restart retained the same PID through native leader resume and collected the worker's output. Public restart resumed the leader but stopped the original worker first, settled to idle, and archived no work. [run.sh:93](repos/AY-Liu__multi-agent-runner/run.sh:93), [stop.sh:25](repos/AY-Liu__multi-agent-runner/stop.sh:25), [scripts/harness.sh:43](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:43). |
| `restart_live.py bad_launch` and `reset_drain` | An empty agent launch yielded a temporary file, decision exit 0, and no worker or visible usage error. Direct launcher exit was 1 with usage. Reset returned 0 while a TERM-resistant fixture remained live and cleared its agent files. On release that old provider wrote a new artifact under the freshly reset project output directory. [scripts/execute_decisions.sh:74](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:74), [scripts/launch_subagent.sh:16](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:16), [stop.sh:25](repos/AY-Liu__multi-agent-runner/stop.sh:25), [run.sh:85](repos/AY-Liu__multi-agent-runner/run.sh:85). |
| `sessions.py round_trip`, `worker_handoff`, and `legacy_stream` | Native IDs across A→B→A were fresh, fresh, old A. The first switch carried A's text, and the return prompt omitted B's text. A real launcher inserted the new instruction under “Previous instruction summary.” The standalone Claude stream helper's five-key result shape was classified as Codex for legacy-ID migration, while adding the documented result-type marker classified the same fixture as Claude. [scripts/lib.sh:426](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:426), [scripts/lib.sh:497](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:497), [scripts/lib.sh:588](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:588), [scripts/launch_subagent.sh:54](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:54), [scripts/stream_processor.py:114](repos/AY-Liu__multi-agent-runner/scripts/stream_processor.py:114). |
| `contracts.py same_stamp` | Fixed only the archive clock to one UTC second. Two provider calls yielded one same-stem JSON/JSONL pair, consisting of Claude's normalized output and Codex's raw output. In the naturally fast three-call switch control all normalized outputs also occupied one history filename. [scripts/lib.sh:68](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:68), [scripts/lib.sh:725](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:725), [providers/codex/provider.sh:91](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:91). |
| `provider_edges.py cwd` and `argv_limit` | Both fake subprocesses had the caller CWD. Codex received the root option and placed its decision at the harness root. Claude had no root option, wrote the decision in the caller directory and the harness substituted an empty decision. A 118,001-byte note passed with a 129,178-byte single prompt argument in the confirming run. A 128,001-byte note returned 126 with E2BIG diagnostics in leader stderr and zero CLI starts. [run.sh:11](repos/AY-Liu__multi-agent-runner/run.sh:11), [scripts/wake_leader.sh:128](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:128), [providers/codex/provider.sh:50](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:50), [providers/claude/provider.sh:37](repos/AY-Liu__multi-agent-runner/providers/claude/provider.sh:37), [scripts/lib.sh:302](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:302). |
| `provider_edges.py reset_preflight`, `contracts.py cleanup_tmp`, and `reset_stop_args` | Reset without a discovered CLI returned 1 and preserved the fixture output. With a stub it returned 0 and deleted the output with zero provider calls. Single-wake with a launch left a completed worker `running`. Reset removed the agent data and the private instruction file in the external-for-project `TMPDIR` remained. An unknown provider on public stop logged an error, then removed the synthetic PID file and returned 0 with missing helper errors. [run.sh:61](repos/AY-Liu__multi-agent-runner/run.sh:61), [run.sh:76](repos/AY-Liu__multi-agent-runner/run.sh:76), [scripts/execute_decisions.sh:74](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:74), [scripts/lib.sh:20](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:20), [scripts/lib.sh:56](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:56), [stop.sh:21](repos/AY-Liu__multi-agent-runner/stop.sh:21). |
| `blocked.py` | While leader call 2 was held, the other worker wrote a good result and its wrapper disappeared. At 8, 60, and 184 seconds after leader start, tick count was still 1, worker state was `running`, and no third leader existed. Releasing the leader allowed collection and a third wake by 189.776 s. [scripts/harness.sh:154](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:154), [scripts/harness.sh:226](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:226). |
| `observability.py live_projection`, `contracts.py scan_cost`, and `malformed.py monitor_truncation` | The periodic status showed 44 B from old normalized output while the current Codex stream contained 4,224 B. The new result appeared on completion. At 0/12/48 seeded agents, the leader performed 0/48/192 status reads and passed prompts of 10,962/21,518/53,162 bytes. Two distinct stderr lines sharing the first 80 characters were collapsed by the monitor. A later distinct prefix was displayed. [scripts/harness.sh:249](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:249), [scripts/wake_leader.sh:31](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:31), [scripts/lib.sh:111](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:111). |

**Limitations.** These are black-box and fault-injection tests of the local control plane with proposed protocol payloads, plus direct tests of parser helpers. They establish process instances, arguments, status, and side effects in an isolated Linux namespace. They do not measure live provider response quality, authentication or quotas, the CLI versions' acceptance of these arguments, native sessions after machine restart, failure event ordering in each product, actual billing, or the quality of model-crafted plans. Backoff interception measures requested waits, and gating controls establishes that a race is possible without estimating its frequency. The 24-agent sample is an admission test. Synthetic roster durations include local interpreter startup and are environment-specific. The real 180-second and foreground-blocking tests used the clock with no synthetic sleep. Filesystem fault injection stopped a writer in an open file window, leaving actual power-loss behavior, multi-host reliability, and portability outside these results.

**Independent replay.** The archive and fixture files were rebuilt from the runnable blocks in §9. In the replay, both unittest discoveries, syntax and limit controls, the complete primary fixture matrix, and the selected Python 3.12 repeats completed with exit 0 from the assertion driver. The idle heartbeat repeated at 181.370 s, the stuck-leader intervention repeated with collection stalled through 184.000 s, and the timeout stop action again left its worker active at 181.984 s. A separate stream capture held a successful entry's pipe until 10.056 s even though it returned in 0.314 s. The final pipe-backed repeats measured 181.395 s between heartbeat CLI starts and 191.511 s through output EOF, and 30.032 s between Claude retry CLI starts and 40.063 s through output EOF.

## 7. Measurement audit for every negative or surprising result, including alternate commands or code-path checks used to rule out setup mistakes.

| Surprise or negative | Audit and alternate evidence |
| --- | --- |
| Entry returned permission denied | Checked actual executable modes with `stat` and Git's tree metadata. Inside the same snapshot and namespace, explicit Bash launched the underlying script and completed both healthy adapter paths. Executing the same bytes through Bash isolates the difference to the checked-in mode. The syntax sweep put each shell file in script position. A deliberately invalid second positional file tested with `bash -n run.sh bad.sh` returned 0, and by itself returned 2. [README.md:24](repos/AY-Liu__multi-agent-runner/README.md:24), [README.md:253](repos/AY-Liu__multi-agent-runner/README.md:253), [run.sh:1](repos/AY-Liu__multi-agent-runner/run.sh:1), [stop.sh:1](repos/AY-Liu__multi-agent-runner/stop.sh:1). |
| Normal workflow initially appeared to time out | The first capture used a pipe and timed out even though the terminal artifact and finish log were already present. A file-backed output and `Popen.wait` separated supervisor exit from stream EOF. A clean repeat achieved both end-to-end workflows and the dedicated probe matched the exact output pipe inode to the orphaned `sleep 10`. This explains the extra ~10 seconds in the natural heartbeat and natural retry pipe timings. It is a process I/O lifetime defect, separate from healthy task completion. [scripts/wake_leader.sh:179](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:179), [scripts/wake_leader.sh:200](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:200), [scripts/execute_decisions.sh:93](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:93). |
| New fenced output was ignored or became empty | Read the saved Markdown, both decision files and return codes, and the console messages. An old timestamp suppressed the extractor. A missing or invalid timestamp reached the extractor, which printed both success and overwrite warnings. The exact same decision written directly worked. A minimal Python `try: raise SystemExit(0)` with bare `except:` reproduced the fallthrough mechanism. Python 3.12 repeated the 3.14 result. [scripts/wake_leader.sh:223](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:223), [scripts/wake_leader.sh:246](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:246), [scripts/wake_leader.sh:260](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:260). |
| Partial decision batch | The fixture controlled role order and read back the original role content, its truncation, and the first and third action footprints. The Bash exit was 1 with an inline-Python `TypeError`, so the failure was visible in the executor pipe and still had committed effects. An otherwise valid direct action afterward executed normally on the same filesystem. [scripts/execute_decisions.sh:58](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:58), [scripts/execute_decisions.sh:65](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:65), [scripts/execute_decisions.sh:121](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:121). |
| Successful continuation lost supervision | First wrote a real terminal marker, then supplied a new inbox line and a genuine nonterminal decision. Verified the same sentinel mtime, leader prompt, worker liveness at supervisor exit, and late artifact write. Removed only the old marker in the disposable copy before the next controlled continuation. Tested fresh premature termination separately to distinguish sentinel reuse from unconditional done-first handling. [run.sh:93](repos/AY-Liu__multi-agent-runner/run.sh:93), [scripts/harness.sh:209](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:209), [scripts/execute_decisions.sh:34](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:34). |
| Retry missed explicit transient failures | Used the same synthetic exit code, stdout/event and stderr with isolated subprocesses. Only changed the invocation context to a Bash conditional for the positive retry control. Repeated both adapters with two Python versions. The standalone Codex classifier and guarded adapter did retry. The repo's Claude stubs and the natural Claude success control use a process exit of 0 for the 429 payload, which explains why those pass. The public harness's log and persisted leader flag show where its own `errexit` aborts. [tests/test_claude_retry.py:35](repos/AY-Liu__multi-agent-runner/tests/test_claude_retry.py:35), [scripts/lib.sh:250](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:250), [scripts/lib.sh:302](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:302), [scripts/harness.sh:165](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:165). |
| Exit 42 reported as done or a failed attempt reused old state | Worker fake trace recorded exit 42 before termination and fresh stderr. Held workers until PID publication and compared a clean exit and a fresh explicit failure envelope. Codex policy was reachable separately. In the repeat case, inspected different raw and normalized generations and the prior exit-code/pointer files. The observed state follows the compatibility flag or old compatible result. No provider quota pressure or failure to launch was involved. [scripts/launch_subagent.sh:94](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:94), [providers/codex/provider.sh:76](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:76), [scripts/lib.sh:735](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:735). |
| Missing session aborted part of a successful path | Checked valid direct decision, normalized output and CLI exit 0 before the harness failure. At bootstrap, verified archival happened before the failure. Adding a session string to the same worker record fixed the initialization. Compared default Bash subshell behavior with explicitly enabled `inherit_errexit` on live worker collection, with both option states printed by Bash. That accounts for different outcomes from the same helper in different caller contexts. [scripts/lib.sh:637](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:637), [scripts/lib.sh:735](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:735), [scripts/wake_leader.sh:213](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:213), [scripts/harness.sh:226](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:226). |
| Backoff budget, false retry and classifier discrepancies | Kept the real retry functions and counted fake CLI starts. The bounded test replaced only sleep with a trace and supplied success on call 13. The natural 30-second delay checked the first live-backoff path independently. For Claude, changed only two harmless stderr words around the literal `rate` match. For Codex, held the useful event sequence and switched a nested or top-level failure or the exit status. Confirmed malformed lines and invalid UTF-8 separately with direct Python invocations. [scripts/lib.sh:186](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:186), [scripts/lib.sh:267](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:267), [scripts/codex_retry_policy.py:51](repos/AY-Liu__multi-agent-runner/scripts/codex_retry_policy.py:51), [scripts/codex_jsonl_to_compat.py:64](repos/AY-Liu__multi-agent-runner/scripts/codex_jsonl_to_compat.py:64). |
| Stop action no-op or global stop left work behind | Verified both path constructions, names and PID records, and ran public stop with the same active regular provider afterward. Logged the wrapper, provider and harmless child PIDs and their actual group from `os.getpgid`. Group TERM on the measured fixture group stopped the leftover child. The signal-resistant stub acknowledged TERM and still produced a result on release. The naturally scheduled stop case checked the exact user-loop path. TERM to the top entry PID alone was a separate check of parent-child ownership. No outside process was eligible in the PID namespace. [scripts/execute_decisions.sh:98](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:98), [scripts/lib.sh:11](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:11), [stop.sh:25](repos/AY-Liu__multi-agent-runner/stop.sh:25), [stop.sh:46](repos/AY-Liu__multi-agent-runner/stop.sh:46), [run.sh:93](repos/AY-Liu__multi-agent-runner/run.sh:93). |
| Race and stale state findings | Positive and negative paired controls used the same provider/input and changed the allowed interleaving. For publication, intercepted just the existing instruction-summary setter and waited for the real loop to process the missing PID before letting it resume. For concurrent boots, coordinated the two real empty process snapshots and guard reads before releasing them. For write integrity, paused the actual Python `open` call before or after truncation. Sequential writes preserved both keys, and a fresh write after an interrupted truncate rebuilt only the requested key. No frequency estimate was inferred from shims. [scripts/launch_subagent.sh:54](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:54), [scripts/harness.sh:103](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:103), [scripts/harness.sh:154](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:154), [scripts/lib.sh:344](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:344). |
| Default launch sample and shipped demo | Ordinary working cases provide a check on the effect of the injected scheduling gap. The 20-test sample had no gap with the reported workload and small roster. The demo check used the actual prompt inputs and named groups while the deterministic provider supplied all decisions and artifacts. These controls support the ordinary execution path without attributing planner quality or a production race rate to a scripted provider. [scripts/harness.sh:92](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:92), [examples/mini-escape-room/leader.md:29](repos/AY-Liu__multi-agent-runner/examples/mini-escape-room/leader.md:29). |
| PID disappeared, was reused, or looked live after exit | For observed true exits used process-state inspection plus CLI exit records, and controlled when the collector ran. Used a deliberate unreaped harmless child to demonstrate the semantic limit of `kill -0` and reaped it before the positive recovery. The repo makes no identity check beyond a numeric PID. Wrong-PID signaling from reuse is a design risk inferred from that predicate and was not injected. [scripts/harness.sh:43](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:43), [scripts/lib.sh:144](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:144), [stop.sh:25](repos/AY-Liu__multi-agent-runner/stop.sh:25). |
| Restart and provider attribution gaps | Tested identical recovery fixture shapes through direct loop entry, public entry with PID files, and public entry without them. The raw-only Codex case normalized successfully by direct command. The malformed-status stop test repeated after repairing only the corrupt JSON. For provider misattribution, preserved the old Claude type and scoped file and read the generated scoped Codex file and the exact native resume argument. This establishes provenance loss independently of live session acceptance. [scripts/harness.sh:34](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:34), [stop.sh:39](repos/AY-Liu__multi-agent-runner/stop.sh:39), [scripts/lib.sh:637](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:637), [providers/codex/provider.sh:51](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:51). |
| Live restart, early launcher rejection, and reset return | The worker/crash cases start a real public loop and SIGKILL only its harness child, with exact process ancestry from `/proc`. The entry exits 137 and the worker remains alive. Comparing direct and public successors identifies the stop-before-reconcile behavior. The rejected launch matched the actual empty-name check with a direct call. The reset case records ignored TERM, survival, directory deletion, and a file written after reset on gate release. The ordinary finished-worker reset confirmed directory deletion in the same sandbox. [scripts/harness.sh:43](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:43), [run.sh:85](repos/AY-Liu__multi-agent-runner/run.sh:85), [scripts/launch_subagent.sh:16](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:16), [scripts/execute_decisions.sh:94](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:94), [stop.sh:25](repos/AY-Liu__multi-agent-runner/stop.sh:25). |
| Compatibility flags and output types | Held exit 0 and the same launch lifecycle, exercised an empty object, missing text, string error value, and array. The retained normalized data, Markdown, and exit-code file distinguish unchecked field truthiness from an adapter failure reading a non-object. The bootstrap result-less test uses a distinct success predicate, which explains the asymmetry. [scripts/lib.sh:192](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:192), [scripts/lib.sh:689](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:689), [scripts/lib.sh:738](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:738), [scripts/harness.sh:64](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:64). |
| Old Markdown, handoff summary, and archive collision | Compared captured prompt strings, provider arguments, normalized result, Markdown, native scoped IDs and raw archives. Codex wrote a fresh last-message file in its normal control, while Claude's no-op normalization left the old Markdown. Compared A→B and B→A with explicit provider-specific IDs and a new instruction passed through the real launcher. Added a single discriminating type marker to the legacy stream output to change its classification. Natural archive collision was confirmed with a shim affecting only `ts_file`, yielding raw Codex and normalized Claude files with the same stem. [providers/codex/provider.sh:50](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:50), [providers/claude/provider.sh:61](repos/AY-Liu__multi-agent-runner/providers/claude/provider.sh:61), [scripts/lib.sh:426](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:426), [scripts/lib.sh:588](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:588), [scripts/lib.sh:689](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:689), [scripts/lib.sh:725](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:725). |
| Wrong CWD or oversized context | The working-directory case began from a sandbox sibling and captured provider process CWD and file destinations, with the same starter role and decision. Codex's fake deliberately honored the explicit root option. Claude's fake used inherited CWD. The first oversized-note run looked for E2BIG in top-level output and missed the diagnostic. A fresh repeat inspected `agents/leader/stderr.log`; shorter payloads started the same fake. Direct `execve` via Python and a system binary accepted one 131,071-byte argument and two 70,000-byte arguments, and returned E2BIG for one 131,072-byte argument. The 2,097,152-byte `ARG_MAX` is aggregate. The failure is per argument at this host. [providers/codex/provider.sh:50](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:50), [providers/claude/provider.sh:57](repos/AY-Liu__multi-agent-runner/providers/claude/provider.sh:57), [scripts/wake_leader.sh:167](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:167), [scripts/lib.sh:302](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:302). |
| Status line and monitor visibility | Compared raw stream length, normalized generation, and console after a real sixth tick and before release of the worker. The stream grew while the headline stayed at the old compatibility size, and the normal completion updated the normalized result. Positive distinct-prefix control confirmed the stderr monitor suppresses messages after truncation rather than due to data loss. Provider event delivery to the leader is snapshot-based. [scripts/harness.sh:249](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:249), [scripts/lib.sh:111](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:111), [scripts/wake_leader.sh:49](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:49). |
| Resource and cleanup expectations | Roster test counted actual interpreter calls via a transparent forwarding shim and headroom far below the separate exec limit. Fan-out measured concurrently live PIDs and exact instruction file count before opening fixture gates. Once/reset controls followed an actual completed worker, checked the PID evidence, runtime removal, and the known private temp path. The no-CLI reset control used system-only PATH and the positive setup used the same code and files with a discoverable fake. [scripts/wake_leader.sh:31](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:31), [scripts/execute_decisions.sh:74](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:74), [run.sh:61](repos/AY-Liu__multi-agent-runner/run.sh:61), [run.sh:76](repos/AY-Liu__multi-agent-runner/run.sh:76), [scripts/lib.sh:56](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:56). |
| Heartbeat failed to wake a stuck foreground call | The idle control woke on wall time in normal operation. During the blocked leader control the late worker's PID was already gone and good output already present, with no tick or decision progress through 184 seconds. The deliberate gate had over 200 seconds of headroom, and release produced an immediate ordinary recovery path. The completed and in-flight controls isolate the synchronous call site from clock, worker availability, and polling latency. [scripts/harness.sh:139](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:139), [scripts/harness.sh:167](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:167), [scripts/harness.sh:226](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:226). |

## 8. Post-mortem: design pressures, accumulated tradeoffs, likely failure modes, and the highest-leverage improvements.

The repository's stated pressures are small deployment, local CLI reuse, editable agent policy, and periodic leadership. The implementation gets there with Bash processes, inline standard-library Python, and a directory of readable artifacts. The source and demo indicate a manual operating model with a cooperative leader, a small known worker roster, and a human available to inspect a bad run. In that model, raw logs and native sessions make a short pipeline easy to steer. As runs become longer, the cost of the same simplicity surfaces at the joints between model-issued actions, published state, and externally timed process effects. [README.md:10](repos/AY-Liu__multi-agent-runner/README.md:10), [README.md:12](repos/AY-Liu__multi-agent-runner/README.md:12), [README.md:178](repos/AY-Liu__multi-agent-runner/README.md:178), [examples/mini-escape-room/leader.md:29](repos/AY-Liu__multi-agent-runner/examples/mini-escape-room/leader.md:29).

1. **Process failure can erase the evidence needed to recover.** An interactive CLI was promoted to a background workflow actor, while Bash treats a nonzero status as a reason to leave the actor and its caller. The status and normalization steps are later statements. The background wrapper is orphaned and observed by PID, which leaves the collector without a collected process exit event. The collector then trusts available mutable result files. The observed false-success chain is CLI exit 42 → shell leaves before logging it → collector sees no exit code or an older record → compatibility flags favor success → state becomes `done`. If multiple attempts share filenames, even an explicit new error can be concealed by a retained success. [scripts/lib.sh:38](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:38), [scripts/lib.sh:298](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:298), [scripts/launch_subagent.sh:94](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:94), [providers/codex/provider.sh:76](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:76), [scripts/lib.sh:738](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:738).
2. **Command intent and committed state share mutable filenames.** A single operator can inspect or replace them easily. After a crash, repeated model wake, or partial write, the system cannot tell which action batch or attempt the file describes. The runner uses timestamp presence as a decision test and UTC seconds as archive names. It has no epoch or sequence number for either. The observed failures include reapplying an old action, leaving an already-applied prefix after a validation failure, losing a committed state field after stale read-modify-write, and pairing artifacts from different providers at one timestamp. A familiar name should remain the display identity while decisions and executions receive unique durable identities. [scripts/wake_leader.sh:223](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:223), [scripts/execute_decisions.sh:58](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:58), [scripts/lib.sh:344](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:344), [scripts/lib.sh:725](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:725).
3. **A synchronous leader couples planning availability to supervision.** When the provider returns quickly, the serial boundary simplifies decisions. Under a hung call or retry loop, the polling loop cannot collect independently completed workers or even update tick information. The experiment held a foreground call beyond 180 seconds and observed exactly that. Scheduling, subprocess ownership and result ingestion should keep making progress while the model works. A separate budget and single-flight policy can preserve serialized decisions. [scripts/harness.sh:154](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:154), [scripts/harness.sh:226](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:226), [scripts/lib.sh:242](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:242), [scripts/lib.sh:298](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:298).
4. **The ownership model developed around PIDs rather than jobs.** An async shell layered under another launcher allows a simple detached worker but leaves no authoritative object for process group, identity, deadline, outcome, or acknowledged cancellation. The two stop entry points drifted on path construction and scope. Startup now performs best-effort cleanup before some recovery steps, while a prior done flag persists across tasks. The result is uncollected live work, stale ownership records, and incompatible restart paths. A supervisor should explicitly own or reconcile each attempt before replacing it. [scripts/execute_decisions.sh:94](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:94), [scripts/launch_subagent.sh:103](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:103), [scripts/execute_decisions.sh:98](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:98), [stop.sh:25](repos/AY-Liu__multi-agent-runner/stop.sh:25), [run.sh:93](repos/AY-Liu__multi-agent-runner/run.sh:93), [scripts/harness.sh:34](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:34).
5. **Adapter portability was added through a shared shape with missing provenance and authority.** The existing integration can keep native sessions and use local handoff summaries. The current provider often stands in for the provider that produced persisted data. Legacy inference, mismatched Markdown generation, and opaque exit/error states then become scheduling bugs. Harden the handoff with explicit producer metadata, attempt ownership, and a typed adapter result. Select one source of truth for the Markdown, and carry traversable provider-to-provider checkpoints. [scripts/lib.sh:394](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:394), [scripts/lib.sh:637](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:637), [scripts/lib.sh:689](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:689), [providers/codex/provider.sh:76](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:76), [providers/claude/provider.sh:61](repos/AY-Liu__multi-agent-runner/providers/claude/provider.sh:61).

The largest reliability win is to add an owned, bounded attempt lifecycle and an acknowledged, wake-scoped decision path. Both changes can retain a local CLI workflow and readable status projections. Cosmetic monitoring or more elaborate leader prompts would leave the observed stale-generation and process-exit failures in place. §10 lists concrete acceptance checks.

The least disruptive implementation is a single local supervisor with attempt-specific directories and a durable task/decision ledger. A Bash adapter can remain the CLI invocation layer while a caller owns process groups, applies deadlines, and writes a complete result envelope. A small standard-library store or locked append-only log can retain a launch intent before spawning, then record process identity and outcome. After an interruption between spawning and recording ownership, reconciliation should identify the existing attempt or make the uncertainty visible before issuing another launch. Atomic file replacement limits torn state projections. It does not make provider side effects transactional, so action and attempt IDs also need an idempotency or explicit re-admission policy. [scripts/execute_decisions.sh:74](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:74), [scripts/launch_subagent.sh:94](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:94), [scripts/lib.sh:344](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:344), [scripts/harness.sh:34](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:34).

## 9. Evidence appendix with local file/line references and commands.

### Source map

| What to inspect | Pin-local anchors |
| --- | --- |
| Public entry, soft stop, and reset | [required inputs](repos/AY-Liu__multi-agent-runner/run.sh:31), [provider preflight](repos/AY-Liu__multi-agent-runner/run.sh:61), [modes](repos/AY-Liu__multi-agent-runner/run.sh:76), [agent PID handling](repos/AY-Liu__multi-agent-runner/stop.sh:25), [stray scan](repos/AY-Liu__multi-agent-runner/stop.sh:46), [runtime deletion](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:56), [soft-stop transition](repos/AY-Liu__multi-agent-runner/scripts/stop_state.py:15) |
| Scheduler and state machine | [bootstrap](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:23), [completion scan](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:92), [wake trigger](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:130), [foreground wake](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:154), [termination and tick](repos/AY-Liu__multi-agent-runner/scripts/harness.sh:215), [agent state transition](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:677) |
| Planner and dispatcher contract | [decision protocol](repos/AY-Liu__multi-agent-runner/leader.md:24), [long-running work](repos/AY-Liu__multi-agent-runner/leader.md:88), [runtime schema](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:63), [prompt assembly](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:112), [decision recovery](repos/AY-Liu__multi-agent-runner/scripts/wake_leader.sh:226), [action execution](repos/AY-Liu__multi-agent-runner/scripts/execute_decisions.sh:58) |
| Worker lifecycle and transport | [publish running](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:54), [wrapper and monitor](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:65), [provider call and exit marker](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:94), [PID publication](repos/AY-Liu__multi-agent-runner/scripts/launch_subagent.sh:103), [result collection](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:717), [Codex envelope](repos/AY-Liu__multi-agent-runner/scripts/codex_jsonl_to_compat.py:64) |
| CLI boundary and native sessions | [provider selection](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:20), [Codex invocation](repos/AY-Liu__multi-agent-runner/providers/codex/provider.sh:32), [Claude invocation](repos/AY-Liu__multi-agent-runner/providers/claude/provider.sh:28), [legacy inference](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:394), [scoped session lookup](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:497), [handoff](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:524), [session commit](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:637) |
| Retry and diagnostics | [monitor deduplication](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:94), [Claude classifier](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:170), [Claude backoff](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:220), [Codex backoff](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:290), [Codex classifier](repos/AY-Liu__multi-agent-runner/scripts/codex_retry_policy.py:51), [standalone event formatter](repos/AY-Liu__multi-agent-runner/scripts/stream_processor.py:66) |
| Data persistence and test scope | [JSON read](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:331), [JSON rewrite](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:344), [Markdown projection](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:689), [archive name](repos/AY-Liu__multi-agent-runner/scripts/lib.sh:725), [runtime artifact paths](repos/AY-Liu__multi-agent-runner/README.md:241), [fallback test adapter](repos/AY-Liu__multi-agent-runner/tests/test_claude_retry.py:58), [legacy handoff test](repos/AY-Liu__multi-agent-runner/tests/test_provider_session_handoff.py:57) |

### Snapshot checks and offline runner

The shell blocks below operate on disposable archive copies only. The original pin is read with Git. The `/lab` mount contains the fixture copies and their temporary directories, while `/source` is the archive mounted read-only. The clean environment intentionally excludes the user's Bash startup files and authenticated CLI binaries. The network and process namespaces are private. Use a fresh lab per complete run, or use a new `REVIEW_CASE_SUFFIX` to repeat a named case in the same lab.

~~~~bash
review_root='$HOME/.t3/scratch/2026-11-18-spend-a-million-tokens-or-d93b80f1'
review_repo="$review_root/repos/AY-Liu__multi-agent-runner"
review_head='e2fe272625e4d5aeafaa18e317b8c1c5e2da38bd'
date -u +'%F %T.%N UTC'
git -C "$review_repo" rev-parse HEAD HEAD^{tree}
test "$(git -C "$review_repo" rev-parse HEAD)" = "$review_head"
GIT_OPTIONAL_LOCKS=0 git -C "$review_repo" status --porcelain=v1 --untracked-files=all --ignored=matching
git -C "$review_repo" ls-tree "$review_head" -- run.sh stop.sh
review_lab=$(mktemp -d -p "$review_root" .ay-liu-runner-repeat.XXXXXXXX)
mkdir -p "$review_lab/source" "$review_lab/tmp" "$review_lab/controls"
git -C "$review_repo" archive "$review_head" | tar -xf - -C "$review_lab/source"

review_offline() {
  bwrap --die-with-parent --unshare-user --unshare-pid --unshare-net --clearenv \
    --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/lib /lib \
    --symlink usr/lib /lib64 --proc /proc --dev /dev \
    --bind "$review_lab" /lab --ro-bind "$review_lab/source" /source \
    --setenv PATH /usr/bin --setenv TMPDIR /lab/tmp --setenv TZ UTC \
    --setenv PYTHONDONTWRITEBYTECODE 1 \
    --setenv REVIEW_CASE_SUFFIX "${REVIEW_CASE_SUFFIX:-}" \
    --chdir /source -- "$@"
}

review_offline /usr/bin/bash -c '
  set -e
  test "${HOME-unset}" = unset
  test ! -e $HOME
  ! command -v codex
  ! command -v claude
  cat /proc/net/route
  ps -o pid,ppid,comm -e
'
review_offline /usr/bin/timeout 30s /usr/bin/python3 -m unittest discover -v -s tests -p 'test_*.py'
review_offline /usr/bin/bash -c '
  for script in run.sh stop.sh scripts/*.sh providers/*/provider.sh; do
    bash -n "$script" || exit
    printf "bash -n PASS %s\n" "$script"
  done
  python3 -c "from pathlib import Path; files=[*Path(\"scripts\").glob(\"*.py\"), *Path(\"tests\").glob(\"*.py\")]; [compile(p.read_bytes(),str(p),\"exec\") for p in files]; print(len(files))"
'
review_offline /usr/bin/bash -c '
  stat -c "%a %n" run.sh stop.sh
  ./run.sh --once; run_rc=$?
  ./stop.sh; stop_rc=$?
  printf "direct mode return codes %s %s\n" "$run_rc" "$stop_rc"
  test "$run_rc" -eq 126 && test "$stop_rc" -eq 126
'
review_offline /usr/bin/bash -c '
  bad="$TMPDIR/bad-syntax-control.sh"
  printf "%s\n" "if (" > "$bad"
  bash -n run.sh "$bad"; first=$?
  bash -n "$bad"; second=$?
  printf "syntax control statuses %s %s\n" "$first" "$second"
  test "$first" -eq 0 && test "$second" -eq 2
'
review_offline /usr/bin/python3 - <<'PY'
import errno
import subprocess
for chunks in ([131071], [131072], [70000, 70000]):
    try:
        rc = subprocess.run(["/usr/bin/true", *("x" * n for n in chunks)],
                            check=True).returncode
        print(chunks, rc)
    except OSError as error:
        assert error.errno == errno.E2BIG
        print(chunks, "E2BIG", error.errno)
PY
review_offline /usr/bin/python3 - <<'PY'
try:
    raise SystemExit(0)
except:
    print("bare except suppresses SystemExit")
PY
~~~~

The 3.12 repeat used the same namespace settings and the explicit read-only interpreter mount below. The stub provider executable still used the system interpreter in that repeat. System Python, test interpreter, and the harness's child `python3` selection were thus distinguishable.

~~~~bash
review_python312="${REVIEW_PYTHON_312:-$HOME/.local/share/mise/installs/python/3.12.16}"
review_offline_py312() {
  bwrap --die-with-parent --unshare-user --unshare-pid --unshare-net --clearenv \
    --ro-bind /usr /usr --symlink usr/bin /bin --symlink usr/lib /lib \
    --symlink usr/lib /lib64 --proc /proc --dev /dev \
    --bind "$review_lab" /lab --ro-bind "$review_lab/source" /source \
    --ro-bind "$review_python312" /opt/python312 \
    --setenv PATH /opt/python312/bin:/usr/bin --setenv TMPDIR /lab/tmp --setenv TZ UTC \
    --setenv PYTHONDONTWRITEBYTECODE 1 --setenv REVIEW_RUNTIME_PATH /opt/python312/bin:/usr/bin \
    --setenv REVIEW_CASE_SUFFIX -py312 --chdir /source -- "$@"
}
review_offline_py312 /opt/python312/bin/python3 -m unittest discover -s tests -p 'test_*.py'
~~~~

### Reproduction commands

Place the enclosed fixtures in the lab by running the installation blocks below. Run the commands from the shell holding the `review_offline` function. Each case ends with assertion checks and prints a structured observation. The three roughly three-minute controls use real wall time, and can run in independent processes. The parameterized scan and fault controls use only the named fixtures.

~~~~bash
review_case() {
  review_script="$1"
  shift
  review_offline /usr/bin/python3 "/lab/controls/$review_script" "$@"
}
review_case flow.py codex
review_case flow.py claude
review_case flow.py decisions
review_case flow.py continuation
review_case flow.py early_done
review_case natural.py heartbeat
review_case natural.py claude
# Optional pipe-backed repeats for process-exit versus output-EOF timing.
review_case natural.py heartbeat pipe
review_case natural.py claude pipe
review_case blocked.py
review_case observability.py live_projection
review_case observability.py stop_on_timeout

for provider in codex claude; do
  review_case failure.py retry "$provider"
  review_case failure.py worker_exit "$provider"
  review_case provider_edges.py budget "$provider"
done
review_case failure.py no_session
review_case failure.py stale_worker
for control in stop term_resistant pipe_eof; do
  review_case processes.py "$control"
done
review_case start_gap.py forced
review_case start_gap.py baseline
for control in duplicate admission state_writes concurrent_boot term_parent zombie; do
  review_case concurrency.py "$control"
done
for entry in direct public public-no-pid; do
  review_case recovery.py reconciliation "$entry"
done
for control in empty_session foreign corrupt_stop; do
  review_case recovery.py "$control"
done
review_case restart_live.py active direct
review_case restart_live.py active public
review_case restart_live.py bad_launch
review_case restart_live.py reset_drain
for control in round_trip worker_handoff legacy_stream; do
  review_case sessions.py "$control"
done
for control in false_hit normalization cwd argv_limit reset_preflight; do
  review_case provider_edges.py "$control"
done
for control in errinherit same_stamp cleanup_tmp reset_stop_args scan_cost; do
  review_case contracts.py "$control"
done
review_case malformed.py status_matrix
review_case malformed.py monitor_truncation

review_offline_py312 /opt/python312/bin/python3 /lab/controls/failure.py retry codex
review_offline_py312 /opt/python312/bin/python3 /lab/controls/failure.py retry claude
review_offline_py312 /opt/python312/bin/python3 /lab/controls/flow.py decisions
review_offline_py312 /opt/python312/bin/python3 /lab/controls/concurrency.py state_writes
~~~~

### Fixture installation

<details>
<summary>lab.py</summary>

~~~~bash
cat > "$review_lab/controls/lab.py" <<'PY_EVAL'
from pathlib import Path
import json
import os
import shutil
import signal
import subprocess
import time

SOURCE = Path("/source")
TEMP = Path("/lab/tmp")
CONTROLS = Path("/lab/controls")
CASES = Path("/lab/cases")

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj) + "\n")

def read(path, default=None):
    try:
        return path.read_text()
    except FileNotFoundError:
        return default

def load(path, default=None):
    raw = read(path)
    return default if raw is None else json.loads(raw)

def fixture(name, plan, provider="codex"):
    name += os.getenv("REVIEW_CASE_SUFFIX", "")
    root = CASES / name
    shutil.copytree(SOURCE, root)
    write_json(root / "fixture.json", plan)
    bindir = root / "fake-bin"
    bindir.mkdir()
    for binary in ("codex", "claude"):
        (bindir / binary).symlink_to(CONTROLS / "fake_provider.py")
    tmp = TEMP / name
    tmp.mkdir()
    base_path = os.getenv("REVIEW_RUNTIME_PATH", "/usr/bin")
    env = {"PATH": f"{bindir}:{base_path}", "TMPDIR": str(tmp), "TZ": "UTC",
           "PYTHONDONTWRITEBYTECODE": "1",
           "CLAW_PROVIDER": provider, "MULTI_AGENT_PROVIDER": provider}
    return root, env

def spawn(root, env, *argv, cwd=None, pipes=False):
    kwargs = dict(cwd=cwd or root, env=env, stderr=subprocess.STDOUT, text=True,
                  start_new_session=True)
    if pipes:
        return subprocess.Popen(argv, stdout=subprocess.PIPE, **kwargs)
    seq = len(list(root.glob("harness-capture.*.log"))) + 1
    output = root / f"harness-capture.{seq}.log"
    with output.open("w") as log:
        p = subprocess.Popen(argv, stdout=log, **kwargs)
    p.review_output = output
    return p

def finish(proc, timeout=12):
    output = getattr(proc, "review_output", None)
    try:
        if output is not None:
            return proc.wait(timeout=timeout), read(output)
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if output is not None:
            proc.wait(timeout=3)
            out = read(output)
        else:
            out, _ = proc.communicate(timeout=3)
        raise AssertionError(f"timed out on {proc.args}: {out[-4000:]}")

def run(root, env, *argv, timeout=12, cwd=None):
    return finish(spawn(root, env, *argv, cwd=cwd), timeout=timeout)

def trace(root):
    lines = (read(root / "trace.jsonl") or "").splitlines()
    return [json.loads(line) for line in lines if line]

def starts(root):
    return [r for r in trace(root) if r["event"] == "start"]

def state(root, agent):
    return load(root / "agents" / agent / "status.json", {})

def wait_until(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.02)
    raise AssertionError(f"condition unmet after {timeout}s")

def proc_state(pid):
    raw = read(Path(f"/proc/{pid}/stat"))
    return raw.rsplit(")", 1)[-1].split()[0] if raw else "gone"

def proc_alive(pid):
    return proc_state(pid) not in ("gone", "Z", "X")

def decision(*actions, done=False):
    return {"done": done, "task_status": "done" if done else "running",
            "actions": list(actions), "message": "fixture decision"}

def action(kind, agent=None, **kwargs):
    result = {"type": kind, **kwargs}
    if agent:
        result["agent"] = agent
        if kind in ("launch", "resume"):
            result.setdefault("instruction", f"worker-id: {agent}")
    return result

def emit(label, **details):
    print(label, json.dumps(details, sort_keys=True, default=str), flush=True)
PY_EVAL
~~~~

</details>

<details>
<summary>fake_provider.py</summary>

~~~~bash
cat > "$review_lab/controls/fake_provider.py" <<'PY_EVAL'
#!/usr/bin/python3
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import sys
import time

args = sys.argv[1:]
provider = Path(sys.argv[0]).name
root = Path(args[args.index("-C") + 1]) if "-C" in args else Path.cwd()
prompt = args[-1]
match = re.search(r"(?:^|\n)worker-id: ([a-zA-Z0-9_-]+)", prompt)
agent = "leader" if "# HARNESS CONTRACT" in prompt else (match[1] if match else "smoke")
trace = root / "trace.jsonl"
config = json.loads((root / "fixture.json").read_text())

def emit(event, **extra):
    row = dict(event=event, agent=agent, provider=provider, monotonic=time.monotonic(),
               pid=os.getpid(), ppid=os.getppid(), pgid=os.getpgid(0), **extra)
    with trace.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.write(json.dumps(row) + "\n")

with trace.open("a+") as stream:
    fcntl.flock(stream, fcntl.LOCK_EX)
    stream.seek(0)
    attempt = 1 + sum(r["event"] == "start" and r["agent"] == agent
                      for r in map(json.loads, stream))
    resume = args[args.index("--resume") + 1] if "--resume" in args else (
        args[args.index("resume") + 1] if "resume" in args[:-1] else None)
    model = args[args.index("--model") + 1] if "--model" in args else None
    effort = next((arg.split("=")[-1].strip('"') for arg in args
                   if arg.startswith("model_reasoning_effort=")), None)
    stream.write(json.dumps(dict(event="start", agent=agent, provider=provider, attempt=attempt,
                                 monotonic=time.monotonic(), pid=os.getpid(), ppid=os.getppid(),
                                 pgid=os.getpgid(0), cwd=str(Path.cwd()), resume=resume, model=model,
                                 effort=effort, prompt_bytes=len(prompt.encode()))) + "\n")

seen = root / "seen"
seen.mkdir(exist_ok=True)
(seen / f"{agent}.{attempt}.txt").write_text(prompt)
plan = config.get(agent, config.get("*", []))
if attempt <= len(plan):
    step = plan[attempt - 1]
else:
    step = config.get("overflow", {"result": f"unexpected {agent} wake {attempt}", "exit": 73})
emit("configured", attempt=attempt)

if step.get("spawn_child"):
    import subprocess
    child = subprocess.Popen(["/usr/bin/sleep", "90"], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    emit("spawned-child", child_pid=child.pid, child_pgid=os.getpgid(child.pid))
if step.get("ignore_term"):
    signal.signal(signal.SIGTERM, lambda *_: emit("ignored-term", attempt=attempt))
if "write" in step:
    for relpath, data in step["write"].items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
if "decision" in step:
    path = root / "state/decisions/latest.json"
    decision = dict(step["decision"])
    decision.setdefault("timestamp", f"fixture-wake-{attempt}")
    path.write_text(json.dumps(decision) + "\n")
if "raw_decision" in step:
    (root / "state/decisions/latest.json").write_text(step["raw_decision"])
if step.get("touch_done"):
    (root / "state/done").touch()
if "live_events" in step:
    for event in step["live_events"]:
        print(json.dumps(event), flush=True)
if "gate" in step:
    limit = time.monotonic() + step.get("gate_timeout", 20)
    while not (root / step["gate"]).exists():
        if time.monotonic() > limit:
            emit("gate-timeout", attempt=attempt)
            sys.exit(78)
        time.sleep(0.015)
if "pause" in step:
    time.sleep(step["pause"])

if "write_after" in step:
    for relpath, data in step["write_after"].items():
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)

result = step.get("result", f"{agent}: attempt {attempt}")
sid = step.get("session", f"{provider}-{agent}-{attempt}")
error = step.get("error")
if "stderr" in step:
    print(step["stderr"], file=sys.stderr, flush=True)

if not step.get("silent"):
    if provider == "codex":
        if step.get("invalid_utf8"):
            sys.stdout.buffer.write(b"\xff\n")
        else:
            events = [{"type": "thread.started", "thread_id": sid},
                      {"type": "turn.started"}]
            if error:
                events.append({"type": "turn.failed", "message": error})
            else:
                events.extend([{"type": "item.completed", "item": {"type": "agent_message", "text": result}},
                               {"type": "turn.completed", "usage": {"input_tokens": 12, "output_tokens": 8}}])
            for event in step.get("events", events):
                print(json.dumps(event))
        if not step.get("no_md"):
            Path(args[args.index("--output-last-message") + 1]).write_text(step.get("md", result))
    else:
        print(json.dumps(step.get("payload", {"type": "result", "subtype": "error" if error else "success",
                                              "session_id": sid, "is_error": bool(error),
                                              "result": error or result, "num_turns": 1,
                                              "total_cost_usd": 0.001})))
emit("finish", attempt=attempt, exit=step.get("exit", 0))
sys.exit(step.get("exit", 0))
PY_EVAL
chmod 755 "$review_lab/controls/fake_provider.py"
~~~~

</details>

<details>
<summary>flow.py</summary>

~~~~bash
cat > "$review_lab/controls/flow.py" <<'PY_EVAL'
from lab import *
import sys

def live_start(root, agent, attempt=1):
    return next((r for r in starts(root) if r["agent"] == agent and r["attempt"] == attempt), None)

def healthy(provider):
    name = f"healthy-{provider}"
    root, env = fixture(name, {"leader": [
        {"decision": decision(
            action("create_role", "alpha", prompt="Alpha role header"),
            action("create_role", "beta", prompt="Beta role header"),
            action("launch", "alpha", effort="low"),
            action("launch", "beta", effort="medium"))},
        {"decision": decision(action("resume", "alpha", effort="high"))},
        {"decision": decision(done=True),
         "write": {"output/report.md": "fixture final artifact\n"}}],
        "alpha": [{"gate": "release-first", "result": "alpha first"},
                  {"gate": "release-resume", "result": "alpha resumed"}],
        "beta": [{"gate": "release-first", "result": "beta first"}]}, provider)

    harness = spawn(root, env, "bash", "run.sh", "--provider", provider, "--effort", "medium")
    first = [wait_until(lambda: live_start(root, agent)) for agent in ("alpha", "beta")]
    for agent in ("alpha","beta"):
        wait_until(lambda: read(root / f"agents/{agent}/pid"))
    assert not any(r["event"] == "finish" and r["agent"] in ("alpha","beta") for r in trace(root))
    (root / "release-first").touch()
    second = wait_until(lambda: live_start(root, "alpha", 2), 10)
    wait_until(lambda: read(root / "agents/alpha/pid"))
    (root / "release-resume").touch()
    rc, out = finish(harness, 12)
    workers = first + [second]
    leaders = [r for r in starts(root) if r["agent"] == "leader"]
    emit(name, rc=rc, leader_resumes=[r["resume"] for r in leaders],
         worker_resumes=[r["resume"] for r in workers],
         worker_efforts=[r["effort"] for r in workers], worker_models=[r["model"] for r in workers],
         worker_states={agent: state(root, agent) for agent in ("alpha", "beta")},
         worker_results={agent: load(root / f"agents/{agent}/latest.json")["result"] for agent in ("alpha", "beta")},
         worker_markdown={agent: read(root / f"agents/{agent}/output.md") for agent in ("alpha", "beta")},
         alpha_archives=len(list((root / "agents/alpha/runs").glob("*.json"))),
         wake_spacing=[round(b["monotonic"]-a["monotonic"], 3) for a,b in zip(leaders,leaders[1:])],
         instruction_files=sorted(p.name for p in Path(env["TMPDIR"]).glob("*.md")),
         done=(root / "state/done").exists(), artifact=read(root / "output/report.md"),
         completions=[l for l in out.splitlines() if "Wake reasons: " in l])
    assert rc == 0 and (root / "state/done").exists()
    assert [r["resume"] for r in workers] == [None, None, f"{provider}-alpha-1"]
    assert [r["resume"] for r in leaders] == [None, f"{provider}-leader-1", f"{provider}-leader-2"]
    assert all(state(root, agent)["state"] == "done" for agent in ("alpha", "beta"))
    assert read(root / "seen/alpha.1.txt").startswith("Alpha role header\n\n---")
    assert "alpha first" in read(root / "seen/leader.2.txt")
    if provider == "codex":
        assert [r["effort"] for r in workers] == ["low", "medium", "high"]
    else:
        assert [r["model"] for r in workers] == ["opus"]*3
    assert read(root / "output/report.md") == "fixture final artifact\n"

def decisions():
    first = decision(action("create_role", "existing", prompt="direct role"))
    next_ = decision(action("create_role", "alternative", prompt="fenced role"))
    fenced = "Leader response\n\n```json\n" + json.dumps(next_) + "\n```"
    root, env = fixture("decision-replay", {"leader": [
        {"decision": first}, {"result": fenced}, {"result": fenced},
        {"raw_decision": "{", "result": fenced},
        {"raw_decision": "{}", "result": "no structured decision"},
        {"decision": decision(action("create_role", "before", prompt="committed before error"),
                              action("create_role", "broken", prompt=17),
                              action("create_role", "after", prompt="not reached"))},
        {"decision": next_}]})
    def once():
        return run(root, env, "bash", "run.sh", "--once")
    assert once()[0] == 0
    existing = root / "prompts/roles/existing/SYSTEM.md"
    alternative = root / "prompts/roles/alternative/SYSTEM.md"
    existing.write_text("local edit between wakes")
    replay_rc, replay_log = once()
    replayed = read(existing)
    absent_alt = not alternative.exists()
    timestamp = load(root / "state/decisions/latest.json")["timestamp"]
    (root / "state/decisions/latest.json").unlink()
    fresh_rc, fresh_log = once()
    fresh_content = read(alternative)
    fresh_actions = load(root / "state/decisions/latest.json")["actions"]
    corrupt_rc, corrupt_log = once()
    fallback_recovered = read(alternative)
    corrupt_actions = load(root / "state/decisions/latest.json")["actions"]
    empty_rc, empty_log = once()
    empty = load(root / "state/decisions/latest.json")
    (root / "prompts/roles/broken").mkdir()
    (root / "prompts/roles/broken/SYSTEM.md").write_text("valuable existing role")
    partial_rc, partial_log = once()
    direct_rc, direct_log = once()
    emit("decision replay and validation", replay_rc=replay_rc, replayed=replayed,
         absent_alt=absent_alt, timestamp=timestamp,
         replay_fallback="Extracted decision" in replay_log,
         fresh_rc=fresh_rc, fresh_content=fresh_content, fresh_extracted="Extracted decision" in fresh_log, fresh_actions=fresh_actions,
         fresh_overwritten="fallback empty decision" in fresh_log,
         corrupt_rc=corrupt_rc, corrupt_extracted="Extracted decision" in corrupt_log,
         recovered=fallback_recovered, corrupt_actions=corrupt_actions, empty_rc=empty_rc, empty_actions=empty["actions"],
         direct_rc=direct_rc, direct_alternative=read(alternative),
         empty_warning="fallback empty decision" in empty_log,
         partial_rc=partial_rc, before=read(root / "prompts/roles/before/SYSTEM.md"),
         broken=read(root / "prompts/roles/broken/SYSTEM.md"),
         after_exists=(root / "prompts/roles/after/SYSTEM.md").exists(),
         partial_error=[l for l in partial_log.splitlines() if "TypeError" in l])
    assert replay_rc == fresh_rc == corrupt_rc == empty_rc == 0
    assert replayed == "direct role" and absent_alt and timestamp == "fixture-wake-1"
    assert fresh_content is None and fallback_recovered is None
    assert fresh_actions==corrupt_actions==empty["actions"]==[]
    assert all("Extracted decision" in l and "fallback empty decision" in l for l in (fresh_log,corrupt_log))
    assert direct_rc==0 and read(alternative)=="fenced role"
    assert partial_rc != 0 and read(root / "prompts/roles/before/SYSTEM.md")
    assert read(root / "prompts/roles/broken/SYSTEM.md") == ""
    assert not (root / "prompts/roles/after/SYSTEM.md").exists()

def continuation():
    root, env = fixture("done-continuation", {"leader": [
        {"decision": decision(done=True), "write": {"output/original.md": "done first"}},
        {"decision": decision(action("launch", "followup"))},
        {"decision": decision(action("launch", "after_clear"))},
        {"decision": decision(done=True), "write": {"output/continued.md": "done follow-up"}}],
        "followup": [{"gate": "resume-followup", "write_after": {"output/unmanaged.md": "late write"}}],
        "after_clear": [{"gate": "resume-after-clear"}]})
    assert run(root, env, "bash", "run.sh")[0] == 0
    ts = (root / "state/done").stat().st_mtime_ns
    with (root / "inbox.md").open("a") as stream:
        stream.write("\nFixture follow-up input\n")
    rc, out = run(root, env, "bash", "run.sh")
    leader_prompt = read(root / "seen/leader.2.txt")
    same_done_marker = (root / "state/done").stat().st_mtime_ns == ts
    worker = wait_until(lambda: live_start(root, "followup"))
    worker_alive_after_harness = proc_alive(worker["pid"])
    state_at_return = state(root, "followup")["state"]
    assert not (root / "output/unmanaged.md").exists()
    (root / "resume-followup").touch()
    wait_until(lambda: (root / "output/unmanaged.md").exists())
    wait_until(lambda: any(r["agent"] == "followup" and r["event"] == "finish" for r in trace(root)))
    after_finish = state(root, "followup")["state"]
    (root / "state/done").unlink()
    p = spawn(root, env, "bash", "run.sh")
    wait_until(lambda: live_start(root, "after_clear"))
    wait_until(lambda: read(root / "agents/after_clear/pid"))
    (root / "resume-after-clear").touch()
    fixed_rc, fixed_out = finish(p, 12)
    emit("done marker continuation", rc=rc, seen_inbox="Fixture follow-up input" in leader_prompt,
         previous_done_marker=same_done_marker, last_decision_done=False,
         state_at_return=state_at_return, worker_alive_after_harness=worker_alive_after_harness,
         wrote_after_harness=read(root / "output/unmanaged.md"), after_finish=after_finish,
         fixed_rc=fixed_rc, fixed_state=state(root, "after_clear")["state"],
         prior_state_after_new_start=state(root, "followup")["state"],
         fixed_artifact=read(root / "output/continued.md"), total_leader_calls=len([r for r in starts(root) if r["agent"] == "leader"]))
    assert rc == fixed_rc == 0 and same_done_marker and worker_alive_after_harness
    assert "Fixture follow-up input" in leader_prompt and state_at_return == after_finish == "running"
    assert state(root, "after_clear")["state"] == "done" and (root / "output/continued.md").exists()

def early_done():
    root, env = fixture("fresh-done-active", {"leader": [
        {"decision": decision(action("launch", "quick"), action("launch", "slow"))},
        {"decision": decision(action("stop", "slow"), done=True)}],
        "quick": [{"gate": "allow-quick"}],
        "slow": [{"gate": "allow-slow", "write_after": {"output/unmanaged.md": "late from slow"}}]})
    p = spawn(root, env, "bash", "run.sh")
    for agent in ("quick", "slow"):
        wait_until(lambda: live_start(root,agent))
        wait_until(lambda: read(root / f"agents/{agent}/pid"))
    (root / "allow-quick").touch()
    rc, out = finish(p, 12)
    slow_pid = live_start(root, "slow")["pid"]
    slow_state = state(root, "slow")["state"]
    alive = proc_alive(slow_pid)
    (root / "allow-slow").touch()
    wait_until(lambda: (root / "output/unmanaged.md").exists())
    emit("done while active", rc=rc, slow_state=slow_state, slow_process_alive=alive,
         stop_action_reached="Stopped slow" in out,
         done=(root / "state/done").exists(), late_write=read(root / "output/unmanaged.md"))
    assert rc == 0 and slow_state == "running" and alive and "Stopped slow" not in out

if sys.argv[1] == "codex" or sys.argv[1] == "claude":
    healthy(sys.argv[1])
else:
    globals()[sys.argv[1]]()
PY_EVAL
~~~~

</details>

<details>
<summary>natural.py</summary>

~~~~bash
cat > "$review_lab/controls/natural.py" <<'PY_EVAL'
from lab import *
import sys

pipes = sys.argv[2:] == ["pipe"]
suffix = "-pipe" if pipes else ""

if sys.argv[1] == "heartbeat":
    root, env = fixture("natural-heartbeat" + suffix, {"leader": [
        {"decision": decision(action("wait"))}, {"decision": decision(done=True)}
    ]})
    started = time.monotonic()
    p = spawn(root, env, "bash", "run.sh", "--provider", "codex", pipes=pipes)
    rc, out = finish(p, timeout=215)
    leader = starts(root)
    delta = leader[1]["monotonic"] - leader[0]["monotonic"]
    emit("natural heartbeat", rc=rc, capture="pipe" if pipes else "file", elapsed=round(time.monotonic()-started, 3),
         leader_delta=round(delta, 3), wakes=len(leader), resume=leader[1]["resume"],
         states=[line for line in out.splitlines() if "Poll interval:" in line or "Wake reasons:" in line],
         tick=load(root / "state/harness.json")["tick_count"])
    assert rc == 0 and 180 <= delta <= 192 and len(leader) == 2
    assert leader[1]["resume"] == "codex-leader-1" and (root / "state/done").exists()
elif sys.argv[1] == "claude":
    root, env = fixture("natural-claude" + suffix, {"leader": [
        {"error": "fixture 429 rate limit"}, {"decision": decision(done=True)}
    ]}, "claude")
    started = time.monotonic()
    p = spawn(root, env, "bash", "run.sh", "--provider", "claude", "--once", pipes=pipes)
    rc, out = finish(p, timeout=45)
    leader = starts(root)
    delta = leader[1]["monotonic"] - leader[0]["monotonic"]
    emit("natural Claude", rc=rc, capture="pipe" if pipes else "file", elapsed=round(time.monotonic()-started, 3),
         leader_delta=round(delta, 3), models=[r["model"] for r in leader],
         retry_lines=[l for l in out.splitlines() if "RETRY" in l], archives=sorted(p.name for p in (root / "agents/leader/runs").iterdir()))
    assert rc == 0 and 29.9 <= delta <= 36 and [r["model"] for r in leader] == ["opus","sonnet"]
    assert (root / "state/done").exists()
PY_EVAL
~~~~

</details>

<details>
<summary>failure.py</summary>

~~~~bash
cat > "$review_lab/controls/failure.py" <<'PY_EVAL'
from lab import *
import sys

def retry(provider):
    failed = {"error":"429 rate limit from fixture", "stderr":"429 rate limit from fixture", "exit":42}
    root, env = fixture("retry-" + provider, {"leader":[failed, {"decision":decision(done=True)}]}, provider)
    rc, out = run(root, env, "bash", "run.sh")
    leader = root / "agents/leader"
    stranded = load(root / "state/harness.json")
    emit(provider+" unguarded failure", rc=rc, attempts=len(starts(root)), guard=stranded["leader_running"],
         last_wake=stranded["leader_last_woken_at"], raw=read(leader / ("latest.jsonl" if provider=="codex" else "latest.json")),
         exit_record=read(leader/"exit_code"), retry_logged="RETRY" in out,
         warning_logged="WARNING: wake_leader.sh exited" in out)
    assert rc==42 and len(starts(root))==1 and stranded["leader_running"] and read(leader/"exit_code") is None
    assert "RETRY" not in out and "WARNING: wake_leader.sh exited" not in out

    # Same failure input and adapter, different shell error context.
    root, env = fixture("retry-guarded-"+provider, {"smoke":[failed, {"result":"retry success"}]}, provider)
    rc, out = run(root, env, "bash", "-c", r'''
source scripts/lib.sh
sleep() { printf 'fixture wait %s\n' "$1"; }
mkdir -p agents/smoke
if provider_run_agent launch smoke 'worker-id: smoke' "$ROOT/agents/smoke/output.md" \
  "$ROOT/agents/smoke/latest.json" "$(provider_raw_output_file smoke)" "$ROOT/agents/smoke/stderr.log" ""; then
  result=$?
else
  result=$?
fi
printf 'guarded adapter rc=%s\n' "$result"''')
    events=starts(root)
    emit(provider+" guarded helper", rc=rc, attempts=len(events), models=[r["model"] for r in events],
         result=load(root / "agents/smoke/latest.json")["result"],
         output=[l for l in out.splitlines() if "RETRY" in l or "fixture wait" in l or "adapter rc" in l])
    assert rc==0 and len(events)==2 and "fixture wait 30" in out and "guarded adapter rc=0" in out
    assert load(root / "agents/smoke/latest.json")["result"]=="retry success"

def no_session():
    for provider in ("codex","claude"):
        root, env = fixture("no-session-"+provider, {"leader":[{"session":"","decision":decision(done=True)}]}, provider)
        rc, out = run(root, env, "bash", "run.sh", "--once")
        d = root / "agents/leader"
        observed = dict(rc=rc, cli_exit=read(d/"exit_code"), normalized=load(d/"latest.json"),
                        archives=len(list((d/"runs").glob("*.json"))),
                        has_decision=(root/"state/decisions/latest.json").exists(),
                        done=(root/"state/done").exists(),status=state(root,"leader"))
        emit(provider+" missing session", **observed)
        assert rc==1 and observed["cli_exit"]=="0\n" and observed["has_decision"] and not observed["done"]

def worker_exit(provider):
    cases=[
        ("nonzero-normal-shape", {"result":"successful-looking text","exit":42,"stderr":"permanent failure"}, "done"),
        ("nonzero-explicit-error", {"error":"permanent failure","exit":42,"stderr":"permanent failure"}, "error"),
        ("zero-normal-shape", {"result":"successful-looking text"}, "done"),
    ]
    for suffix, step, expected in cases:
        root, env = fixture(f"worker-exit-{provider}-{suffix}", {
            "leader":[{"decision":decision(action("launch","smoke"))},{"decision":decision(done=True)}],
            "smoke":[dict(step,gate="release-worker")]},provider)
        p=spawn(root,env,"bash","run.sh")
        wait_until(lambda:any(r["agent"]=="smoke" for r in starts(root)))
        wait_until(lambda:read(root/"agents/smoke/pid"))
        assert state(root,"smoke")["state"]=="running"
        (root/"release-worker").touch()
        rc,out=finish(p,15)
        d=root/"agents/smoke"
        observed=state(root,"smoke")
        emit(provider+" worker exit "+suffix, rc=rc, state=observed["state"],
             cli_exit=next(r["exit"] for r in trace(root) if r["agent"]=="smoke" and r["event"]=="finish"),
             exit_record=read(d/"exit_code"), normalized=load(d/"latest.json"), pid_in_json=observed.get("pid"),
             pid_file=(d/"pid").exists(), stderr=read(d/"stderr.log"),
             wake_reasons=[l for l in out.splitlines() if "Wake reasons:" in l])
        assert rc==0 and observed["state"]==expected
        assert read(d/"exit_code")==("0\n" if step.get("exit",0)==0 else None)

def stale_worker():
    root,env=fixture("stale-worker",{"leader":[
        {"decision":decision(action("launch","smoke"))},
        {"decision":decision(action("resume","smoke"))},
        {"decision":decision(done=True)}],
        "smoke":[{"gate":"allow-first","result":"old success"},
                 {"gate":"allow-second","error":"permanent fresh failure","exit":42,"no_md":True}]})
    p=spawn(root,env,"bash","run.sh")
    for i, gate in enumerate(("allow-first","allow-second"),1):
        wait_until(lambda:next((r for r in starts(root) if r["agent"]=="smoke" and r["attempt"]==i),None),10)
        wait_until(lambda:read(root/"agents/smoke/pid"))
        (root/gate).touch()
    rc,out=finish(p,15)
    d=root/"agents/smoke"
    observed=load(d/"latest.json")
    emit("Codex stale normalized result after failed resume",rc=rc, state=state(root,"smoke")["state"],
         result=observed["result"], sid=read(d/"session_id.codex"),md=read(d/"output.md"),
         old_exit_record=read(d/"exit_code"), new_cli_exit=next(r["exit"] for r in trace(root)
           if r["agent"]=="smoke" and r["event"]=="finish" and r["attempt"]==2),
         raw_failure="permanent fresh failure" in read(d/"latest.jsonl"),
         archives=[load(f)["result"] for f in sorted((d/"runs").glob("*.json"))])
    assert rc==0 and state(root,"smoke")["state"]=="done" and observed["result"]=="old success"
    assert "permanent fresh failure" in read(d/"latest.jsonl")

globals()[sys.argv[1]](*sys.argv[2:])
PY_EVAL
~~~~

</details>

<details>
<summary>processes.py</summary>

~~~~bash
cat > "$review_lab/controls/processes.py" <<'PY_EVAL'
from lab import *
import select
import sys

def launch(root, env, agent="smoke"):
    instruction = root / "instruction.md"
    instruction.write_text(f"worker-id: {agent}")
    rc,out = run(root,env,"bash","scripts/launch_subagent.sh",agent,str(instruction))
    assert rc==0, out
    worker=wait_until(lambda:next((r for r in starts(root) if r["agent"]==agent),None))
    return worker, int(read(root/f"agents/{agent}/pid"))

def stop():
    root,env=fixture("process-stop",{"smoke":[{"gate":"hold", "spawn_child":True}]})
    worker, wrapper=launch(root,env)
    child=wait_until(lambda:next((r for r in trace(root) if r["event"]=="spawned-child"),None))
    leaf=child["child_pid"]
    decision_path=root/"state/decisions/latest.json"
    write_json(decision_path,decision(action("stop","smoke")))
    decision_rc,decision_out=run(root,env,"bash","scripts/execute_decisions.sh")
    survived_action=proc_alive(worker["pid"]) and proc_alive(leaf)
    action_state=state(root,"smoke")["state"]
    wrapper_pgid=os.getpgid(wrapper)
    assert wrapper_pgid==worker["pgid"]==child["child_pgid"] and wrapper!=wrapper_pgid
    stop_rc,stop_out=run(root,env,"bash","stop.sh")
    wait_until(lambda:not proc_alive(worker["pid"]))
    survived_leaf=proc_alive(leaf)
    post=state(root,"smoke")
    emit("stop targets and process scope",decision_rc=decision_rc,decision_log=decision_out.splitlines(),
         survived_action=survived_action, action_state=action_state,
         wrapper=wrapper,provider_pid=worker["pid"],leaf_pid=leaf,group=wrapper_pgid,
         stop_rc=stop_rc,stop_log=stop_out.splitlines(), provider_alive=proc_alive(worker["pid"]),
         leaf_alive=survived_leaf,post_state=post["state"], pidfile=(root/"agents/smoke/pid").exists())
    assert decision_rc==stop_rc==0 and survived_action and action_state=="running" and survived_leaf
    assert post["state"]=="idle" and not (root/"agents/smoke/pid").exists()
    os.killpg(wrapper_pgid,signal.SIGTERM)
    wait_until(lambda:not proc_alive(leaf))

def term_resistant():
    root,env=fixture("stop-resistant",{"smoke":[{"gate":"release","ignore_term":True}]})
    worker,wrapper=launch(root,env)
    wait_until(lambda:any(r["event"]=="configured" for r in trace(root)))
    assert proc_alive(worker["pid"])
    rc,out=run(root,env,"bash","stop.sh")
    wait_until(lambda:any(r["event"]=="ignored-term" for r in trace(root)))
    before=state(root,"smoke")
    is_alive=proc_alive(worker["pid"])
    (root/"release").touch()
    wait_until(lambda:(root/"agents/smoke/exit_code").exists())
    emit("soft stop against TERM resistant provider", rc=rc, state=before["state"],
         provider_alive_after_stop=is_alive, pidfile=(root/"agents/smoke/pid").exists(),
         terminal_write=read(root/"agents/smoke/exit_code"), result=load(root/"agents/smoke/latest.json"),
         log=out.splitlines())
    assert rc==0 and is_alive and before["state"]=="idle"

def pipe_eof():
    root,env=fixture("leader-pipe-eof",{"leader":[{"decision":decision(done=True)}]})
    begun=time.monotonic()
    p=spawn(root,env,"bash","run.sh","--once",pipes=True)
    fd=os.readlink(f"/proc/self/fd/{p.stdout.fileno()}")
    rc=p.wait(timeout=3)
    direct_exit=time.monotonic()-begun
    holders=[]
    for q in Path("/proc").glob("[0-9]*"):
        pid=int(q.name)
        if pid==os.getpid() or pid==p.pid:
            continue
        try:
            if os.readlink(q/"fd/1")==fd:
                holders.append(dict(pid=pid, cmd=(q/"cmdline").read_bytes().replace(b"\0",b" ").decode(),
                                    pgid=os.getpgid(pid), ppid=int((q/"stat").read_text().rsplit(")",1)[-1].split()[1])))
        except (FileNotFoundError,PermissionError,ProcessLookupError):
            pass
    out,_=p.communicate(timeout=15)
    eof=time.monotonic()-begun
    emit("leader spinner pipe ownership",rc=rc,process_exit_s=round(direct_exit,3),pipe_eof_s=round(eof,3),
         stdout_holders=holders, done=(root/"state/done").exists())
    assert rc==0 and len(holders)==1 and holders[0]["cmd"].startswith("sleep 10 ")
    assert holders[0]["pgid"]==p.pid and eof-direct_exit>8

globals()[sys.argv[1]]()
PY_EVAL
~~~~

</details>

<details>
<summary>start_gap.py</summary>

~~~~bash
cat > "$review_lab/controls/start_gap.py" <<'PY_EVAL'
from lab import *
import sys

forced=sys.argv[1]=="forced"
root,env=fixture(f"worker-publication-gap-{sys.argv[1]}",{
    "leader":[{"decision":decision(action("launch","smoke"))},
              {"decision":decision(action("launch","witness"))},
              {"decision":decision(done=True)}],
    "smoke":[{"gate":"complete-smoke","result":"fresh worker result"}],
    "witness":[{"gate":"complete-witness"}]})
if forced:
    shim=root/"fake-bin/python3"
    shim.write_text("""#!/usr/bin/python3
import os, pathlib, sys, time
if (len(sys.argv) == 6 and sys.argv[1] == "-c" and
    sys.argv[3].endswith("/agents/smoke/status.json") and sys.argv[4] == "instruction_summary"):
    root=pathlib.Path(os.environ["REVIEW_TEST_ROOT"])
    (root/"pause-published").touch()
    until=time.monotonic()+18
    while not (root/"advance-launcher").exists() and time.monotonic()<until:
        time.sleep(.015)
os.execv("/usr/bin/python3", ["python3", *sys.argv[1:]])
""")
    shim.chmod(0o755)
    env["REVIEW_TEST_ROOT"]=str(root)

def started(agent, attempt=1):
    return next((r for r in starts(root) if r["agent"]==agent and r["attempt"]==attempt),None)
p=spawn(root,env,"bash","run.sh")
if forced:
    wait_until(lambda:(root/"pause-published").exists())
    wait_until(lambda:started("leader",2),9)
    before=state(root,"smoke")
    assert "PID file missing while state=running" in read(root/"logs/harness.log")
    assert before["state"]=="error" and not (root/"agents/smoke/pid").exists()
    (root/"advance-launcher").touch()
else:
    wait_until(lambda:started("smoke"))
    wait_until(lambda:read(root/"agents/smoke/pid"))
    before=state(root,"smoke")
    assert before["state"]=="running"
wait_until(lambda:started("smoke"))
wait_until(lambda:read(root/"agents/smoke/pid"))
(root/"complete-smoke").touch()
wait_until(lambda:(root/"agents/smoke/exit_code").exists())
wait_until(lambda:started("witness"),10)
wait_until(lambda:read(root/"agents/witness/pid"))
(root/"complete-witness").touch()
rc,out=finish(p,14)
end=state(root,"smoke")
emit("worker status/PID publication",forced=forced,rc=rc,pre_provider_state=before["state"],
     end_state=end["state"], result=load(root/"agents/smoke/latest.json")["result"],
     markdown=read(root/"agents/smoke/output.md"), old_pid_file=(root/"agents/smoke/pid").exists(),
     gap_logged="PID file missing while state=running" in out,
     witness_state=state(root,"witness")["state"])
assert rc==0 and state(root,"witness")["state"]=="done"
assert end["state"]==("error" if forced else "done")
assert (root/"agents/smoke/pid").exists()==forced
PY_EVAL
~~~~

</details>

<details>
<summary>recovery.py</summary>

~~~~bash
cat > "$review_lab/controls/recovery.py" <<'PY_EVAL'
from lab import *
import sys

def seeded(root, name, *, payload=None, raw=None, pidfile=True, markdown=None, status_state="running"):
    d=root/"agents"/name
    d.mkdir(parents=True)
    write_json(d/"status.json",dict(agent=name,state=status_state,pid=900000,
              started_at="2026-01-01T00:00:00Z",finished_at=None,instruction_summary="old instruction for "+name))
    if pidfile:
        (d/"pid").write_text("900000\n")
    if payload is not None:
        (d/"latest.json").write_text(payload if isinstance(payload,str) else json.dumps(payload))
    if raw is not None:
        (d/"latest.jsonl").write_text(raw)
    if markdown is not None:
        (d/"output.md").write_text(markdown)
    return d

def reconciliation(entry):
    root,env=fixture("recovery-"+entry,{"leader":[{"decision":decision(done=True)}]})
    assert not proc_alive(900000)
    has_pid=entry!="public-no-pid"
    seeded(root,"valid",payload={"session_id":"previous-sid","result":"previous result","is_error":False},pidfile=has_pid)
    seeded(root,"bad",payload="{",pidfile=has_pid)
    seeded(root,"empty",pidfile=has_pid)
    seeded(root,"no-result",payload={"session_id":"from-empty","is_error":False},pidfile=has_pid)
    seeded(root,"alias",payload={"session_id":"alias-sid","content":"valid visibly","is_error":False},pidfile=has_pid)
    raw="\n".join(map(json.dumps,[dict(type="thread.started",thread_id="raw-sid"),
        dict(type="item.completed",item=dict(type="agent_message",text="valid raw result"))]))+"\n"
    raw_dir=seeded(root,"raw-only",raw=raw,pidfile=has_pid)
    expected=run(root,env,"python3","scripts/codex_jsonl_to_compat.py",str(raw_dir/"latest.jsonl"),"--exit-code","0")
    assert expected[0]==0 and json.loads(expected[1])["result"]=="valid raw result"
    script="scripts/harness.sh" if entry=="direct" else "run.sh"
    rc,out=run(root,env,"bash",script)
    names=("valid","bad","empty","no-result","alias","raw-only")
    end={name:state(root,name)["state"] for name in names}
    archives={name:len(list((root/"agents"/name/"runs").glob("*.json"))) for name in names}
    emit("restart reconciliation "+entry,rc=rc,end=end,archives=archives,ll_pid=state(root,"valid")["pid"],
         active_pid_file=(root/"agents/valid/pid").exists(),
         wake=next((l for l in out.splitlines() if "Leader waking..." in l),None),
         raw_direct_result=json.loads(expected[1])["result"])
    assert rc==0 and not (root/"agents/valid/pid").exists()
    if entry=="public":
        assert set(end.values())=={"idle"} and set(archives.values())=={0}
    else:
        assert end==dict(zip(names,("done","error","idle","error","error","idle")))
        assert archives["valid"]==1 and sum(archives.values())==1

def empty_session():
    root,env=fixture("recover-empty-sid",{"leader":[{"decision":decision(done=True)}]})
    d=seeded(root,"recoverable",payload={"result":"useful completed output","is_error":False},pidfile=False)
    rc,out=run(root,env,"bash","scripts/harness.sh")
    emit("restart successful payload with no session",rc=rc,provider_calls=len(starts(root)),state=state(root,"recoverable"),
         archived=len(list((d/"runs").glob("*.json"))), markdown=read(d/"output.md"),
         pre_archive_log="had valid output" in out, initialized="Harness initialized" in out)
    assert rc==1 and len(starts(root))==0 and state(root,"recoverable")["state"]=="running"
    assert len(list((d/"runs").glob("*.json")))==1
    write_json(d/"latest.json",{"is_error":False,"result":"useful completed output","session_id":"valid-sid"})
    rc,out=run(root,env,"bash","scripts/harness.sh")
    emit("restart equivalent payload with session",rc=rc,provider_calls=len(starts(root)),state=state(root,"recoverable"),
         markdown=read(d/"output.md"))
    assert rc==0 and state(root,"recoverable")["state"]=="done"

def foreign():
    root,env=fixture("recover-with-other-provider",{
        "leader":[{"decision":decision(action("resume","foreign"))},{"decision":decision(done=True)}],
        "foreign":[{"gate":"release","result":"future Codex CLI call"}]})
    d=seeded(root,"foreign",payload={"type":"result","subtype":"success","session_id":"claude-prior-id",
                                       "result":"prior Claude output","is_error":False},pidfile=False)
    (d/"session_id.claude").write_text("claude-prior-id\n")
    p=spawn(root,env,"bash","run.sh","--provider","codex")
    w=wait_until(lambda:next((r for r in starts(root) if r["agent"]=="foreign"),None))
    sent=read(d/"session_id.codex")
    (root/"release").touch()
    rc,out=finish(p,12)
    emit("restart cross-provider result ownership",rc=rc,codex_sid_written_by_recovery=sent,
         resumed_with=w["resume"],prior_provider_payload_type="result", end_state=state(root,"foreign")["state"])
    assert rc==0 and w["resume"]=="claude-prior-id" and sent=="claude-prior-id\n"

def corrupt_stop():
    root,env=fixture("stop-malformed-status",{})
    a=seeded(root,"a_first")
    z=seeded(root,"z_later")
    (a/"status.json").write_text("{")
    write_json(root/"state/harness.json", {"leader_running":True})
    rc,out=run(root,env,"bash","stop.sh")
    left=(z/"pid").exists()
    guard=load(root/"state/harness.json")["leader_running"]
    emit("soft stop with malformed status",rc=rc,first_claim_removed=not (a/"pid").exists(),
         later_claim_left=left,later_state=state(root,"z_later")["state"],
         guard=guard,output=[l for l in out.splitlines() if "JSONDecodeError" in l])
    assert rc!=0 and left and guard
    write_json(a/"status.json",{"state":"running","pid":900000})
    (a/"pid").write_text("900000\n")
    fixed_rc,out=run(root,env,"bash","stop.sh")
    emit("soft stop repaired status fixture",rc=fixed_rc,later_state=state(root,"z_later")["state"],
         guard=load(root/"state/harness.json")["leader_running"])
    assert fixed_rc==0 and state(root,"z_later")["state"]=="idle"

globals()[sys.argv[1]](*sys.argv[2:])
PY_EVAL
~~~~

</details>

<details>
<summary>sessions.py</summary>

~~~~bash
cat > "$review_lab/controls/sessions.py" <<'PY_EVAL'
from lab import *
import sys

def round_trip():
    root,env=fixture("session-round-trip",{"leader":[
        {"decision":decision(action("wait")),"result":"Alpha context only in Codex"},
        {"decision":decision(action("wait")),"result":"Beta update only in Claude"},
        {"decision":decision(done=True),"result":"Codex concludes"}]})
    for provider in ("codex","claude","codex"):
        rc,out=run(root,env,"bash","run.sh","--provider",provider,"--once")
        assert rc==0,out
    p2=read(root/"seen/leader.2.txt")
    p3=read(root/"seen/leader.3.txt")
    observed=starts(root)
    emit("session provider A-B-A",providers=[r["provider"] for r in observed],resumes=[r["resume"] for r in observed],
         handoff1=("## PROVIDER HANDOFF" in p2 and "Alpha context only in Codex" in p2),
         return_handoff="## PROVIDER HANDOFF" in p3, return_has_beta="Beta update only in Claude" in p3,
         archive_count=len(list((root/"agents/leader/runs").glob("*.json"))),
         explicit_ids={name:read(root/f"agents/leader/session_id.{name}") for name in ("codex","claude")})
    assert [r["resume"] for r in observed]==[None,None,"codex-leader-1"]
    assert "Alpha context only in Codex" in p2 and "Beta update only in Claude" not in p3

def worker_handoff():
    root,env=fixture("worker-instruction-handoff",{"smoke":[
        {"gate":"finish-first","result":"First provider's substantive result"},
        {"gate":"finish-second","result":"Second provider finishes"}]})
    i=root/"instruction.md"
    i.write_text("worker-id: smoke\nPrior instruction only")
    for n,provider in enumerate(("codex","claude"), 1):
        env=env|{"MULTI_AGENT_PROVIDER":provider,"CLAW_PROVIDER":provider}
        if n==2:
            i.write_text("worker-id: smoke\nNew instruction only")
        rc,out=run(root,env,"bash","scripts/launch_subagent.sh","smoke",str(i),*(["--resume"] if n==2 else []))
        assert rc==0
        d=root/"agents/smoke"
        owner=int(read(d/"pid"))
        wait_until(lambda:(root/f"seen/smoke.{n}.txt").exists())
        (root/("finish-first" if n==1 else "finish-second")).touch()
        wait_until(lambda:not proc_alive(owner))
        rc,out=run(root,env,"bash","-c",'source scripts/lib.sh; process_agent_result smoke')
        assert rc==0, out
    p2=read(root/"seen/smoke.2.txt")
    section=p2.split("## PROVIDER HANDOFF")[-1]
    emit("actual worker handoff summary",resumes=[r["resume"] for r in starts(root)],
         has_old_output="First provider's substantive result" in section,
         has_previous_instruction="Prior instruction only" in section,
         names_new_as_previous="Previous instruction summary:\nworker-id: smoke\nNew instruction only" in section,
         snapshot=section)
    assert "## PROVIDER HANDOFF" in p2 and "First provider's substantive result" in section
    assert "Prior instruction only" not in section and "New instruction only" in section

def legacy_stream():
    root,env=fixture("stream-legacy",{})
    d=root/"agents/smoke"
    input_data=json.dumps({"type":"system","subtype":"init","model":"fixture"})+"\n"+json.dumps({
        "type":"result","session_id":"legacy-claude-id","result":"legacy Claude stream result",
        "is_error":False,"num_turns":1,"total_cost_usd":.001})+"\n"
    p=subprocess.run(["python3","scripts/stream_processor.py",str(d)],cwd=root,env=env,input=input_data,
                     text=True,capture_output=True,check=True,timeout=5)
    (d/"session_id").write_text("legacy-claude-id\n")
    ambiguous=load(d/"latest.json")
    def get():
        return run(root,env,"bash","-c",'source scripts/lib.sh; printf "detected=%s\nresume=%s\n" "$(detect_session_provider smoke)" "$(get_session smoke)"')
    rc,out=get()
    write_json(d/"latest.json",dict(ambiguous,type="result"))
    fixed_rc,fixed=get()
    emit("legacy adapter provenance inference",rc=rc,output=out.splitlines(),
         stream_output=p.stdout.splitlines(),stream_keys=sorted(ambiguous),type_marker_rc=fixed_rc,
         type_marker_control=fixed.splitlines())
    assert rc==fixed_rc==0 and out.splitlines()==["detected=codex","resume=legacy-claude-id"]
    assert fixed.splitlines()==["detected=claude","resume="]

globals()[sys.argv[1]]()
PY_EVAL
~~~~

</details>

<details>
<summary>provider_edges.py</summary>

~~~~bash
cat > "$review_lab/controls/provider_edges.py" <<'PY_EVAL'
from lab import *
import sys

def budget(provider):
    first={"error":"429 rate limit","exit":42 if provider=="codex" else 0}
    root,env=fixture("provider-budget-"+provider,{"smoke":[first]*12+[{"result":"attempt 13 terminal"}]},provider)
    rc,out=run(root,env,"bash","-c",r'''
source scripts/lib.sh
mkdir -p agents/smoke
sleep() { printf 'BACKOFF %s\n' "$1"; }
if provider_run_agent launch smoke 'worker-id: smoke' "$ROOT/agents/smoke/output.md" \
    "$ROOT/agents/smoke/latest.json" "$(provider_raw_output_file smoke)" "$ROOT/agents/smoke/stderr.log" ""; then
  printf 'END %s\n' "$?"
else
  printf 'END %s\n' "$?"
fi
''')
    backoffs=[int(l.split()[1]) for l in out.splitlines() if l.startswith("BACKOFF ")]
    payload=load(root/"agents/smoke/latest.json")
    models=[r["model"] for r in starts(root)]
    emit(provider+" retry budget with intercepted waits",rc=rc,attempts=len(starts(root)),backoffs=backoffs,
         virtual_sleep=sum(backoffs), result=payload["result"], archive_count=len(list((root/"agents/smoke/runs").glob("*"))),
         primary_calls=models.count("opus"),fallback_calls=models.count("sonnet"))
    assert rc==0 and len(starts(root))==13 and backoffs==[min(30*i,300) for i in range(1,13)]
    assert payload["result"]=="attempt 13 terminal" and "END 0" in out

def false_hit():
    common={"result":"first successful result", "exit":0}
    for variant,stderr in (("contains-substring","please generate output"),("neutral","please compose output")):
        root,env=fixture("claude-stderr-"+variant,{"smoke":[dict(common,stderr=stderr),{"result":"second call result"}]},"claude")
        rc,out=run(root,env,"bash","-c",r'''
source scripts/lib.sh
mkdir -p agents/smoke
sleep() { printf 'BACKOFF %s\n' "$1"; }
provider_run_agent launch smoke 'worker-id: smoke' "$ROOT/agents/smoke/output.md" \
  "$ROOT/agents/smoke/latest.json" "$(provider_raw_output_file smoke)" "$ROOT/agents/smoke/stderr.log" ""
''')
        payload=load(root/"agents/smoke/latest.json")
        emit("Claude stderr "+variant,attempts=len(starts(root)),rc=rc,result=payload["result"],
             models=[r["model"] for r in starts(root)],retry_reason="429/rate-limit" in out)
        assert rc==0 and len(starts(root))==(2 if variant=="contains-substring" else 1)
        assert payload["result"]==("second call result" if variant=="contains-substring" else "first successful result")

def normalization():
    root,env=fixture("normalization-edge-cases",{})
    shell_events=[
        {"type":"thread.started","thread_id":"codex-fixture"},
        {"type":"turn.started"},
        {"type":"item.started","item":{"type":"agent_message","text":"draft message"}},
        {"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":8}}]
    raw=root/"input.jsonl"
    markdown=root/"authoritative.md"
    markdown.write_text("final file output")
    def parse(events,rc):
        if isinstance(events,bytes):
            raw.write_bytes(events)
        else:
            raw.write_text("\n".join(map(json.dumps,events))+"\n")
        p=run(root,env,"python3","scripts/codex_jsonl_to_compat.py",str(raw),
              "--output-md",str(markdown),"--exit-code",str(rc))
        q=run(root,env,"python3","scripts/codex_retry_policy.py",
              "--exit-code",str(rc),"--jsonl-path",str(raw))
        return p,q
    normal,not_retried=parse(shell_events,0)
    nested=[*shell_events,{"type":"item.completed","item":{"type":"error","message":"429 rate limit"}}]
    nested1,nested1_retry=parse(nested,42)
    nested0,nested0_retry=parse(nested,0)
    transient=[*shell_events[:2],{"type":"error","message":"temporary connection reset"},*shell_events[2:]]
    transient0,transient0_retry=parse(transient,0)
    malformed,malformed_retry=parse(b'garbage\n["ignore"]\n'+json.dumps(shell_events[0]).encode()+b"\n",0)
    invalid,invalid_retry=parse(b'\xff\n',0)
    emit("Codex normalization and classifier",draft_overrides_md=json.loads(normal[1]),
         normal_retry=not_retried[1].strip(),
         nested_rc42_error=json.loads(nested1[1])["is_error"],nested_rc42_retry=nested1_retry[1].strip(),
         nested_rc0_error=json.loads(nested0[1])["is_error"],nested_rc0_retry=nested0_retry[1].strip(),
         transient_then_done_error=json.loads(transient0[1])["is_error"],transient_then_done_retry=transient0_retry[1].strip(),
         malformed_control=json.loads(malformed[1]), malformed_retry=malformed_retry[1].strip(),
         invalid_utf8_rc=[invalid[0],invalid_retry[0]])
    assert json.loads(normal[1])["result"]=="draft message" and json.loads(normal[1])["total_cost_usd"]==0
    assert nested1_retry[1].strip()=="true" and not json.loads(nested0[1])["is_error"] and nested0_retry[1].strip()=="false"
    assert json.loads(transient0[1])["is_error"] and transient0_retry[1].strip()=="false"
    assert malformed[0]==malformed_retry[0]==0 and invalid[0]==invalid_retry[0]==1

def cwd():
    for provider in ("codex","claude"):
        root,env=fixture("working-directory-"+provider,{"leader":[{"decision":decision(done=True)}]},provider)
        caller=root/"other-cwd"
        caller.mkdir()
        (caller/"state/decisions").mkdir(parents=True)
        write_json(caller/"fixture.json",{"leader":[{"decision":decision(done=True)}]})
        rc,out=run(root,env,"bash",str(root/"run.sh"),"--provider",provider,"--once",cwd=caller)
        provider_reads=root if provider=="codex" else caller
        child=starts(provider_reads)[0]
        emit(provider+" entry invoked from another cwd",rc=rc,process_cwd=child["cwd"],
             decision_root=(root/"state/decisions/latest.json").exists(), done_root=(root/"state/done").exists(),
             decision_caller=(caller/"state/decisions/latest.json").exists(),
             fallback="fallback empty decision" in out)
        assert child["cwd"]==str(caller) and rc==0
        assert (root/"state/done").exists()==(provider=="codex")
        assert (caller/"state/decisions/latest.json").exists()==(provider=="claude")

def argv_limit():
    cap=subprocess.check_output(["getconf","ARG_MAX"],text=True).strip()
    for n in (5000,118000,128000):
        root,env=fixture(f"leader-note-{n}",{"leader":[{"decision":decision(done=True)}]})
        (root/"notes.md").write_text("a"*n+"\n")
        rc,out=run(root,env,"bash","run.sh","--once")
        events=starts(root)
        err=read(root/"agents/leader/stderr.log") or ""
        call_size=events[0]["prompt_bytes"] if events else None
        emit("leader prompt passed as one argv entry",note_bytes=n+1,argv_max_total=cap,rc=rc,
             provider_starts=len(events),prompt_bytes=call_size,e2big="Argument list too long" in err,
             done=(root/"state/done").exists())
        if n==128000:
            assert rc==126 and not events and "Argument list too long" in err
        else:
            assert rc==0 and len(events)==1 and call_size>n

def reset_preflight():
    root,env=fixture("reset-no-provider",{})
    output=root/"output/report.md"
    output.parent.mkdir()
    output.write_text("keep unless reset")
    blocked_rc,blocked=run(root,env|{"PATH":"/usr/bin"},"bash","run.sh","--reset")
    preserved=output.exists()
    rc,out=run(root,env,"bash","run.sh","--reset")
    emit("reset requires CLI preflight",no_provider_rc=blocked_rc,explicit_message="codex CLI not found" in blocked,
         exists_after_refused=preserved,with_fixture_rc=rc,exists_after_reset=output.exists(),
         provider_attempts=len(starts(root)))
    assert blocked_rc==1 and preserved and rc==0 and not output.exists() and not starts(root)

globals()[sys.argv[1]](*sys.argv[2:])
PY_EVAL
~~~~

</details>

<details>
<summary>concurrency.py</summary>

~~~~bash
cat > "$review_lab/controls/concurrency.py" <<'PY_EVAL'
from lab import *
import sys

def duplicate():
    root,env=fixture("overlapping-same-agent",{
        "leader":[{"decision":decision(action("wait"))},{"decision":decision(done=True)}],
        "smoke":[{"gate":"release-1","result":"attempt ONE","write_after":{"output/attempt-one.md":"ran one"}},
                 {"gate":"release-2","result":"attempt TWO","write_after":{"output/attempt-two.md":"ran two"}}]})
    worker=root/"agents/smoke"
    def started(agent,n=1):
        return next((row for row in starts(root) if row["agent"]==agent and row["attempt"]==n),None)
    for n,name in enumerate(("launch","resume"),1):
        write_json(root/"state/decisions/latest.json",decision(action(name,"smoke")))
        rc,out=run(root,env,"bash","scripts/execute_decisions.sh")
        assert rc==0
        cli=wait_until(lambda:started("smoke",n))
        wait_until(lambda:read(worker/"pid")==f"{cli['ppid']}\n")
    first=started("smoke",1)
    second=started("smoke",2)
    other_live=proc_alive(first["pid"]) and proc_alive(second["pid"])
    p=spawn(root,env,"bash","scripts/harness.sh")
    wait_until(lambda:started("leader"))
    (root/"release-2").touch()
    rc,out=finish(p,12)
    projected_before=load(worker/"latest.json")
    first_survives=proc_alive(first["pid"])
    (root/"release-1").touch()
    wait_until(lambda:(root/"output/attempt-one.md").exists())
    wait_until(lambda:not proc_alive(first["ppid"]))
    after=load(worker/"latest.json")
    emit("overlapping same-name requests",rc=rc,both_admitted=other_live,second_resume=second["resume"],
         before_late=projected_before["result"],first_active_after_finish=first_survives,
         late_result=after["result"],saved_session_file=read(worker/"session_id.codex"),
         state=state(root,"smoke")["state"],history=[load(p)["result"] for p in (worker/"runs").glob("*.json")],
         pidfile=(worker/"pid").exists())
    assert rc==0 and other_live and first_survives
    assert projected_before["result"]=="attempt TWO" and after["result"]=="attempt ONE"
    assert read(worker/"session_id.codex")=="codex-smoke-2\n" and state(root,"smoke")["state"]=="done"
    assert [load(p)["result"] for p in (worker/"runs").glob("*.json")]==["attempt TWO"]

def admission():
    agents=[f"worker{n:02}" for n in range(24)]
    root,env=fixture("admission-quantity",{"*":[{"gate":"release-all","gate_timeout":25}]})
    write_json(root/"state/decisions/latest.json",decision(*(action("launch",name) for name in agents)))
    t=time.monotonic()
    rc,out=run(root,env,"bash","scripts/execute_decisions.sh")
    dispatch_done=time.monotonic()-t
    rows=wait_until(lambda: starts(root) if len(starts(root))==len(agents) else None,12)
    all_live=sum(proc_alive(r["pid"]) for r in rows)
    monitors=sum((root/f"agents/{name}/pid").exists() for name in agents)
    before=time.monotonic()-t
    (root/"release-all").touch()
    wait_until(lambda:sum(row["event"]=="finish" for row in trace(root))==len(agents),12)
    emit("batch admission",rc=rc,once_dispatched=dispatch_done,all_started_by=before,
         live_workers=all_live,pidfiles=monitors,instruction_files=len(list(Path(env["TMPDIR"]).glob("instr_*.md"))))
    assert rc==0 and all_live==len(agents)

def state_writes():
    root,env=fixture("state-file-write-fault",{})
    status=root/"agents/smoke/status.json"
    marker=root/"pausing"
    gate=root/"release"
    write_json(status,{"state":"running","pid":51,"finished_at":None})
    shim=root/"local-shim"
    shim.mkdir()
    (shim/"sitecustomize.py").write_text("""
import builtins, os, pathlib, time
original = builtins.open
target = os.getenv("REVIEW_TEST_STATUS")
method = os.getenv("REVIEW_TEST_ORDER")
marker = pathlib.Path(os.environ["REVIEW_TEST_MARKER"])
gate = pathlib.Path(os.environ["REVIEW_TEST_GATE"])
def pause():
    marker.touch()
    limit = time.monotonic() + 10
    while not gate.exists() and time.monotonic() < limit:
        time.sleep(0.02)
def controlled_open(file, mode="r", *args, **kwargs):
    match = isinstance(file, str) and file == target and mode == "w"
    if match and method == "pre-open":
        pause()
    stream = original(file, mode, *args, **kwargs)
    if match and method == "post-open":
        pause()
    return stream
builtins.open = controlled_open
""")
    base=env|dict(PYTHONPATH=str(shim),REVIEW_TEST_STATUS=str(status),REVIEW_TEST_MARKER=str(marker),
                   REVIEW_TEST_GATE=str(gate))
    def set_(key,value,style=None):
        cmd=("bash","-c",'source scripts/lib.sh; json_set "$1" "$2" "$3"',
             "_",str(status),key,value)
        if style:
            return spawn(root,base|{"REVIEW_TEST_ORDER":style},*cmd)
        return run(root,env,*cmd)
    a=set_("instruction_summary","instruction A","pre-open")
    wait_until(marker.exists)
    assert set_("pid","72")[0]==0
    between=load(status)
    gate.touch()
    assert finish(a,4)[0]==0
    lost=load(status)
    assert between["pid"]==72 and lost["pid"]==51 and lost["instruction_summary"]=="instruction A"
    assert set_("pid","72")[0]==0 and load(status)["pid"]==72
    seq=load(status)
    marker.unlink()
    gate.unlink()
    b=set_("state","done","post-open")
    wait_until(marker.exists)
    truncated=status.stat().st_size
    get_rc,get_out=run(root,env,"bash","-c",'source scripts/lib.sh; json_get "$1" state',"_",str(status))
    os.killpg(b.pid,signal.SIGKILL)
    b.wait(timeout=3)
    after=status.stat().st_size
    assert set_("pid","73")[0]==0
    recovered=load(status)
    emit("state lost update and truncated write",committed_between=between,after_late_writer=lost,
         sequential_control=seq,truncated_visible=truncated,json_get_rc=get_rc,json_get=get_out.strip(),
         truncated_after_kill=after,next_write=recovered)
    assert truncated==after==0 and get_rc==0 and not get_out.strip() and recovered=={"pid":73}

def concurrent_boot():
    root,env=fixture("concurrent-public-boots",{"leader":[{"gate":"unused"},{"gate":"unused"}]})
    bin_=root/"fake-bin"
    shim=bin_/"python3"
    shim.write_text("""#!/usr/bin/python3
import os, pathlib, subprocess, sys, time
args=sys.argv[1:]
root=pathlib.Path(os.environ["REVIEW_TEST_ROOT"])
def align(prefix):
    (root/f"{prefix}.{os.getpid()}").touch()
    until=time.monotonic()+8
    while len(list(root.glob(f"{prefix}.*")))<2 and time.monotonic()<until:
        time.sleep(0.01)
if pathlib.Path(sys.argv[0]).name=="ps":
    result=subprocess.run(["/usr/bin/ps",*args],capture_output=True,check=True)
    align("preflight-snapshot")
    os.write(1,result.stdout)
elif len(args)==4 and args[0]=="-c" and args[2].endswith("/state/harness.json") and args[3]=="leader_running":
    result=subprocess.run(["/usr/bin/python3",*args],capture_output=True,check=True)
    align("guard-observation")
    os.write(1,result.stdout)
else:
    os.execv("/usr/bin/python3",["python3",*args])
""")
    shim.chmod(0o755)
    (bin_/"ps").symlink_to(shim)
    env["REVIEW_TEST_ROOT"]=str(root)
    a=spawn(root,env,"bash","run.sh")
    b=spawn(root,env,"bash","run.sh")
    rows=wait_until(lambda:starts(root) if len(starts(root))==2 else None,10)
    both=sum(proc_alive(r["pid"]) for r in rows)
    counting=load(root/"state/harness.json")
    emit("two public supervisors",both_leaders=both,provider_groups=[r["pgid"] for r in rows],
         parents=[r["ppid"] for r in rows],guard=counting["leader_running"],
         preflight_snapshots=len(list(root.glob("preflight-snapshot.*"))),
         guard_reads=len(list(root.glob("guard-observation.*"))))
    assert both==2 and {r["pgid"] for r in rows}=={a.pid,b.pid} and counting["leader_running"]
    for p in (a,b):
        os.killpg(p.pid,signal.SIGKILL)
        p.wait(timeout=3)

def term_parent():
    root,env=fixture("terminate-parent",{"leader":[{"gate":"allow-child","decision":decision(done=True)}]})
    p=spawn(root,env,"bash","run.sh")
    leader=wait_until(lambda:starts(root)[0] if starts(root) else None)
    os.kill(p.pid,signal.SIGTERM)
    rc=p.wait(timeout=3)
    child_alive=proc_alive(leader["pid"])
    guard=load(root/"state/harness.json")["leader_running"]
    harness_children=[]
    for path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            args=path.read_bytes()
        except (FileNotFoundError,ProcessLookupError):
            continue
        if str(root/"scripts/harness.sh").encode() in args:
            harness_children.append(int(path.parent.name))
    (root/"allow-child").touch()
    wait_until(lambda:(root/"state/done").exists())
    emit("TERM to entry PID during wake",entry_rc=rc,provider_alive_after_entry=child_alive,
         running_during=guard,harness_pids=harness_children,child_finished_task=(root/"state/done").exists(),
         final_guard=load(root/"state/harness.json")["leader_running"])
    assert rc==-signal.SIGTERM and child_alive and harness_children
    assert not load(root/"state/harness.json")["leader_running"]

def zombie():
    root,env=fixture("zombie-recorded-owner",{"leader":[{"decision":decision(done=True)},{"decision":decision(done=True)}]})
    child=subprocess.Popen(["true"])
    wait_until(lambda:proc_state(child.pid)=="Z")
    a=root/"agents/smoke"
    write_json(a/"status.json",{"state":"running","pid":child.pid})
    (a/"pid").write_text(f"{child.pid}\n")
    write_json(a/"latest.json",{"session_id":"sid","result":"ready for collection","is_error":False})
    rc,out=run(root,env,"bash","scripts/harness.sh")
    during=state(root,"smoke")["state"]
    claimed="still running" in out
    child.wait(timeout=3)
    (root/"state/done").unlink()
    rc2,out2=run(root,env,"bash","scripts/harness.sh")
    emit("recorded zombie PID liveness",rc=rc,zombie_kept_running=during,logged_alive=claimed,
         after_reap_rc=rc2,after_reap_state=state(root,"smoke")["state"],
         archive_count=len(list((a/"runs").glob("*.json"))))
    assert rc==rc2==0 and during=="running" and claimed and state(root,"smoke")["state"]=="done"

globals()[sys.argv[1]]()
PY_EVAL
~~~~

</details>

<details>
<summary>contracts.py</summary>

~~~~bash
cat > "$review_lab/controls/contracts.py" <<'PY_EVAL'
from lab import *
import sys

def errinherit():
    for mode in ("default","inherit"):
        root,env=fixture("subshell-errexit-"+mode,{"leader":[
            {"decision":decision(action("launch","smoke"))},{"decision":decision(done=True)}],
            "smoke":[{"session":"","gate":"release","result":"valid text without session id"}]})
        if mode=="inherit":
            env["BASHOPTS"]="inherit_errexit"
        check_rc, check_out=run(root,env,"bash","-c","shopt inherit_errexit")
        p=spawn(root,env,"bash","run.sh")
        wait_until(lambda:any(r["agent"]=="smoke" for r in starts(root)))
        wait_until(lambda:read(root/"agents/smoke/pid"))
        (root/"release").touch()
        rc,out=finish(p,12)
        a=root/"agents/smoke"
        emit("result collection with "+mode+" command substitution",shopt=check_out.strip(),
             cli_exit=read(a/"exit_code"), result=load(a/"latest.json")["result"],
             rc=rc,state=state(root,"smoke")["state"], pidfile=(a/"pid").exists(),
             archive=len(list((a/"runs").glob("*.json"))), decision_done=(root/"state/done").exists(),
             leader_calls=sum(r["agent"]=="leader" for r in starts(root)))
        if mode=="inherit":
            assert check_rc==0 and rc==1 and state(root,"smoke")["state"]=="running"
            assert (a/"pid").exists() and not (root/"state/done").exists()
        else:
            assert check_rc==1 and rc==0 and state(root,"smoke")["state"]=="done"
            assert not (a/"pid").exists() and (root/"state/done").exists()

def same_stamp():
    root,env=fixture("forced-second-collision",{"leader":[
        {"decision":decision(action("wait")), "result":"Codex trace result"},
        {"decision":decision(done=True),"result":"Claude result overwrites JSON"}]})
    date=root/"fake-bin/date"
    date.write_text("""#!/bin/bash
if [[ "$*" == '-u +%Y%m%dT%H%M%SZ' ]]; then
  printf '%s\n' '20261119T170000Z'
else
  exec /usr/bin/date "$@"
fi
""")
    date.chmod(0o755)
    for provider in ("codex","claude"):
        assert run(root,env,"bash","run.sh","--provider",provider,"--once")[0]==0
    runs=root/"agents/leader/runs"
    rows={f.suffix:read(f) for f in runs.iterdir()}
    emit("same-second cross-provider archives",files=sorted(f.name for f in runs.iterdir()),
         json_result=json.loads(rows[".json"])["result"],
         raw_from_codex="Codex trace result" in rows[".jsonl"],
         executions=len(starts(root)))
    assert len(starts(root))==2 and len(rows)==2 and "Claude result" in rows[".json"] and "Codex trace" in rows[".jsonl"]

def cleanup_tmp():
    root,env=fixture("temporary-instruction-retention",{"leader":[{"decision":decision(action("launch","smoke"))}],
         "smoke":[{"gate":"release", "result":"success"}]})
    rc,out=run(root,env,"bash","run.sh","--once")
    a=root/"agents/smoke"
    wrapper=int(wait_until(lambda:read(a/"pid")))
    (root/"release").touch()
    wait_until(lambda:(a/"exit_code").exists() and not proc_alive(wrapper))
    temp_paths=list(Path(env["TMPDIR"]).glob("instr_*.md"))
    mode=oct(temp_paths[0].stat().st_mode & 0o777)
    state_before_reset=state(root,"smoke")["state"]
    reset_rc,reset_out=run(root,env,"bash","run.sh","--reset")
    emit("single wake and instruction lifetime",rc=rc,ended_without_collecting=state_before_reset,
         exit_record_before_reset=True,instruction_files_before_reset=len(temp_paths),mode=mode,
         reset_rc=reset_rc,instruction_files_after_reset=sum(path.exists() for path in temp_paths),
         cleared_agent=not a.exists(),recorded_instruction=read(temp_paths[0]))
    assert rc==reset_rc==0 and state_before_reset=="running" and not a.exists()
    assert mode=="0o600" and temp_paths[0].exists()

def reset_stop_args():
    root,env=fixture("stop-provider-argument",{})
    a=root/"agents/smoke"
    write_json(a/"status.json",{"state":"running","pid":900000})
    (a/"pid").write_text("900000\n")
    rc,out=run(root,env,"bash","stop.sh","--provider","bad-selection")
    emit("unknown provider on public stop",rc=rc,logged_error="unknown provider" in out,
         pidfile=(a/"pid").exists(),status=state(root,"smoke")["state"],
         missing_helpers=[line for line in out.splitlines() if "command not found" in line])
    assert rc==0 and "unknown provider" in out and not (a/"pid").exists() and state(root,"smoke")["state"]=="running"

def scan_cost():
    for n in (0,12,48):
        root,env=fixture(f"roster-{n}",{"leader":[{"decision":decision(done=True)}]})
        checks=root/"json-reads"
        shim=root/"fake-bin/python3"
        shim.write_text("""#!/bin/bash
if [[ $# == 4 && "$1" == -c && "$3" == */agents/*/status.json ]]; then
  printf '%s\n' "$4" >> "$REVIEW_READ_COUNT"
fi
exec /usr/bin/python3 "$@"
""")
        shim.chmod(0o755)
        env["REVIEW_READ_COUNT"]=str(checks)
        for i in range(n):
            d=root/"agents"/f"fixture{i:02}"
            write_json(d/"status.json",{
              "state":"done","started_at":"2026-01-01T00:00:00Z","finished_at":"2026-01-01T00:01:00Z",
              "instruction_summary":"a"*200})
            (d/"output.md").write_text("b"*500)
        t=time.monotonic()
        rc,out=run(root,env,"bash","run.sh","--once",timeout=15)
        result=starts(root)[0]
        readings=(read(checks) or "").splitlines()
        emit("leader status prompt scaling",roster=n,rc=rc,status_reads=len(readings),
             prompt_bytes=result["prompt_bytes"],seconds_to_provider=round(result["monotonic"]-t,3),
             keys=sorted(set(readings)))
        assert rc==0 and len(readings)==4*n and result["prompt_bytes"]>n*700

globals()[sys.argv[1]]()
PY_EVAL
~~~~

</details>

<details>
<summary>blocked.py</summary>

~~~~bash
cat > "$review_lab/controls/blocked.py" <<'PY_EVAL'
from lab import *

root,env=fixture("foreground-leader-spans-heartbeat",{
    "leader":[{"decision":decision(action("launch","trigger"),action("launch","late"))},
              {"gate":"end-leader","gate_timeout":218,"decision":decision(action("wait"))},
              {"decision":decision(done=True)}],
    "trigger":[{"gate":"finish-trigger"}], "late":[{"gate":"finish-late","gate_timeout":215}]})
p=spawn(root,env,"bash","run.sh")
def started(agent,n=1):
    return next((row for row in starts(root) if row["agent"]==agent and row["attempt"]==n),None)

for name in ("trigger","late"):
    wait_until(lambda:started(name))
    wait_until(lambda:read(root/f"agents/{name}/pid"))
(root/"finish-trigger").touch()
wake=wait_until(lambda:started("leader",2),10)
owner=int(read(root/"agents/late/pid"))
(root/"finish-late").touch()
wait_until(lambda:(root/"agents/late/exit_code").exists() and not proc_alive(owner))
begin=load(root/"state/harness.json")
for mark in (8,60,184):
    deadline=wake["monotonic"]+mark
    remaining=deadline-time.monotonic()
    if remaining>0:
        time.sleep(remaining)
    mid=load(root/"state/harness.json")
    state_mid=state(root,"late")["state"]
    leader_count=len([row for row in starts(root) if row["agent"]=="leader"])
    emit("during foreground leader",elapsed=round(time.monotonic()-wake["monotonic"],3),raw_result=load(root/"agents/late/latest.json")["result"],
         worker_state=state_mid,worker_pid_alive=proc_alive(owner),tick=mid["tick_count"],
         leader_running=mid["leader_running"], last_woken=mid["leader_last_woken_at"], leader_count=leader_count)
    assert mid==begin and state_mid=="running" and leader_count==2 and not proc_alive(owner)
(root/"end-leader").touch()
rc,out=finish(p,14)
emit("after foreground leader yields",rc=rc,status=state(root,"late")["state"],
     leader_count=len([row for row in starts(root) if row["agent"]=="leader"]),
     done=(root/"state/done").exists(),time_after_leader_start=round(time.monotonic()-wake["monotonic"],3),
     leader_spinner_lines=len([l for l in out.splitlines() if "[leader] working" in l]))
assert rc==0 and state(root,"late")["state"]=="done" and started("leader",3)
PY_EVAL
~~~~

</details>

<details>
<summary>observability.py</summary>

~~~~bash
cat > "$review_lab/controls/observability.py" <<'PY_EVAL'
from lab import *
import sys

def live_projection():
    root,env=fixture("live-raw-vs-projection",{"leader":[
        {"decision":decision(action("launch","smoke"))},
        {"decision":decision(done=True)}],
        "smoke":[{"gate":"release","gate_timeout":44, "live_events":[
            {"type":"thread.started","thread_id":"live-session"},
            {"type":"item.started","item":{"type":"agent_message","text":"x"*4096}}],
            "result":"fresh completion"}]})
    d=root/"agents/smoke"
    write_json(d/"status.json",{"state":"idle","pid":None})
    write_json(d/"latest.json",{"result":"old result","is_error":False})
    (d/"output.md").write_text("old markdown")
    p=spawn(root,env,"bash","run.sh")
    old_bytes=(d/"latest.json").stat().st_size
    raw_bytes=wait_until(lambda:(d/"latest.jsonl").stat().st_size
        if (d/"latest.jsonl").exists() and (d/"latest.jsonl").stat().st_size>4096 else None)
    wait_until(lambda: "Agents: smoke=running" in read(p.review_output),37)
    summary=next(l for l in read(p.review_output).splitlines() if "Agents: smoke=running" in l)
    mid=load(d/"latest.json")["result"]
    log_before=read(root/"logs/harness.log")
    (root/"release").touch()
    rc,out=finish(p,12)
    emit("active Codex transport versus harness status",rc=rc,raw_bytes=raw_bytes,
         compat_bytes=old_bytes,summary=summary,mid_result=mid,
         final_result=load(d/"latest.json")["result"],
         live_event_rendered="x"*100 in log_before,ends=state(root,"smoke")["state"])
    assert rc==0 and f", {old_bytes}B)" in summary and mid=="old result"
    assert load(d/"latest.json")["result"]=="fresh completion" and "x"*100 not in log_before

def stop_on_timeout():
    root,env=fixture("leader-action-stop-on-timeout",{"leader":[
        {"decision":decision(action("launch","smoke"))},
        {"decision":decision(action("stop","smoke"))},
        {"decision":decision(done=True)}],
        "smoke":[{"gate":"release", "gate_timeout":220, "result":"worker still completed"}]})
    p=spawn(root,env,"bash","run.sh")
    owner=wait_until(lambda:next((r for r in starts(root) if r["agent"]=="smoke"),None))
    wait_until(lambda:read(root/"agents/smoke/pid"))
    wait_until(lambda:len([r for r in starts(root) if r["agent"]=="leader"])==2,200)
    out=p.review_output
    wait_until(lambda:read(out).count("Decisions executed.")==2)
    live=proc_alive(owner["pid"])
    st=state(root,"smoke")["state"]
    still_has_pid=(root/"agents/smoke/pid").exists()
    observed=[r for r in starts(root) if r["agent"]=="leader"]
    delta=observed[1]["monotonic"]-observed[0]["monotonic"]
    (root/"release").touch()
    rc,log=finish(p,12)
    emit("real periodic wake with stop request",rc=rc,timeout_delta=round(delta,3),stop_decision_consumed=True,
         provider_alive_after_stop=live,state_after_stop=st,pid_after_stop=still_has_pid,
         final=state(root,"smoke")["state"],
         stopped_message="Stopped smoke" in log)
    assert rc==0 and delta>=180 and live and st=="running" and still_has_pid
    assert state(root,"smoke")["state"]=="done" and "Stopped smoke" not in log

globals()[sys.argv[1]]()
PY_EVAL
~~~~

</details>

<details>
<summary>malformed.py</summary>

~~~~bash
cat > "$review_lab/controls/malformed.py" <<'PY_EVAL'
from lab import *
import sys

def status_matrix():
    payloads=[("empty-object",{}, "done"),
              ("no-text",{"session_id":"valid-session","is_error":False},"done"),
              ("string-false",{"session_id":"valid-session","is_error":"false","result":"valid text"},"error"),
              ("array",["not an object"],"error")]
    for name,payload,expected in payloads:
        root,env=fixture(f"claude-result-{name}",{"leader":[{"decision":decision(action("launch","smoke"))},
                                                           {"decision":decision(done=True)}],
                      "smoke":[{"gate":"release","payload":payload}]},provider="claude")
        p=spawn(root,env,"bash","run.sh")
        wait_until(lambda:any(r["agent"]=="smoke" for r in starts(root)))
        wait_until(lambda:read(root/"agents/smoke/pid"))
        (root/"release").touch()
        rc,out=finish(p,12)
        d=root/"agents/smoke"
        emit("opaque normalized Claude payload",name=name, rc=rc, state=state(root,"smoke")["state"],
             exit_code=read(d/"exit_code"), session=read(d/"session_id"),
             markdown=read(d/"output.md"), payload=load(d/"latest.json"))
        assert rc==0 and state(root,"smoke")["state"]==expected

def monitor_truncation():
    root,env=fixture("monitor-prefix",{})
    err=root/"test.stderr"
    prefix="x"*80
    err.write_text(prefix+"-first\n")
    result=run(root,env,"bash","-c", r'''
source scripts/lib.sh
mapfile -t a < <(activity_monitor_stderr_state test.stderr "" 80 "stderr: ")
printf '%s\n' "${a[1]}"
printf '%s\n' "$1" >> test.stderr
mapfile -t b < <(activity_monitor_stderr_state test.stderr "${a[0]}" 80 "stderr: ")
printf 'suffix-after-a-different-line=%s\n' "${b[1]-}"
printf '%s\n' 'different prefix' >> test.stderr
mapfile -t c < <(activity_monitor_stderr_state test.stderr "${b[0]}" 80 "stderr: ")
printf 'suffix-after-different-prefix=%s\n' "${c[1]-}"
''',"_",prefix+"-second")
    emit("monitor deduplication after truncation",rc=result[0], output=result[1].splitlines())
    assert "suffix-after-a-different-line=\n" in result[1]
    assert "suffix-after-different-prefix= | stderr: different prefix" in result[1]

globals()[sys.argv[1]]()
PY_EVAL
~~~~

</details>

<details>
<summary>restart_live.py</summary>

~~~~bash
cat > "$review_lab/controls/restart_live.py" <<'PY_EVAL'
from lab import *
import sys

def started(root,agent,n=1):
    return next((r for r in starts(root) if r["agent"]==agent and r["attempt"]==n),None)

def active(entry):
    root,env=fixture("crash-live-worker-"+entry,{
        "leader":[{"decision":decision(action("launch","smoke"))},
                  {"decision":decision(action("wait"),
                                       done=entry=="public")},
                  {"decision":decision(done=True)}],
        "smoke":[{"gate":"release","result":"same worker from old supervisor"}]})
    p=spawn(root,env,"bash","run.sh")
    worker=wait_until(lambda:started(root,"smoke"))
    owner=int(wait_until(lambda:read(root/"agents/smoke/pid")))
    parent_file=Path(f"/proc/{p.pid}/task/{p.pid}/children")
    def supervisor_pid():
        for pid in (read(parent_file) or "").split():
            try:
                argv=Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            except FileNotFoundError:
                continue
            if str(root/"scripts/harness.sh").encode() in argv:
                return int(pid)
        return None
    pid=wait_until(supervisor_pid)
    os.kill(pid,signal.SIGKILL)
    previous_rc, previous_log=finish(p,4)
    live_after_crash=proc_alive(worker["pid"]) and proc_alive(owner)
    assert previous_rc==137 and live_after_crash and state(root,"smoke")["state"]=="running"

    next_entry="scripts/harness.sh" if entry=="direct" else "run.sh"
    successor=spawn(root,env,"bash",next_entry)
    resumed=wait_until(lambda:started(root,"leader",2))
    observed=state(root,"smoke")["state"]
    if entry=="direct":
        retained=proc_alive(owner) and proc_alive(worker["pid"])
        assert observed=="running" and retained and int(read(root/"agents/smoke/pid"))==owner
        (root/"release").touch()
    else:
        wait_until(lambda:not proc_alive(worker["pid"]))
        retained=proc_alive(worker["pid"])
        assert observed=="idle" and not retained
    successor_rc, successor_out=finish(successor,12)
    final=state(root,"smoke")["state"]
    archives=list((root/"agents/smoke/runs").glob("*.json"))
    emit("live process across supervisor crash",entry=entry,first_rc=previous_rc,supervisor_pid=pid,
         original_worker=worker["pid"],live_after_crash=live_after_crash,after_restart=observed,
         retained_live=retained, leader_resumed=resumed["resume"],successor_rc=successor_rc,
         bootstrap_retained_log="still running" in successor_out,final=final,
         collected=[load(f)["result"] for f in archives])
    assert successor_rc==0 and resumed["resume"]=="codex-leader-1"
    if entry=="direct":
        assert final=="done" and [load(f)["result"] for f in archives]==["same worker from old supervisor"]
    else:
        assert final=="idle" and not archives

def bad_launch():
    root,env=fixture("launcher-rejection",{})
    write_json(root/"state/decisions/latest.json",decision(action("launch",instruction="missing agent name", agent="")))
    before=list(Path(env["TMPDIR"]).glob("*"))
    rc,out=run(root,env,"bash","scripts/execute_decisions.sh")
    after=list(Path(env["TMPDIR"]).glob("instr_*.md"))
    observed_agents=list((root/"agents").glob("*"))
    emit("dispatcher acknowledgment with rejected launcher",rc=rc, reported_executed="Decisions executed." in out,
         provider_invocations=len(starts(root)),agent_dirs=len(observed_agents),
         before_temp=len(before),after_temp=len(after),
         usage_visible="Usage: launch_subagent" in out)
    assert rc==0 and not starts(root) and not observed_agents and len(after)==1 and "Decisions executed." in out
    control_rc,control_out=run(root,env,"bash","scripts/launch_subagent.sh","",str(after[0]))
    assert control_rc==1 and "Usage: launch_subagent" in control_out

def reset_drain():
    root,env=fixture("reset-with-live-provider",{"leader":[{"decision":decision(action("launch","smoke"))}],
        "smoke":[{"gate":"release","ignore_term":True,
                  "write_after":{"output/after-reset.md":"late fixture write"}}]})
    once_rc, _=run(root,env,"bash","run.sh","--once")
    w=wait_until(lambda:started(root,"smoke"))
    wait_until(lambda:any(r["event"]=="configured" and r["agent"]=="smoke" for r in trace(root)))
    reset_rc,out=run(root,env,"bash","run.sh","--reset")
    alive=proc_alive(w["pid"])
    observed=not (root/"agents/smoke").exists()
    (root/"release").touch()
    wait_until(lambda:(root/"output/after-reset.md").exists())
    emit("reset while provider ignores TERM",once_rc=once_rc, reset_rc=reset_rc,
         state_dir_cleared=observed,provider_alive_after_reset=alive,
         ignored_term=any(r["event"]=="ignored-term" for r in trace(root)),
         post_reset_artifact=read(root/"output/after-reset.md"))
    assert once_rc==reset_rc==0 and alive and observed
    assert any(r["event"]=="ignored-term" for r in trace(root))

globals()[sys.argv[1]](*sys.argv[2:])
PY_EVAL
~~~~

</details>

### Supplemental scheduling and suite tracing controls

<details>
<summary>schedule_probe.py</summary>

~~~~bash
cat > "$review_lab/controls/schedule_probe.py" <<'PY_EVAL'
from lab import *
from concurrent.futures import ThreadPoolExecutor
import sys

def sample():
    def trial(index):
        root,env=fixture(f"ordinary-launch-{index:02}",{
            "leader":[{"decision":decision(action("launch","smoke"))},
                      {"decision":decision(done=True)}],
            "smoke":[{"pause":0.07,"result":"ordinary successful worker"}]})
        p=spawn(root,env,"bash","run.sh")
        rc,out=finish(p,18)
        wait_until(lambda:(root/"agents/smoke/exit_code").exists())
        status=state(root,"smoke")
        return dict(trial=index,rc=rc,status=status["state"],gap="PID file missing while state=running" in out,
                    result=load(root/"agents/smoke/latest.json")["result"])
    with ThreadPoolExecutor(max_workers=4) as executor:
        results=list(executor.map(trial,range(20)))
    emit("uninstrumented launch sample", count=len(results),
         observed_gaps=sum(row["gap"] for row in results),
         states={state:sum(row["status"]==state for row in results) for state in ("done","error")},
         nonzero_exits=[row for row in results if row["rc"]],
         cases_with_gaps=[row for row in results if row["gap"]])
    assert all(row["rc"]==0 and row["result"]=="ordinary successful worker" for row in results)
    assert all(row["status"]==("error" if row["gap"] else "done") for row in results)

def example():
    groups=("puzzle_group","story_group","operations_group")
    initial=[action("create_role",agent,prompt=f"Fixture role for {agent}") for agent in groups]
    initial.extend(action("launch",agent,effort="low") for agent in groups)
    root,env=fixture("checked-in-demo-input",{
        "leader":[{"decision":decision(*initial)},
                  {"decision":decision(done=True),
                   "write":{"output/mini_escape_room_demo.md":"Fixture synthesis output\n"}}],
        **{agent:[{"gate":"release", "result":f"Fixture result from {agent}"}] for agent in groups}})
    for filename in ("leader.md","inbox.md"):
        shutil.copyfile(root/"examples/mini-escape-room"/filename,root/filename)
    p=spawn(root,env,"bash","run.sh","--provider","codex","--effort","low")
    worker_rows=wait_until(lambda:[r for r in starts(root) if r["agent"] in groups]
                           if len([r for r in starts(root) if r["agent"] in groups])==3 else None,12)
    assert all(proc_alive(r["pid"]) for r in worker_rows)
    for agent in groups:
        wait_until(lambda:read(root/f"agents/{agent}/pid"))
    (root/"release").touch()
    rc,out=finish(p,12)
    first=read(root/"seen/leader.1.txt")
    final=read(root/"seen/leader.2.txt")
    dest=root/"output/mini_escape_room_demo.md"
    emit("shipped demo inputs on local fake provider",rc=rc,
         prompt_contains_shipped_task="The Missing Birthday Cake" in first,
         prompt_contains_shipped_inbox="No follow-up yet" in first,
         final_contains_all_groups=all(f"Fixture result from {name}" in final for name in groups),
         states={name:state(root,name)["state"] for name in groups},
         passed_effort=[r["effort"] for r in worker_rows],artifact=str(dest.relative_to(root)))
    assert rc==0 and "The Missing Birthday Cake" in first and "No follow-up yet" in first
    assert all(f"Fixture result from {name}" in final and state(root,name)["state"]=="done" for name in groups)
    assert read(dest)=="Fixture synthesis output\n" and all(r["effort"]=="low" for r in worker_rows)

globals()[sys.argv[1]]()
PY_EVAL
review_case schedule_probe.py example
review_case schedule_probe.py sample
~~~~

</details>

<details>
<summary>Standalone Python helper line trace of the bundled suite</summary>

~~~~bash
mkdir -p "$review_lab/line-observer" "$review_lab/line-results"
cat > "$review_lab/line-observer/sitecustomize.py" <<'PY_OBSERVER'
import atexit
import json
import os
from pathlib import Path
import sys

helpers = {"codex_effort.py","codex_jsonl_to_compat.py","codex_retry_policy.py",
           "stop_state.py","stream_processor.py"}
observed = {}

def record(frame,event,arg):
    filename = frame.f_code.co_filename
    name = filename.rsplit("/",1)[-1]
    if name not in helpers or "/scripts/" not in filename:
        return None
    if event == "line":
        observed.setdefault(name,set()).add(frame.f_lineno)
    return record

def flush():
    if observed:
        target=Path("/lab/line-results") / f"lines-{os.getpid()}.json"
        # PID namespaces for this metric are not run concurrently.
        target.write_text(json.dumps({name:sorted(lines) for name,lines in observed.items()}))
atexit.register(flush)
sys.settrace(record)
PY_OBSERVER
review_offline /usr/bin/env PYTHONPATH=/lab/line-observer \
  /usr/bin/python3 -m unittest discover -s tests -p 'test_*.py'
review_offline /usr/bin/python3 - <<'PY'
from pathlib import Path
from types import CodeType
from collections import defaultdict
import json
lines = defaultdict(set)
for p in Path("/lab/line-results").glob("*.json"):
    for name, covered in json.loads(p.read_text()).items():
        lines[name].update(covered)
def executable(code):
    line_set = {n for _, _, n in code.co_lines() if n and n > 0}
    for child in code.co_consts:
        if isinstance(child, CodeType):
            line_set.update(executable(child))
    return line_set
for p in sorted(Path("/source/scripts").glob("*.py")):
    scope = executable(compile(p.read_bytes(), str(p), "exec"))
    print(p.name, len(lines[p.name]), len(scope))
PY
~~~~

</details>

The lab directories and fixture subprocesses are disposable. After all fixture commands exit, remove only that newly created lab directory and rerun the pin and cleanliness checks against the original checkout. The assessment did not modify any tracked source or use a Git write operation.

## 10. Prioritized improvements and acceptance criteria.

| Priority | Change | Acceptance criterion |
| --- | --- | --- |
| **P0** | Fix both public invocation modes and give the supervisor one process ownership path. Set executable bits or change all documented entry commands. Acquire an OS-backed per-root supervisor lock before coordinator side effects. Use a deliberate process group or equivalent job handle, publish its identity with an accepted run, and implement action stop and public stop through the same TERM, grace, escalation and reap logic. | A fresh documented invocation passes. Two simultaneous starts admit one scheduler and one leader. A stop action stops cooperative workers and descendants, confirms shutdown of a TERM-resistant fake after escalation, and leaves durable `cancelled` evidence. A bare zombie or reused PID cannot be mistaken for the owned active process. |
| **P0** | Make process result capture unconditional and separate attempts. Replace implicit `errexit` handling around external commands with explicit status capture. Record provider, process exit, application outcome, stream paths, and session availability together for an immutable attempt ID. Publish `latest` after the attempt is finalized. | Exit 42 always appears in an attempt record, enters bounded retry when classified transient, and cannot publish a prior success as the new result. Missing or invalid session pointers leave a clear state and permit deterministic recovery. A same-name launch while active is refused or queued with its own attempt ID. |
| **P1** | Validate an entire decision before executing it. Bind it to a task and wake ID, commit atomically, classify malformed output explicitly, and acknowledge action IDs with idempotent dispatch. Route file and fenced inputs through the same parser. Make terminal commit require a drained or explicitly cancelled required-work set. | Existing, missing and malformed prior decisions cannot cause stale launches, successful extraction produces a usable modern decision once, and a failed validation leaves all earlier files intact. Replaying a decision after interruption does not start a second copy. Starting a follow-up from a completed task preserves history and uses a new completion marker. |
| **P1** | Reconcile durable attempts before replacing their owners. Keep provider metadata with each attempt and treat session IDs as provider-native capabilities. Define when a switch back takes a native resume and when it receives a cross-provider delta. Publish current Markdown from the same result generation. | Startup recovers valid raw and normalized outcomes with or without a PID file and can distinguish cancelled, interrupted, and failed attempts. A Codex restart never binds a Claude ID as native. A→B→A preserves B's finished context. Claude Markdown and JSON agree after resume, and same-second attempts cannot share archive paths. |
| **P1** | Separate supervision from model scheduling and add explicit limits. Poll or reap workers while the single-flight leader runs. Add attempt and task deadlines, bounded retry with jitter and a permanent-failure path, and configurable provider and worker admission. | A leader stalled beyond 180 seconds leaves worker completions and cancellation responsive. Prolonged transient failures terminate within a configured budget and leave per-attempt evidence. Admission stays within a configured maximum, with the rest queued or refused visibly. |
| **P2** | Harden the extension and workspace contract. Identify the CWD explicitly for both adapters, bound prompts or use documented input channels for long content, confine role naming and output roots, and declare which authority and settings pass to each provider. Avoid loading private shell configuration implicitly for unattended execution. Make inspection output correlate task, decision, agent, and attempt, and cover raw-byte ingestion separately from logical progress. | Caller CWD cannot divert role/decision files. Oversized notes fail early with a usable error or arrive through a supported streaming input. A new adapter can be validated against a versioned result and session contract. Logs allow a single attempt to be traced from admission to collection, and instructions and retry artifacts have defined retention. |
| **P2** | Keep a credential-free integration test lane beside the unit tests. Have fake CLIs cover direct and fenced decisions, signal and exit ordering, restart across providers, redirection, ordinary app errors, and deterministic interleavings. Add a real-provider contract check only in an environment where that provider is configured for it. | CI exercises the tracked permission modes, both adapters through the public entry path, the previously failing controls, and clean copy isolation. A contributor can verify failures from process traces and archived inputs independently of provider availability. |

The highest-priority tests target ownership and correctness across process exit, restart, and repeated decisions. The existing adapters, readable runtime views, and prompt-defined work split remain useful once those boundaries become explicit.
