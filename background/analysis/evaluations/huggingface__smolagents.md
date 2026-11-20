# smolagents core-runtime evaluation

## 1. Snapshot, scope, and elapsed-time evidence

| Field | Value |
| --- | --- |
| Repository | `huggingface/smolagents` |
| Checkout | `repos/huggingface__smolagents`, detached HEAD |
| Commit | `2689e450364d451a0afa0a5e883d12a031c125dd` |
| Tree | `40faae9d14cea003a64156ae28ed7455783c691e` |
| Pinned change | Support starred and iterable unpacking in assignments (#2556) |
| Package version | `1.27.0.dev0` |
| UTC start | `2026-11-19 03:29:39 UTC` |
| UTC end | `2026-11-19 03:59:45 UTC` |
| Elapsed active minutes | `30.10` |
| Checkout integrity | Exact HEAD and empty porcelain status at intake and close. Final status included ignored paths. The Git tree ID matched and `git diff --check` was clean. |

I read the evaluation protocol, the repository’s `AGENTS.md`, the applicable ancestor `$HOME/AGENTS.md`, and `CONTRIBUTING.md`. Searches of tracked and hidden files found no more specific instructions under the pinned checkout. The protocol's combined strengths and weaknesses item is covered in sections 4 and 5. UTC comes from the clock tool. The elapsed interval covers source tracing, offline setup, repository tests, new behavioral checks, analysis, report writing, and evidence verification. I performed source analysis and designed probes while test processes ran. [Evaluation protocol](./README.md), [repository instructions](repos/huggingface__smolagents/AGENTS.md), [ancestor instructions]($HOME/AGENTS.md), [pyproject.toml:5–22][src-1], [CONTRIBUTING.md:35–57][src-2].

Scope covers `MultiStepAgent`, both concrete agent loops, the model and tool contracts, delegation, memory and state, executor lifecycle and transfer, streaming, failure and cancellation semantics, concurrency, monitoring, and extension points. The review uses docs and examples solely as evidence about runtime contracts. Scope excludes UI, deployment and site machinery, marketing, and security testing. All execution used local scripted inputs, cached packages, and test doubles at external interfaces. Test processes ran with a clean environment and home, a network namespace containing only loopback, and the pinned checkout mounted read-only. Test artifacts lived in a disposable disk-backed directory outside the checkout. See sections 7 and 10 for exact scope and commands.

Work phases used for the elapsed-time audit

| UTC boundary | Work completed since preceding boundary |
| --- | --- |
| 03:32:15 | Read instructions and core loop, pinned the checkout, established an offline dependency and test harness, and analyzed the first broad result. |
| 03:35:32 | Traced both action paths, reran the filtered suite, and reproduced loop lifecycle, fallback, budget, and accounting behavior. |
| 03:38:55 | Investigated gated fan-out, child state ownership, local timeout and remote tool preparation. |
| 03:42:04 | Compared model wrapper requests, retries and stops and validated the Bedrock payload against SDK schema. Reproduced with a second interpreter and started the archive install check. |
| 03:45:02 | Audited Transformers streamer and extension contracts, warnings and SDK coverage. |
| 03:53:53 | Wrote the evaluation, added source and transport controls, reran stock selections and exercised the runnable appendix. |
| Closing interval | Measured repeated stream work, checked request pacing and reviewed source links, evidence, artifacts and checkout integrity. |

**Verdict.** The core is a readable, useful implementation of a stateful ReAct loop. Both action styles work with small typed model and tool fixtures, and broad offline tests corroborate the happy path. The main limit is lifecycle correctness under interruptions and overlapping work. The agent instance owns state that callers can mistakenly treat as run-scoped, while batch execution can perform work that the next model request cannot see. Fix run termination and result accounting before extending the orchestration surface.

## 2. Core architecture and end-to-end control and data flow

### 2.1 Common driver and orchestration state

`MultiStepAgent` owns a model, tools, managed-agent instances, prompt templates, an agent-level `state` dictionary, a conversation ledger, callbacks, a logger, and a monitor. Tool and child maps are keyed by name. Construction provisions `final_answer`, optionally adds base tools, and checks supplied names for collisions. Both subclasses render their system prompts from Jinja templates. The executor, where present, is also attached to the agent instance. [agents.py:294–352,354–434,1258–1274,1543–1585,1620–1636][src-3].

1. **Prepare.** `run()` resolves the action budget, clears the interruption flag, merges `additional_args` into `state`, and adds their textual representation to the task. It recomputes the system prompt, optionally resets history and metrics, and appends `TaskStep`. `CodeAgent` sends variables followed by the merged tools and child callables to its executor. These operations happen before the returned generator is advanced. [agents.py:436–496][src-4].
2. **Plan.** `_run_stream()` starts step numbering at one. If enabled, planning precedes the action at step one and at the configured interval. A fresh history gets a task and tool plan prompt. Subsequent plans take the summary projection of prior actions, dropping the old system prompt and prior plans, with an updated planning directive. A planning call sits outside the action exception handler. The planning object is yielded, then timed, passed to callbacks, and appended on the next advance. [agents.py:540–567,639–747][src-5], [memory.py:92–150,174–206][src-6].
3. **Act.** The subclass projects memory to messages, calls the model, interprets the answer, invokes tools or an executor, and emits events. The outer loop treats `ActionOutput.is_final_answer` as a candidate, runs configured answer checks, and marks the action accepted. Domain `AgentError` instances become feedback for the next step. `AgentGenerationError` aborts. Action finalization calls callbacks, appends memory, and yields the finalized `ActionStep`. [agents.py:569–624,758–787][src-7], [memory.py:126–150][src-8], [utils.py:92–137][src-9].
4. **Finish.** A final candidate accepted in the normal loop reaches `FinalAnswerStep` after type conversion. Exhaustion runs a separate `model.generate()` over the history and a fallback prompt, records a synthetic action at `max_steps + 1` with `AgentMaxStepsError`, and emits a final best-effort answer. In non-stream mode, `run()` consumes the generator to completion and optionally constructs `RunResult` with output, history, token counts, timing, and a success or exhaustion state. The step budget governs action dispatches. Planning, fallback generation, child calls, and the number of tools within an action add work beyond that count. [agents.py:498–538,606–637,810–853][src-10], [agent_types.py:254–281][src-11].

### 2.2 ToolCallingAgent

The model sees tool and child descriptors plus a textual system prompt. Native tool calls enter the runtime as `ChatMessageToolCall` records. If the assistant provides text only, `Model.parse_tool_calls()` looks for the JSON name/arguments form and builds a call ID. `ToolCallingAgent` normalizes JSON arguments and emits `ToolCall` records before dispatch. For a tool, it resolves top-level string references in `state`, checks the declared input schema, unwraps supported agent value containers, and calls `Tool.forward()` through `Tool.__call__()`. Child calls use the same admission path and execute the child callable directly. [agents.py:1260–1325,1327–1336,1361–1400,1444–1502][src-12], [models.py:193–201,288–329,416–431,599–610][src-13], [tools.py:228–256,1361–1412][src-14], [agent_types.py:254–281][src-11].

A single call runs inline. A multi-call action creates a bounded `ThreadPoolExecutor` with a fresh context copy for each worker. Tool results are emitted as they complete. The completed action's call records and observation lines are sorted by call ID, so memory serialization has a deterministic order for a fully successful batch. Image and audio tool outputs go into agent state and appear to the model as named references. Ordinary results become text observations. A final answer is modeled as one call to the reserved `final_answer` name, with an optional lookup of a returned state key. [agents.py:1335–1359,1373–1442][src-15], [prompts/toolcalling_agent.yaml:5–25][src-16].

### 2.3 CodeAgent and execution boundaries

`CodeAgent` requests tagged code or a `{thought, code}` JSON document. It negotiates stop strings, appends a closing tag to unstructured output when needed, parses code, and applies a final-answer variable-name repair. It emits a synthetic `python_interpreter` call for the action. `PythonExecutor` has three required methods, `send_tools`, `send_variables`, and `__call__`, with `CodeOutput(output, logs, is_final_answer)` as the result. CodeAgent adds logs and a truncated display of the result to the action record, keeps the raw result in `action_output`, and yields an `ActionOutput`. The concrete CodeAgent context manager looks for an optional `cleanup()` on its executor. [agents.py:1527–1541,1583–1618,1638–1764][src-17], [models.py:43–64][src-18], [utils.py:189–251][src-19], [local_python_executor.py:332–357,1698–1713][src-20].

The local executor keeps a namespace and user-defined functions between calls. It parses Python into AST nodes, evaluates the supported subset, counts AST operations, captures prints, and wraps the configured final tool with an internal control transfer. That transfer returns the answer with the terminal bit even when it happens inside a helper. The architecture supports loops, intermediate variables, and compositions of several tools within one action. Expanded destructuring at the pinned commit passed the stock assignment tests. [local_python_executor.py:1445–1597,1600–1695,1716–1793][src-21], [tests/test_local_python_executor.py:644–699][src-22], [tests/test_agents.py:562–571,615–632][src-23].

`RemotePythonExecutor` shares the same call shape. It emits source for tools plus a runtime deserializer for variables, managers of individual backends provision a persistent execution context, and completion decoding turns the remote final-answer signal into `CodeOutput`. E2B decodes SDK outputs and errors. Docker, Modal, and Blaxel share a WebSocket/Jupyter path keyed by request ID and terminated on the matching idle message. Their cleanup hooks differ. The built-in remote CodeAgent factory rejects managed agents explicitly. Local tools carry Python objects and host callback behavior, while transfer and rehydration are additional contracts for remote tools. [agents.py:1593–1618][src-24], [remote_executors.py:53–141,306–448,450–529,679–709,813–835,963–980,1049–1069][src-25], [serialization.py:45–59,173–249,451–507][src-26].

### 2.4 Delegation, memory projections, and observability

A managed child has a name, a description, a declared `task` field, and optional `additional_args`. A CodeAgent using the local executor passes child instances as callable tools. A ToolCallingAgent publishes them alongside regular tools. `MultiStepAgent.__call__()` makes a child-specific task, invokes the child's regular run, wraps output in a textual report, and can include a concise history projection. Each child resolves its own step budget and memory reset. The parent sees report text rather than the child's typed progress stream or a hierarchical result, and its monitor accounts for its own model calls. This is synchronous composition with optional tool-call parallelism. [agents.py:369–387,490–492,868–890,1260–1263,1453–1502][src-27], [monitoring.py:81–117][src-28], [tests/test_agents.py:2511–2565][src-29].

Memory has a live system prompt and a mutable list of `TaskStep`, `PlanningStep`, and `ActionStep` records. Model inputs are a projection of records, with internal `tool-call` and `tool-response` roles flattened to assistant/user roles in the shared model adapters unless configured otherwise. These messages use textual call and observation descriptions. `get_clean_message_list()` copies inputs before role changes and image conversion, then joins adjacent messages of the same role. Summary mode omits some reasoning and plans while retaining task, calls, outcomes, and errors. `AgentMemory` can expose full or succinct step dictionaries and replay recorded data. This is a transcript projection. Configuration persistence goes through `to_dict()` / `from_dict()` and folder methods, which recreate model and tool definitions from supported classes and source. [agents.py:758–770,892–947,970–1062,1118–1158][src-30], [memory.py:50–206,214–277][src-31], [models.py:282–285,332–413,518–567][src-32].

There are two independent streaming switches. `run(stream=True)` returns the orchestration iterator, even with a non-streaming model. `stream_outputs=True` enables provider deltas inside action or plan generation, even if `run()` drains internally. The aggregate action content holds text, indexed call fragments, and token usage. Visible events can include deltas, tool calls and results, action candidate outputs, plan and action records, and `FinalAnswerStep`. The final event identifies the terminal output. In the exhaustion path it carries best-effort output without a separate stream status. `CallbackRegistry` dispatches by record type through the method resolution order. `Monitor` uses the action callback to count durations and available tokens, while `RunResult` sums planning and action usage across retained history with an unknown-usage check. [agents.py:256–265,416–434,494–535,554–611,620–623,1291–1325,1655–1674][src-33], [models.py:203–279][src-34], [memory.py:280–316][src-35], [monitoring.py:36–117][src-36].

## 3. Why the design works and its governing invariants

| Invariant or working assumption | How it helps | Observable boundary at this pin |
| --- | --- | --- |
| The model proposes an action, and the agent runtime owns execution and iteration. | Local models, API wrappers, and scripted implementations fit the same loop. A caller can exercise the entire path with a handwritten `ChatMessage`. | `generate()` and optional `generate_stream()` are separate capability contracts. A `ChatMessage` field can still be accepted by one layer and mishandled by another. [models.py:123–157,468–610][src-37], [agents.py:1276–1360,1638–1764][src-38]. |
| A step has distinct proposed action, result, and history representations. | Debugging can inspect parsed action, model messages, errors, and observations. The next model call receives actionable feedback. | Tool events can escape before step commit. Memory can lose per-call outcomes after partial failure. [agents.py:577–605,1373–1442][src-39], [memory.py:51–150][src-40]. |
| The terminal bit belongs to the runtime's action result, followed by answer validation. | Both agents accepted explicit `None`, `False`, and `0` final values in one action with `RunResult.state == "success"`. The accepted terminal record is independent of the value's truthiness. | The exhaustion route is a separate best-effort outcome. Stream consumers need `FinalAnswerStep` or finalized step status after checks. [agents.py:582–637,1356–1359,1763–1764][src-41], [local_python_executor.py:1658–1682][src-42]. |
| The action allowance is checked at the common loop boundary. | Code and tool users get one place to reason about budgets and default recovery. | This bounds action turns. A turn can include setup, planning, multiple effects, or nested child work. Interrupt currently shares the turn boundary. [agents.py:540–611,754–756,868–876][src-5]. |
| A concrete agent instance is effectively single-flight. | The memory, executor state, and callbacks can be inspected or deliberately edited in place. Sequential continuing runs are straightforward. | This assumption is implicit, and parallel dispatch can violate it through repeated calls to one managed child. Direct overlapping streams also share setup state. [agents.py:328–352,468–496,540–605,1425–1434][src-43]. |
| Each successful parallel action has uniquely identified calls. | Completion order can drive the live callback experience while an ID sort stabilizes memory. | The model adapter carries call IDs. A malformed duplicate ID reaches a map overwrite instead of an admission error. [agents.py:1373–1380,1425–1442][src-44], [models.py:239–274][src-45]. |
| A persistent executor namespace and conversational history have separate lifetimes. | Code can bind values and helpers for later snippets. Tool users can reference application-provided data by name. | `reset=True` is a conversation and metrics reset. The application and executor state survive. [agents.py:449–492][src-46], [local_python_executor.py:1743–1753,1775–1793][src-47]. |

The short path is effective because a model response, execution result, and subsequent observation are all inspectable locally. The base loop owns the expensive policy decisions, and each subclass primarily translates its action representation. Fixed schemas and ordinary Python values make small agents easy to compose. This simplicity depends on clear ownership of a running conversation and an accurate link between performed work and recorded outcomes. The tests around both terminal paths and the parallel action boundary expose where those assumptions need enforcement. [tests/test_agents.py:417–498,664–749,1974–2090,2511–2565][src-48], [agents.py:540–637,1373–1442][src-5].

## 4. Strengths

- **One driver for two materially different action styles.** The same planning interval, model memory projection, fallback, callbacks, and lifecycle serve imperative code and structured call batches. This keeps model/provider concerns in `models.py`, execution concerns in the executors or `Tool`, and the ReAct policy in a relatively small driver. Both scripted action loops passed their stock two-step tests. [agents.py:540–637,1276–1360,1638–1764][src-5], [tests/test_agents.py:417–498][src-48].
- **Good local test seams.** A `Model` subclass can return typed values without an SDK. `ApiModel` supports a provided client. `CodeAgent` accepts an executor instance and has an explicit cleanup path. As a result, the evaluation could use the real orchestration loop for lifecycle tests, the real adapter for outgoing request checks, and the real transfer code for a remote-protocol fixture. [models.py:468–610,1177–1207][src-49], [agents.py:1527–1539,1583–1596][src-17], [local_python_executor.py:1698–1713][src-50].
- **Useful execution feedback.** Recoverable parse and tool errors are expressed in the next turn's prompt, and printed code output is retained on normal code failures. The local executor tags the failing statement and supports a custom final answer. The healthy final-answer check path actually retries on a rejected candidate. [agents.py:582–605,613–618,1723–1764][src-41], [local_python_executor.py:1666–1689][src-51], [memory.py:126–148][src-8], [tests/test_agents.py:664–737,2141–2183,2346–2363][src-52].
- **Parallel dispatch is small and inspectable.** Single calls avoid the thread pool. Parallel calls copy the current context, publish completions promptly, and sort committed outcomes by ID. In the controlled successful batch, the events arrived `z`, `a` and memory recorded `a`, `z`, with both observations available to the next model. A separate context probe confirmed the caller label reached both workers and worker edits stayed in their contexts. [agents.py:1416–1442][src-53] (C1, C4).
- **Extensible tool authoring and useful typed records.** The decorator derives descriptors from annotations and docstrings. Class tools expose lazy setup and their own mutable application state. The memory dataclasses and typed callback registration allow applications to inspect or adjust a plan and keep a faithful trace for sequential work. The plan mutation probe showed that a callback edit was included in the next model prompt. [tools.py:106–142,228–256,1061–1168][src-54], [_function_type_hints_utils.py:204–231,291–323][src-55], [memory.py:25–64,154–206,280–316][src-56], [agents.py:416–434,554–567][src-57] (X2).
- **Coverage for core happy paths and backward compatibility.** Tests include local Python behavior and printing, memory projections, tool conversion, staged response streaming, managed delegation, and old serialized agent inputs. The archive install test passed with base dependencies only. The mocked OpenAI tests passed under two Python and SDK versions. The separate local folder round-trip restored a manager, child, and self-contained decorated tool. [tests/test_agents.py:1429–1450,1730–1813,2250–2283,2445–2565][src-58], [tests/test_import.py:6–30][src-59], [tests/test_memory.py:52–155][src-60] (X1).

## 5. Weaknesses and evidence status

**Classification.** A reproduced defect has an observed mismatch in a supported runtime path and a control or alternate path. A reproduced limitation has observed behavior whose scope is intentional, implicit, or ambiguous. A source-supported risk identifies a reachable mechanism whose real integration consequence remains unmeasured. A setup failure concerns the test environment. The identifiers in parentheses connect claims to measurements in section 8.

### 5.1 Run termination has holes at stream, action, and executor boundaries

**Reproduced defect — closing an in-flight stream can fail (L1).** With either agent, consuming a `ToolCall` and then calling `close()` raises `RuntimeError: generator ignored GeneratorExit`. The controller's `finally` runs the callbacks, appends an action with no output or error, and tries to yield it during generator closure. The first close leaves the generator suspended. A second close succeeds. An ordinary full drain and closure at an already finalized `ActionStep` succeed. This matters for consumers that render progress, abandon a task between events, or use generator cleanup on failure. It also explains the independent unraisable exception in a stock agent test that takes just one event. [agents.py:577–605][src-39], [tests/test_agents.py:1651–1676][src-61].

**Reproduced defect — plan-time cancellation allows the next action (L3).** The repository describes review and cancellation after planning, and its example callback calls `agent.interrupt()`. With that exact mechanism and an ordinary counter tool, both agents passed another request to the model and performed the action before reporting interruption. A terminal action could return success before another checkpoint. An interrupt set from the last permitted nonterminal action callback likewise allowed fallback generation (Z1). The switch is read at the top of an iteration and set by `interrupt()`. There is no check between the plan callback and action dispatch. The public switch is useful for stopping at a subsequent nonterminal turn boundary. Immediate preemption of a running model or tool would require a different contract. [agents.py:540–578,582–611,754–756][src-5], [docs/source/en/guided_tour.md:627–633][src-62], [docs/source/en/examples/plan_customization.md:10–38][src-63], [examples/plan_customization/plan_customization.py:62–96][src-64], [tests/test_agents.py:1429–1449][src-58].

**Reproduced defect — local timeout measures expiry but still blocks on work (E1).** `future.result(timeout=...)` times out. Raising inside a `with ThreadPoolExecutor(...)` triggers a waiting shutdown before the caller sees the error. Thus a cooperative test tool remained blocked after expiry, then mutated the execution namespace and completed when released. A real `CodeAgent.run()` recorded a timeout error for the action and returned the late assignment in the next action. The timeout docstring promises the caller can continue after expiry. The current design can wait as long as host work takes. AST operation limits govern a separate class of work. [local_python_executor.py:279–320,1472–1477,1651–1695,1775–1793][src-65], [agents.py:1723–1750][src-66], [tests/test_local_python_executor.py:2240–2349][src-67].

**Reproduced adapter-seam defect — local model worker failure can strand the consumer (T2).** `TransformersModel.generate_stream()` starts a background thread targeting `model.generate` and reads the inferencer's iterator from the caller thread. In the adapter test with the installed `TextIteratorStreamer` and an injected producer, the producer raised and exited; the consumer remained in the empty queue until the test supplied the stop sentinel. The runtime has neither a producer-to-consumer exception channel nor a deadline at this adapter boundary. The fixture establishes the failure mode of the stream adapter. Actual Torch model behavior and error frequencies remain unmeasured. [models.py:934–946,965–987,1109–1151][src-68].

### 5.2 Tool batches execute ahead of reliable admission and commit

**Reproduced defect — a sibling failure erases a successful tool outcome from model history (C1).** A two-call batch emitted output `7001`, then its other tool failed. The shared step retained the model's original request and an action-level error, while its `tool_calls` and `observations` fields remained unset. The next model request saw the generic error and lacked `7001`. The counter effect had already happened. `future.result()` raises before the post-batch assignments that put all successes and call records into memory. An all-success batch with identical control flow stored both values. Blind retry in a side-effectful workflow can therefore duplicate previously completed work. [agents.py:577–605,1373–1442][src-39], [memory.py:92–150][src-6].

**Reproduced defect — mixed terminal/nonterminal batches perform work before rejection (C2).** The controller reports that `final_answer` must be alone, but only after `process_tool_calls()` yields a final `ToolOutput`. All siblings have already been submitted. The independent counter effect occurred with two workers and with `max_tool_threads=1`. With one worker, the executor's context manager still drains queued work after rejection. The error test in the repository confirms the rejection message and does not instrument sibling execution. This is separate from the partial commit bug. A structurally invalid batch can be rejected before any dispatch. [agents.py:1335–1359,1416–1442][src-15], [tests/test_agents.py:1815–1888][src-69].

**Reproduced defect — parallel calls to one managed child mix histories (C3).** A valid parent batch issued two unique calls to the same registered child. With two workers and a controlled interleaving, the left reply summary included the right task, and the right reply summary included the left result. With a one-worker parent, each report remained local to its request. The child is a shared callable instance. Its normal reset, task setup, step numbering and memory appends modify that instance in place. The supported parent fan-out path exposes the ownership error even for caller code that makes only one top-level `run()` call. [agents.py:328–352,369–387,468–488,540–605,868–890,1425–1434,1453–1488][src-43].

**Additional limitations at that boundary.** Two direct same-instance `run(stream=True)` calls created before advancing either iterator projected the later task into both streams (X3). Direct overlapping calls have no advertised isolation contract. A stateless managed child model can still leak the wrapper's mutable history under C3. `Tool.setup()` also ran twice on one tool during concurrent first use (C4). The stock dispatcher propagates context, but initialization is an unchecked `is_initialized` read followed by `setup()`. Custom tool authors can serialize or pre-initialize their instances. Duplicate call IDs silently selected the last payload (C6). Duplicate IDs are malformed input, so the demonstrated weakness is lack of diagnostic rejection at the boundary. [agents.py:468–496,1373–1380,1425–1434][src-70], [tools.py:126–142,228–256][src-71].

### 5.3 Executor reuse and tool transfer differ across backends

**Reproduced defect at the remote abstraction — second run wraps the same final tool again (E4).** Using a real `CodeAgent` and the shared remote executor implementation, the first run returned `5`. The second normal run of the same instance returned its fallback after generated tool source raised `NameError` for `allow_pickle_setting`. `send_tools()` mutates the actual host tool's class to a wrapper. On the next send, it installs the previous wrapper's `forward` as the new `_forward`, using raw inspected source with the prior closure reference. A fresh default final tool restored the normal third run and the prior code namespace value `11`. The first and second emitted definitions and the Python MRO identify the change before any external transport. A plain local namespace, the repository WebSocket decoder with local frames, and the E2B executor decoding method with a stand-in SDK response produced the same result (Z3). This applies to preparation shared by built-in remote backends. Backend-specific provisioning and execution against a live service remain outside the result. [agents.py:490–492,1583–1618][src-72], [remote_executors.py:94–113,143–174,279–304,481–529][src-73], [tools.py:1335–1358][src-74], [utils.py:285–374,376–402][src-75].

**Reproduced defect — the code repair rewrites a valid custom final-answer keyword (E5).** A `final_answer` tool legitimately declared a `final_answer` parameter. `final_answer(final_answer="red")` became `final_answer(final_answer_variable="red")` and failed binding. The tool's ordinary keyword invocation and the generated positional equivalent returned `RED`. The repair intended for assignments works on text patterns that also occur in keyword arguments. Built-in `answer=` works because its keyword is different. [agents.py:1702–1713][src-76], [local_python_executor.py:332–357][src-20], [tests/test_agents.py:2346–2363][src-77], [tests/test_local_python_executor.py:2189–2223][src-78].

**Reproduced extension limitations (E2, E3).** Timed local code execution loses a caller `ContextVar` that is present when the timeout wrapper is disabled; the thread pool in the original local executor receives no context copy. A correct custom `PythonExecutor` makes preparation observable: constructing a stream already sent variables and tools, a transfer exception escaped with a task record installed, and an enclosing CodeAgent context manager invoked cleanup on both good and failing runs. This makes use of the same instance for staged streams and retry after setup failure harder to reason about. Process ownership, reset, cancellation, and context semantics are not expressed in the three-method executor abstraction. [agents.py:468–496,1587–1596][src-70], [local_python_executor.py:285–320,1691–1713][src-79], [tools.py:231–249][src-80].

**Source-supported remote lifecycle risk.** The shared WebSocket reader consumes frames until a matching idle frame and receives no per-action deadline from the common executor interface. The remote factories open individual connections and differ in how they release kernels and sandboxes. A lost event or a blocking client call can outlive the agent's step budget. The review exercised successful and error frames in memory, including unrelated idle frames that the reader correctly skipped, and the mocked Docker cleanup path. It did not emulate a real slow kernel or claim identical behavior across SDKs. [remote_executors.py:481–529,679–709,813–835,963–980,1049–1069][src-81], [local_python_executor.py:1705–1713][src-82].

### 5.4 Terminal records and usage signals disagree across interfaces

**Reproduced defect — exhaustion duplicates the last streamed action (L2).** With one unsuccessful action, both agents streamed action numbers `[1, 1]` using the same object twice. Their memory and callbacks held `[1, 2]`, with `AgentMaxStepsError` on step 2. `_handle_max_steps_reached()` builds and records the synthetic step, returns only its content, and `_run_stream()` yields the preceding action again. The final best-effort output was correct. Streaming observers cannot derive the same failure state as consumers of the full result from those action events. [agents.py:498–535,599–637][src-10], [tests/test_agents.py:501–520][src-83], [tests/test_monitoring.py:65–85][src-84].

**Reproduced defect and intended fallback boundary (L2, L7, X7, A7).** `ActionOutput(is_final_answer=True)` is visible before checks, and a rejected candidate can be followed by another candidate in the same run. A terminal `FinalAnswerStep` correctly reflected the accepted candidate in that probe. On budget exhaustion, the default returns a best-effort output outside those checks and `RunResult.state` reports `max_steps_error`. An existing test explicitly expects that fallback. A fallback generation failure was encoded as a list of text blocks while the stable state stayed `max_steps_error`. Separately, optimizing Python with `-O` removes the `assert check_function(...)` expression itself, so the normal acceptance path skipped the user's check and returned a value that normal Python rejected. That optimization discrepancy is a defect; the budget fallback is an existing policy and warrants a distinct outcome for consumers. [agents.py:582–637,810–853][src-41], [tests/test_agents.py:664–737][src-52].

**Reproduced defect — streaming usage is dropped or manufactured (L6, A6, T1).** A planning model emitted a text chunk followed by a usage-only delta with `content=None`. The planning branch only inspected usage within the content guard, leaving an eight-token plan at zero. The same fixture's non-stream path reported all 17 run tokens, compared with 9 in stream mode. Action aggregation included a content-free usage delta correctly. Providers that emit usage with an empty string instead of `None` take a different branch. An action supplying no usage at all produced `None` in non-stream `RunResult` and zero in the stream aggregate. A separate Transformers seam experiment produced three token IDs and the same decoded text in both modes, with four reported output tokens in streaming because the final flush is also counted. The built-in monitor is intentionally action-only. [agents.py:505–521,658–677,714–745][src-85], [models.py:214–279,1127–1151,1751–1764][src-86], [monitoring.py:81–117][src-28].

**Reproduced observability limitation — terminal errors and callbacks use different commit points (L8, X2, X4).** A generation failure during an action reached the caller as `AgentGenerationError`, but the finalized action's `error` field stayed empty. A planning generation failure propagated the original `ValueError` and created no planning record. A raising user action callback prevented the action append and monitor callback. On the successful path, plan delivery precedes callbacks and commit, whereas action record delivery follows them. Passing a child's `RunResult` through the managed callable extracts its output and discards the typed child status. Optional summary text exposed exhaustion in the fixture. These behaviors limit the use of a single event stream as an authoritative run trace. [agents.py:416–434,540–637,639–747,868–890,1320–1325,1697–1700][src-57], [memory.py:280–316][src-35], [tests/test_agents.py:739–749][src-87].

### 5.5 Model and tool interfaces allow configurations that diverge underneath

- **InferenceClientModel structured-output mismatch (reproduced, A1).** Non-stream generation recognizes the allowlisted provider but comments out `response_format` in the dispatched request. Its streaming method forwards the field. With the same scripted client and structured CodeAgent, allowed-provider sync exhausted after parsing plain text, while streaming succeeded. OpenAIModel and LiteLLMModel forwarded the schema in both paths. This finding is about the outgoing argument and agent parser, independent of whether a live service follows the prompt without a schema. [models.py:38–64,1293–1313,1335–1357,1578–1640,1732–1756,1786–1805][src-88], [agents.py:1655–1713][src-89].
- **Bedrock transport schema mismatch (reproduced against installed SDK metadata, A4).** A Bedrock client injected with botocore's shipped Converse parameter validator accepted the CodeAgent text request and rejected the ToolCallingAgent request on `tools` and `tool_choice`. The shared adapter placed OpenAI-style keys in the payload and the Bedrock override only removed `toolConfig`. This result concerns upstream request construction. The native Bedrock response stream and live model behavior remain unmeasured. [models.py:518–567,2013–2081,2093–2133][src-90], [tests/test_models.py:812–846][src-91].
- **Stop and retry behavior differs by phase (reproduced, A2–A3).** For a model ID that the runtimes mark as lacking server-side `stop`, all three tested API adapters clipped the same non-stream reply but delivered a complete stop marker and following text in stream mode. The marker crossed a chunk boundary in the fixture. Retry around opening a response recovered a first rate-limit exception, while an exception raised by the iterator before its first chunk or after an emitted chunk escaped on one attempt. The safe boundary for reattempting work is different before and after publication. The current wrapper makes that boundary the Python client call, even if iteration has yet to produce anything. [models.py:79–91,434–454,1177–1218,1321–1385,1600–1668,1749–1818][src-92], [utils.py:528–606][src-93].
- **Legitimate tool arguments can fail after normalization (reproduced, L9, A5, X5).** The batch uses `tool_call.arguments or {}`. Scalar `0` passed direct invocation and was dropped by both native-call and textual-JSON run paths. The same tool accepted `3` and `{"number": 0}`. Another valid path generated an image, looked it up from `image.png`, and passed the `AgentImage` to an `image` input. Validation treated it as `object` before the existing unwrap logic could run. Calling the tool directly with sanitization and composing the tools in CodeAgent both returned the same pixel. The outer type mapper similarly classified the raw PIL image as `object` in this environment. Requiredness and nullability are also conflated by the shared runtime schema, matching the two intentionally skipped nullable tests. [agents.py:1383–1401,1444–1488][src-94], [tools.py:231–249,1361–1412][src-80], [agent_types.py:254–281][src-11], [_function_type_hints_utils.py:291–319,387–431][src-95], [tests/test_tools.py:973–1014][src-96].
- **The accepted message type can break the next turn (reproduced, L10).** A `ToolCallingAgent` model returned a `ChatMessage` with two valid text blocks and one valid native tool call. The tool executed, then the next input assembly applied `.strip()` to the list in `ActionStep.to_messages()`. With a direct shared normalizer call, text flattening kept only the first block and non-flattening mode kept both. The schema permits lists and the tool path recorded this list without normalization. The fixture used text blocks only, so the error was independent of media dependencies. [models.py:123–157,332–413][src-37], [agents.py:1284–1291,1320–1336][src-97], [memory.py:57–58,92–98][src-98].

The opt-in `ApiModel` pacing limiter also has an ordinary concurrency limitation (S2). Two concurrent callers paced against the same last-call timestamp and were admitted together in a deterministic fake-clock schedule. This is relevant to concurrent children sharing one client model. SDK-side throttling may add its own serialization. [models.py:1177–1207][src-99], [utils.py:497–525][src-100].

### 5.6 Stateful ergonomics impose limits on long sessions and extension parity

- **History growth and repeated media (reproduced tradeoff, C7, X6).** Every normal action stores its projected input list and rebuilds the conversation for the next model call. For a simple fixed two-message contribution per action, 10, 20, 40 and 80 steps stored 110, 420, 1,640 and 6,480 model-input message entries. The latest prompt sizes were 20, 40, 80 and 160. The default 20-step budget caps one normal run. Long histories with `reset=False` or higher budgets keep accumulating. One fixed task image occurred once, twice and three times in the first three action prompts because each `ActionStep` takes the original image list as its observation. This is a structural count, independent of latency, tokenization, and model quality. [agents.py:468–492,570–575,758–770,1284–1289,1646–1650][src-70], [memory.py:112–124,187–196,228–246][src-101], [models.py:348–384][src-102].
- **Both streamed action loops repeatedly aggregate the whole prefix (reproduced tradeoff, S1).** For 8, 32 and 128 chunks, the two loops called the aggregator 9, 33 and 129 times. They passed a total of 44, 560 and 8,384 chunk entries, including the final pass. The computation grows quadratically per completion even with `LogLevel.OFF`. The matching sync completion returned the same answer with zero calls to the aggregator. These are operation counts for the orchestration seam. Rich and provider elapsed time are outside this measurement. [agents.py:1293–1307,1659–1676][src-103], [models.py:220–279][src-104].
- **State retention is distinct from conversation reset (reproduced tradeoff, L4, C5).** `reset=True` removed all old message records and reset metrics while leaving the injected `seed` and a CodeAgent local variable accessible. A caller requiring a fresh workspace can create a new agent/executor. ToolCallingAgent uses a single fixed key per media type, so two deliberately different one-pixel images both appeared as `image.png`, and only the last was addressable even with one worker. For parallel calls the winner can depend on completion order. [agents.py:468–492,1389–1401][src-70], [local_python_executor.py:1743–1753,1788–1793][src-47], [memory.py:228–234][src-105].
- **Action budget and planner budget can diverge (reproduced, L5).** `run(max_steps=2)` governed execution correctly, but an updated plan reported 18 actions remaining when the constructor default was 20. The template receives `self.max_steps - step`. A zero run override fell through to the default and a negative override hit an unbound local before any model call. Treat a positive limit as the normal API. Invalid edge values would benefit from deliberate validation rather than accidental branch behavior. [agents.py:449–468,540–566,606–611,695–713][src-46].
- **Configuration export is a projection (reproduced, X1).** A JSON round-trip preserved name, prompt templates, tool behavior, and max steps. It reset custom CodeAgent delimiters, structured-output mode, full-result default, instructions, and the InferenceClientModel provider. CodeAgent's importer already reads a `code_block_tags` field that its exporter omits. `to_dict()` explicitly drops callback and check callables. Omitted plain data and intentionally nonportable callables merit separate semantics. The config path does not implement a session checkpoint. [agents.py:970–1062,1766–1803][src-106], [models.py:612–646,1539–1576][src-107].
- **The manual step contract trails the stream implementation (reproduced, X2).** `step(memory_step)` returns the final yielded `ActionOutput`, including `(2, False)` for a normal action. The method docstring describes `None` or an answer, and the memory example tests `while final_answer is None`. A correctly initialized step object and executor were required in the fixture. The public `run()` path handles this event correctly. [agents.py:772–787,1752–1764][src-108], [docs/source/en/tutorials/memory.md:97–133][src-109], [memory.py:50–54][src-31].

## 6. Core-code quality

| Dimension | Assessment |
| --- | --- |
| Decomposition | The common loop plus model, tool, memory and executor modules gives clear entry points for review. `MultiStepAgent` also owns construction, delegation, runtime control and the configuration-export surface. Generation and Rich rendering are intertwined in the two action loops and two planning branches. Those branches independently assemble messages and usage, which shows up as parity issues. [agents.py:268–352,540–747,892–1062,1276–1360,1638–1764][src-110]. |
| State and lifetime | `MemoryStep` objects accurately convey useful types and can be inspected before the next call. The owners of task, step number, monitor state, executor state and callback side effects are all the long-lived agent. Preparation outside the generator and finalization inside a yielding `finally` complicate resource ownership. State restoration begins with an explicit configuration reload and fresh process or executor decisions by the application. [agents.py:328–352,468–496,540–624,1011–1062][src-43], [memory.py:214–277][src-111]. |
| Concurrency | Bounded tool threads, completion-order reporting and per-worker context copies are sensible defaults. One agent step remains a synchronous barrier. Concurrent tools use shared instances and state. Batch admission, per-call failure accounting, timeout and same-child run ownership need stronger contracts before this becomes a reliable orchestrator for concurrent effects. [agents.py:1373–1442,1453–1502][src-44], [local_python_executor.py:285–320][src-79]. |
| Errors and recovery | A small exception taxonomy distinguishes parsing, tool arguments, tool execution, model generation and budget exhaustion. Common errors become useful prompts. Planning, preparation and user callbacks follow different propagation paths, and ordinary model failures can leave a finalized action without an error field. Cleanup and failure metadata should be explicit at each lifecycle boundary. [utils.py:92–137][src-9], [agents.py:490–496,540–637,639–747,846–853,1320–1325,1475–1502][src-72]. |
| Types and schemas | `ChatMessage`, `ToolCall`, `ActionOutput`, `ToolOutput`, `CodeOutput`, and typed memory records communicate the intended data model. Return types rely heavily on `Any`, and the defined `StreamEvent` union is unused in `_run_stream()`'s narrower annotation. The tool descriptor doubles as documentation, prompt interface, provider schema and hand-written runtime validation. These uses disagree on media, call shorthand and nullability. [agents.py:110–122,256–265,436–445,540–542][src-112], [models.py:123–157,288–329][src-37], [tools.py:144–226,1361–1412][src-113]. |
| Observability | In-process callbacks, a trace ledger and simple action metrics make small runs transparent. Event publication, callback commit and memory projection are separate operations. Accounting windows differ across `Monitor`, history totals and run timing. Timing for the non-stream result begins after preparation, and a suspended stream includes elapsed consumer time in per-step timing. A controlled clock confirmed a five-unit action and a 50-unit consumer pause recorded as 55 units, while a separate ten-unit executor preparation was outside the sync result timing. Rich live rendering is coupled to generating deltas. [agents.py:416–434,468–535,554–624,1299–1307,1665–1674][src-57], [memory.py:236–277][src-114], [monitoring.py:57–117][src-115]. |
| Extension and maintainability | `Model.generate`, declarative tool inputs, and the executor protocol are small, usable seams. Source extraction supports transport and simple config portability. Repeated introspection, generated class mutation, and parallel schema implementations put a large correctness obligation on those seams. Prefer shared, explicit outcome and capability records over adding one special case per provider. [agents.py:970–1062,1527–1618][src-106], [models.py:468–610][src-49], [tools.py:292–388,1061–1168,1335–1358][src-116], [remote_executors.py:94–141,143–304][src-73]. |
| Tests | Offline unit coverage is broad, and many tests use concrete memory assertions or SDK-shaped fixtures. Several tests cover a status or output without checking causality and timing. Examples include the timeout tests checking the exception, mixed final-call testing the error message, and the image-input test accepting a scripted caption despite a failed tool call. Lifecycle and fault-injection tests should assert observable events, effects and memory together. [tests/test_local_python_executor.py:2230–2349][src-117], [tests/test_agents.py:176–208,447–464,1815–1888][src-118] (E1, C2, Z2). |

## 7. Executed tests and experiments

### 7.1 Stock repository tests

| Run | Selected outcome | Setup and interpretation |
| --- | --- | --- |
| Initial broad CPython 3.12.16 | **737 passed, 4 failed, 43 skipped, 173 deselected** in 29.63 s | Four optional-package failures. Three tests in `test_monitoring.py` entered the Gradio adapter and one persistence fixture constructed a DuckDuckGo tool requiring `ddgs`. See section 8. |
| Refined broad CPython 3.12.16 | **737 passed, 43 skipped, 177 deselected** in 22.76 s | Same 14 core test modules, with those four nodes deselected. The suite retained a real unraisable generator-close warning. A repeat with dotenv loading explicitly disabled gave the same counts in 22.11 s. Executing the report’s own namespace wrapper and filter reproduced them in 22.61 s. |
| Refined broad CPython 3.14.8 | **737 passed, 43 skipped, 177 deselected** in 29.36 s | Independent interpreter and virtual environment. Same selection and warning. |
| Mocked OpenAI-family and stream tests, 3.12.16 | **11 passed, 1 skipped, 217 deselected** in 0.50 s | Real cached OpenAI SDK 3.55.1 and jiter 0.19.0. Constructor and provider-response fixtures, with SDK or client boundary mocked by the upstream tests. |
| Same SDK slice, 3.14.8 | **11 passed, 1 skipped, 217 deselected** in 1.79 s | Real cached OpenAI SDK 3.49.0 and matching jiter ABI. The skipped node is the `RUN_ALL` model stream integration. |
| Base installation and import, pytest driver on 3.12.16 | **1 passed** with nested Python 3.14.8 in 1.52 s, then **1 passed** with nested Python 3.12.16 in 1.21 s | Original `test_import.py` from a `git archive HEAD` copy. UV first chose the system Python version. The second run pinned `UV_PYTHON` to the test driver’s base interpreter. Both installed the base package with cached wheels in a separate venv and inherited no source `PYTHONPATH`. |
| Close warning promoted to error, 3.12.16 | **1 failed** in 0.19 s | Re-ran `TestToolCallingAgent::test_toolcalling_agent_passes_both_tools_and_managed_agents` with `-W error::pytest.PytestUnraisableExceptionWarning`. This confirmed the independent warning and was followed by explicit `.close()` probes (L1). |

The broad suite covered agents, models, tools, memory, monitoring, function type hints, tool validation, remote-executor unit contracts, the ordinary local Python executor tests, final answers, serialization, value types, utility functions, and the local default interpreter tool. The venvs used pytest 9.2.0, `huggingface-hub` 2.4.0, Pillow 13.0.0, Rich 15.0.0 and Jinja2 3.1.6. The 3.12 run used NumPy 2.5.4, pandas 3.1.1, MCP 1.30.0, Docker 7.2.0, botocore 1.43.123 and IPython 9.18.1. The selected tests include app-facing fixture coverage without invoking a model service. Several upstream constructor tests use inert string placeholders. The network namespace and fixture mocks prevented provider use. [pyproject.toml:13–22,24–113,115–117][src-119], [tests/conftest.py:9–23][src-120], [tests/utils/markers.py:17–25][src-121], [.github/workflows/tests.yml:19–47][src-122].

The 43 stock skips include `RUN_ALL` integrations, Torch-dependent media, macOS MLX, two nullable schema TODOs and two broken dynamic-tool test fixtures identified by their own skip annotations. Deselection was based on test source. It includes model or weight downloads, scoped-out UI or security tests, actual remote provisioning, required optional dependencies that could not be installed offline, and integration-only search and MCP paths. The stock `make test` target selects the full suite and the test extra includes `all`, which brings in hosted and heavyweight integrations. The named runs represent an offline core subset. `test_telemetry.py` uses an optional instrumentation package and a hosted model under `RUN_ALL`. I tested instance metrics, callbacks and context propagation locally. [pyproject.toml:92–117][src-123], [tests/test_agents.py:633–663,1916–1943,2209–2235][src-124], [tests/test_models.py:279–398,660–683][src-125], [tests/test_tools.py:973–1014][src-96], [tests/test_telemetry.py:25–38,66–87][src-126].

### 7.2 Focused local experiments

The focused probes used the pinned package through `PYTHONPATH` from plain Python. The repository pytest fixtures and the autouse logger patch applied only to the stock test runs. They used precomputed model messages, memory-only tools, PIL pixels, stdlib synchronization primitives, and tiny stand-ins behind SDK, kernel or model-weight boundaries. The lifecycle, concurrency, executor, API and extension fixtures completed on CPython 3.12.16 and 3.14.8. The Transformers interface fixture used the cached vendor `TextIteratorStreamer` in CPython 3.12.16 with a deterministic producer in place of model weights. A separate `-O` run on each interpreter deliberately tested validation under optimized Python. See section 8 for exact behavior and controls, and section 10 for commands and representative runnable reproductions.

## 8. Measurement audit

### 8.1 Setup, selection and independence

- The first shell's interpreter lacked `huggingface_hub`, `PIL`, and `dotenv`. Resolving base requirements alone from the uv cache succeeded. The initial optional set failed resolution on `pytest-datadir`, then on jiter's CPython 3.12 wheel. To preserve coverage, I supplied only the `shared_datadir` fixture using a fresh copy of the tracked `tests/data` directory into `tmp_path`. Pytest loaded no ambient plugins. The bundled input PNG remained unchanged. I recovered OpenAI coverage using the locally cached SDK and matching jiter binary for each interpreter. Mocked OpenAI tests then ran in both environments. This rules out the initial optional-import failure as an SDK behavior finding.
- The initial four broad red tests reached the expected optional imports. The Gradio stack stopped before the runtime stream was consumed. The `ddgs` stack stopped in a search-tool constructor before agent persistence. Filtered reruns retained the same number of passing tests, and the independent CodeAgent manager save/load fixture passed with a function tool that needs only base packages. Base packaging also passed in its isolated install. These four results are setup or selection failures. [tests/test_monitoring.py:100–174][src-127], [tests/test_agents.py:2382–2444][src-128], [default_tools.py:129–138][src-129], [tests/test_import.py:6–30][src-59].
- Offline resolution could not obtain `mcpadapt`, E2B or the remaining remote SDK extras needed for their live fixtures, and a compatible cached Pillow wheel was unavailable for the attempted Python 3.10 environment. Python 3.12 and 3.14 had the needed base wheels. The compatible `mcp<2` package alone enables tool module collection and does not provide the missing adapter. Real Torch execution was blocked by a missing compatible cached wheel for the 3.12 environment. The Transformers seam remained exercisable with the cached Python tokenizer/streamer package and fixture token arrays. I used the source version of every adapter under review. [pyproject.toml:13–22,28–74,79–93][src-119], [mcp_client.py:103–126][src-130], [models.py:934–946,1109–1151][src-68].
- I verified the absence of `.env` files along the package’s source ancestry and explicitly disabled dotenv loading for the final reruns. The namespace check used `socket.if_nameindex()` inside the process and found only `lo`. Listing `/sys/class/net` alone would show names from the containing mount and is a poor isolation check. Head and tree were verified via Git, and the initially empty porcelain state was checked again during work, including ignored paths. Disposable tests could write only outside the mounted read-only checkout. Fixture gates had finite safety bounds with release in `finally`. The evaluator did source or report work while tests ran. NumPy and pandas deprecations came from the optional scientific-package versions and a stock DataFrame test. Legacy serializer tests also emitted their expected future warnings. The generator-close warning is a separate runtime event attributed by L1. [local_python_executor.py:1321][src-131], [tests/test_local_python_executor.py:1338–1387][src-132], [tests/test_serialization.py:798–816][src-133].

### 8.2 Run, cancellation and result controls

| Probe | Observation and controls | Attribution and limit |
| --- | --- | --- |
| **L1 — generator close** | Stock test line 1669 emits the unraisable warning on collection of its suspended iterator. With a retained generator, `next()` gave `ToolCall`, the counter log stayed empty, and `.close()` raised with generator state `GEN_SUSPENDED` and a partial `ActionStep` appended. A second `.close()` closed it. Closing immediately after a finalized action and draining a fresh generator ended normally for both agents. | The error is caused by yielding in the shared `finally`. The plain Python probe rules out pytest disposal, provider I/O, tool exceptions, or mocking the generator as causes. [agents.py:577–605][src-39]. |
| **L2 — exhaustion identity and policy** | For each agent, one nonfinal action, one fallback response, then stream termination. Compared actual object identities of two emitted actions with two separate callback and memory records. Emitted `[1, 1]`, committed `[1, 2]`, fallback `best effort`. Full-result run separately returned `max_steps_error` and `AgentMaxStepsError` on the synthetic action. The check saw only the normal rejected value `[2]`. | Counts distinguish repeated emission from duplicated execution. Both are visibly separate code paths. [agents.py:523–535,599–637][src-134], [tests/test_agents.py:717–737][src-135]. |
| **L3, Z1 — interrupt checkpoints** | Run a plan callback that calls `interrupt()` with ready scripted model replies and a simple side-effect counter. The action still recorded `[9]`; a second iteration then raised `AgentError('Agent interrupted.')`. A final action returned `9` instead. In the one-action bound, interrupt from the final permitted action callback still allowed one new fallback generation. A flag set before the first `next()` stopped before any model call. A raising planning callback stopped before dispatch. | No slow worker or scheduler race is needed. These are gaps between checkpoints. The repository's existing interrupt test calls the switch at a nonterminal action boundary, where the next top-of-loop check works. [agents.py:540–611,754–756][src-5], [tests/test_agents.py:1429–1450][src-58]. |
| **L4–L5 — conversation reset and planning budget** | First run `x=7` with `seed=2` and consumed a final value. On the second run with `reset=True`, the prompt had only the fresh task but `final_answer(x)` still returned `7`, and `seed=2` remained. With constructor `20`, override `2`, and `planning_interval=1`, read a literal `budget={{ remaining_steps }}` in the second planning request, yielding `18`. Zero made the model call under the configured default. Negative errored before generation. | Measured both histories and data state to avoid confusing two lifetimes. The action bound works with positive overrides, and the planner bug is the input to its template. [agents.py:449–492,540–575,695–713][src-46], [local_python_executor.py:1775–1793][src-136]. |
| **L6, A6, T1 — token accounting** | Same content/call decisions and known synthetic usage for stream and sync. Usage-only plan delta with `content=None` yielded `0` instead of `8`. Both action paths counted `9`, both monitors counted `9`, and full-result counts were `9` versus `17`. Missing action usage gave `None` sync and `0` stream. `reset=False` yielded a cumulative count of `10` in a second call after two known five-token actions. Real `TextIteratorStreamer` with known IDs produced `['', 'one ', 'two ', 'three']`; counting emissions gave four for three IDs. | These measure bookkeeping, not tokenizer quality or billing. Some network wrappers set `content=''` for usage, so the planning loss requires `None` specifically. Session aggregation and the action-only monitor follow their registered scope. [agents.py:505–521,658–677,714–745][src-85], [models.py:220–279,1127–1151][src-104], [monitoring.py:100–117][src-137]. |
| **L7, X7, A7 — final checks and bad fallback** | Check rejected candidate `1` then accepted `2`; streams emitted both candidate outputs and one final `2`. Explicit `python -O` case used a non-asserting harness: with `__debug__` true, calls were `[1,9]` and result was `9`; optimized gave result `1` and zero check calls. Injecting an ordinary error in fallback generation returned a list of text blocks under the budget error state. | Confirms final acceptance is distinct from `ActionOutput`; Python optimization removes the runtime's `assert`, not an assertion in the measuring harness. Exhaustion being best effort is intentional under the stock test. [agents.py:582–637,846–853][src-41]. |
| **L8, X2, X4 — commit phase and failure records** | Stub action and planning failures with the same exception family. Action wrapped it and committed a timed record with `error=None`; planning raised original and left just the task. A raising user action callback resulted in one task record and no action metrics. A non-raising planning callback mutated the yielded `PlanningStep`; the mutation reached the next model input. Managed-child fallback status was absent from a plain report and appeared as summary text when requested. | Each check inspected both caller-visible and ledger states. The behavior follows `_finalize_step`, callback order and the managed callable's extraction of `RunResult.output`. [agents.py:416–434,540–637,868–890][src-57]. |

### 8.3 Fan-out, execution and data boundaries

| Probe | Observation and controls | Attribution and limit |
| --- | --- | --- |
| **C1, C2 — partial and invalid batches** | Start two independent, valid IDs. The second tool waits until the test consumes the first result, then succeeds or raises. Successful run recorded `7002\n7001` in sorted-ID memory. Failed run recorded the error while the successful `7001` was present only in the stream and the tool's own effect log. Separately send a mixed terminal/bump batch and then a clean final answer. Bump occurred with worker caps one and two. A final-only invocation caused zero bumps. | This shows effects before complete admission or commit. It avoids mistaking `as_completed()` event order for memory order. The comparison is full `run()` plus an actual thread-pool path, not a mock of `process_tool_calls`. [agents.py:1335–1359,1373–1442][src-15]. |
| **C3, C4, X3 — ownership** | Use `threading.Event` gates so child A captures its own task, child B resets shared memory, A finishes and formats its report, then B finishes. Compare one worker with two. Each direct answer still matched its own request, while summaries mixed with two workers. Launching two lazy streams before either iteration recreated ownership failure with no parallel threads. A first-use lazy tool synchronized two workers inside `setup()` and recorded two setups, versus one serially. Worker ContextVar copies gave matching parent labels and isolated changes. | No flaky ordering or delay as synchronization. The primary child path is an ordinary legal batch from one top-level run. Same-instance overlap outside a batch is a limitation of the design assumption. [agents.py:468–496,540–605,868–890,1425–1434][src-70], [tools.py:231–256][src-80]. |
| **C5–C7, X6 — media, ID and transcript cardinality** | Two different pixels `10` and `20` produced two live outputs but one key and final pixel `20` even under serial worker scheduling. Duplicate ID emitted two proposed calls but invoked only the second. Separate unique IDs invoked both. History count used only the actual `ActionStep.model_input_messages` lists and a stateless-length fixture for 10 to 80 actions. With one input image and three turns, the original image was present once, twice and three times in the prompts. | A fixed-slot policy loses independent media handles. Duplicate IDs are malformed, so the test establishes the missing diagnosis. History measurements count entries, independent of heap allocation, tokenization or wall speed. [agents.py:570–575,758–770,1373–1442][src-138], [memory.py:112–124,187–196][src-101]. |
| **E1, E2 — timeout and context** | Released a tool only after its configured 50 ms wait had expired and the caller still could not complete. `Future.result` was wrapped only to signal expiry and rethrow its real exception. The decorator, real `LocalPythonExecutor` and CodeAgent all blocked until the gate opened, with 3.12 elapsed calls of roughly 200, 201 and 227 ms. Re-ran the local executor without that wrapper at 20 ms and observed it still blocked after 120 ms. Fast work returned normally. CodeAgent retained the late variable `88`. Timed versus unwrapped execution toggled caller context visibility. | `ThreadPoolExecutor.__exit__` waits. The fixture therefore distinguishes return-time enforcement from recognizing the timeout. Default local worker context did not copy on either tested interpreter. The worker cannot be killed by ordinary Python thread cancellation. [local_python_executor.py:285–320,1651–1695][src-79], [agents.py:1723–1750][src-66]. |
| **E3–E5, Z3 — executor semantics** | Checked real `CodeAgent.run` against a minimal public executor and verified setup before iteration, cleanup and original setup error. For transfer reuse, executed repository-generated definitions in a normal Python namespace, inspected first/second class MRO and source, and used the same shared real transfer path with synthetic Jupyter frames and an E2B SDK-response stand-in. All three returned `5`, fallback, then `11` with a fresh final tool. Separately compare a valid custom final keyword with direct `Tool` and positional CodeAgent controls. | The same error originates in generated source across transports. The test stands in for kernel I/O and E2B provisioning only. The keyword migration is the runtime's regex, confirmed in `ActionStep.code_action` before the executor invoked the tool. [agents.py:490–496,1587–1618,1702–1726][src-72], [remote_executors.py:94–113,143–304,374–402,481–529][src-73]. |
| **T2 — Transformers consumer failure** | Replaced only load/preparation and the heavy producer with a fixture. Kept the concrete `TextIteratorStreamer` from Transformers 5.23.0 and the adapter's real streaming logic. Producer exception was captured by `threading.excepthook`; the empty queue consumer stayed alive after producer exit. The fixture supplied a stop sentinel during cleanup, allowing a bounded test. Standard producer completion with the same streamer worked. | Confirms the adapter seam with actual queue behavior. Loaded model or hardware failure rates and production model runtime are unresolved. [models.py:965–987,1109–1151][src-139]. |

### 8.4 Model wire behavior and extension controls

| Probe | Observation and controls | Attribution and limit |
| --- | --- | --- |
| **A1 — structured output** | Used a local client whose response format depended solely on the actual outgoing `response_format` keyword. InferenceClientModel sync dropped it for `cerebras` despite accepting the provider, and streaming retained it. OpenAI and LiteLLM controls passed both ways. An unsupported provider was rejected by the sync guard before client invocation. | Corrected the initial hypothesis that both HF paths omitted the schema. The observed failure is sync-specific and detectable directly on the request payload. Provider compatibility and model instruction-following are outside the measurement. [models.py:1586–1601,1623–1640][src-140]. |
| **A2–A4 — stream retries, stop, Bedrock** | Match the same 429 exception class and message at client invocation, first iteration and after one chunk, with zero test delay. Opening retried to two attempts; both iterator errors returned on one. For `o4-mini`, the marker split across chunks survived streaming and sync cut it; a supported model ID forwarded `stop`. Validated the actual Bedrock kwargs against botocore 1.43.123's local `Converse` input metadata, with successful text CodeAgent control. | These results concern wrappers and the installed SDK's local protocol rules. An actual SDK may hide or retry a particular transport failure internally. The fixture uses valid chunks and a real schema validator instead of invented provider rejection. [models.py:434–454,1177–1218,1321–1385,1600–1668,1732–1818,2041–2112][src-141]. |
| **L9, A5, Z2, X5 — input normalization** | Exact scalar `0`, its named form, and nonzero scalar used the same integer `Tool`. Direct and the latter two succeeded, and both full-run zero encodings failed. Image producer returned a true PIL image and a working `AgentImage` state value; direct `.to_raw()` and downstream `Tool` sanitization worked. Raw and wrapped image failed explicit `image` validation. The upstream visual fixture still reported a caption with a failed first action because its model always supplies the same next caption. A separate invocation of the stock `test_toolcalling_agent_handles_image_inputs` with its tracked PNG and a passive wrapper around `run()` confirmed the same error and empty state. Reproduced known required-nullable, defaulted/non-null conflation with the original decorator and explicit Python signature controls. | Rules out mock image identity, missing Pillow, missing schema fields, and unsupported plural scalar args. A stock passing caption test establishes output shape, not typed tool chaining. The verified implicit final tool/child name collision is an admission edge where the supplied names were individually valid. [tools.py:1361–1412][src-142], [agents.py:369–414,1383–1399,1444–1488][src-27], [_function_type_hints_utils.py:291–323,415–431][src-95], [tests/test_agents.py:145–208,427–464][src-143]. |
| **L10, X1, X2 — type and extension semantics** | Valid named call with a standard text-block `ChatMessage`, successful tool effect and raw `AttributeError` on the next input projection. Plain string or `None` content controls advanced normally. Flattening control used a single unmerged message and `flatten_messages_as_text=False` preserved both blocks. Real JSON config and folder round-trips restored stable fields and a self-contained child tool. Explicit overrides restored lost agent fields. Passed required `Timing` and preloaded tools for manual `step()`. Repeated with a seeded `TaskStep` and manual action appends. The return envelopes were `(3, False)` and `(5, True)` with visible tool effects and final output. | The differences originate in public shape handling and exported fields. Successful models, callbacks and tools can use a documented subset. Configuration cannot currently capture a running session automatically. [memory.py:51–98][src-40], [models.py:123–157,332–413,612–646][src-37], [agents.py:772–787,970–1062,1766–1803][src-108]. |
| **S1–S2 — stream aggregation and request pacing** | Recorded each length passed into the real `agglomerate_stream_deltas()` while permitting the real calls and validations to proceed. Both agents saw prefix lengths `1…N` plus a final `N`, versus zero aggregations for the same sync text. For pacing, preset the last-call time to 100, admitted two callers at fake time 101, held both at the same computed 59-second interval, then advanced both to 160. | The prefix result depends on production traversal counts, independent of display, lexical content or clocks. The pacing test controls one reachable scheduling interleaving using a fake clock and makes zero network calls. It is evidence of an unsynchronized rate gate, separate from provider limits. [agents.py:1299–1307,1665–1674][src-144], [utils.py:512–525][src-145]. |

These results support claims about this pin and these contracts. Remaining uncertainty covers live provider capabilities, performance under real model context limits, remote startup and teardown under real faults, and the resource policy of application-defined tools. The offline evidence can isolate where code emits or consumes a value and which ordinary failure triggers a state transition. It cannot estimate how often a provider or workload reaches that state.

## 9. Prioritized post-mortem

The design spends complexity on making the model, tool and executor easy to swap. A regular Python object is the natural place for state, and a generator is a compact way to expose model and tool progress. This makes a small serialized loop practical. Streaming turns every `yield` into a suspension boundary. Fan-out turns the same mutable tool and agent references into cross-thread sharing. Remote execution turns local objects into serialized code and data on every run. Features that were individually small now intersect at preparation, commit and cleanup, with failure invariants spread across several modules.

| Priority | Change | Acceptance evidence |
| --- | --- | --- |
| **P0 — run termination and cancellation** | Give one run explicit ownership of task, counter, cancellation token, and outcome. Define preparation, action commit, exhaustion and terminal phases. Perform cleanup without yielding. Check cancellation after plan callbacks and before dispatch and fallback. Decide what a caller can expect once running work has side effects. Preserve typed failure and a completed or cancelled history entry. | Close at each of pending model delta, proposed call, completed tool, plan, and action commit. Require closure without errors and verify expected effects and history. Interrupt from a plan and the last permitted action. Require zero subsequent dispatches. Verify force-close and `interrupt()` behavior separately. |
| **P0 — preflight and account for entire batches** | Validate unique IDs and structural constraints before submission, including terminal calls. Record a status and result or error per admitted call, preserving completed siblings and choosing a defined policy for pending siblings. Use a run-local namespace for a managed child or serialize invocations to each stateful instance. Define ordering and stable references for artifacts. | Gate completion of a succeeding and failing tool in both orders and compare stream, callback and next-prompt records. Verify the invalid mixed batch produces zero side effects. Dispatch two distinct tasks to the same managed registration with an explicit isolation control. |
| **P0 — executor deadline and idempotent preparation** | Separate elapsed-time enforcement from error classification. If an executor supports a deadline, surface it through its protocol and define how state is retired or protected when a worker outlives the deadline. A process or cooperation boundary can give a stronger guarantee than a shared mutable thread. Generate standalone remote tools without mutating caller objects or relying on closure rewrites. | Use a gated ordinary tool and measure caller completion and late mutation independently. Transfer the same default and custom final tools over repeated runs in each transport adapter fixture. Check that their classes and direct host behavior remain stable. |
| **P1 — publish one terminal record and coherent metrics** | Have sync and stream views consume the same committed outcome and usage model. Distinguish candidates, budget exhaustion, cancellation, generation failure and accepted finals. Use explicit boolean checking rather than an assertion for application callbacks. Account for optional per-step usage without substituting false zeros. Protect committed memory from failing observational hooks. | Assert exactly one terminal result, with the same synthetic exhaustion record and status in both views. Exercise runtime checks under `-O`, plans with a usage-only chunk, continuation runs, model producer errors, and observer failures. |
| **P1 — define portable boundaries using protocol fixtures** | Have each model state support for tools, structured output, stops and streaming. Normalize valid message blocks, per-call correlation, output usage and typed values before the next layer consumes them. Keep requiredness separate from nullability, and bind arguments after resolving references and unwrapping media. Define the stream retry boundary before publication. Aggregate each new delta into the existing state, with pacing synchronized across users of one model instance. | Validate outgoing payload schemas offline using representative SDK types or metadata. Test ToolCallingAgent and CodeAgent request schema parity, indexed tool delta cases, textual stops split across chunks, PIL chaining, zero/false and optional values. Implement explicit fallback or diagnostic for unsupported capabilities. |
| **P2 — give applications deliberate retention and persistence controls** | Document conversation, application and executor lifetimes, with bounded prompt projection separate from trace retention. Store input messages compactly or on request. Make the portable configuration projection round-trip the supported plain data and disclose excluded extension callables. Document the supported manual step output. | Check cumulative versus per-run usage, visual prompts after several turns, stable agent config round-trips and replay content with bounded histories. Keep anchor tests for code persistence and manually edited plans. |

Likely day-to-day failures are stale state after an apparent fresh session, a retried side effect hidden by a failed sibling, a wrong managed summary under fan-out, a caller that cannot close or interrupt promptly, and a configuration that changes meaning across stream, sync or serialization. The first changes should protect the small sequential execution path and make ownership explicit. The source and tests already supply workable seams to add these acceptance cases without introducing a separate orchestration engine.

## 10. Evidence appendix

### 10.1 Pinned source crosswalk

All source paths and line numbers in this report refer to the pinned checkout from section 1. Short module names refer to `src/smolagents/`.

| Question | Primary source entry points | Corroborating local tests |
| --- | --- | --- |
| Where are start, planning, normal action and exhaustion implemented? | [agents.py:436–637,639–747,810–853][src-4] | [tests/test_agents.py:484–521,664–749,1245–1450][src-146], [tests/test_monitoring.py:65–99][src-84] |
| Where do tools enter the runtime and how do outcomes become prompts? | [agents.py:1276–1502][src-38], [memory.py:92–150][src-6], [models.py:288–413,599–610][src-147], [tools.py:1361–1412][src-142] | [tests/test_agents.py:1678–1915,1945–2090,2590–2628][src-148], [tests/test_tools.py:934–1064][src-149] |
| Where are cancellation, event order and callback timing defined? | [agents.py:540–637,754–787][src-5], [memory.py:280–316][src-35], [monitoring.py:57–117][src-115] | [tests/test_agents.py:1090–1218,1429–1450,1651–1676][src-150] |
| What does CodeAgent require from an executor? | [agents.py:1527–1764][src-17], [local_python_executor.py:285–357,1611–1793][src-79], [remote_executors.py:53–141,279–529][src-25] | [tests/test_local_python_executor.py:2189–2354][src-78], [tests/test_remote_executors.py:27–77,231–263][src-151] |
| What happens when a managed agent is called? | [agents.py:369–387,868–890,1260–1263,1453–1502,1598–1618][src-27] | [tests/test_agents.py:2104–2122,2445–2565][src-152] |
| How are model messages and stream chunks translated? | [models.py:123–413,518–610,1109–1151,1293–1385,1578–1668,1732–1818,2041–2133][src-37] | [tests/test_models.py:50–279,363–396,463–510,637–846,929–1053,1210–1316][src-153] |
| Where are configuration and source transfer defined? | [agents.py:892–1062,1118–1158,1766–1803][src-154], [tools.py:292–388,1061–1168,1335–1358][src-116], [serialization.py:45–249,451–507][src-26] | [tests/test_agents.py:1496–1643,2250–2344][src-155], [tests/test_serialization.py:95–438,820–896][src-156] |

### 10.2 Offline run commands

The following shell excerpts specify the run shape. `repo` points to the pinned repository and `scratch` to a disk-backed temporary directory. `py` points to the selected virtual environment's Python. The UV package operations used cached artifacts and `--offline`. pytest ran in the namespace and with the paths shown here. Repeat with a CPython 3.14 environment for the second pass.

```bash
repo="$PWD/repos/huggingface__smolagents"
scratch=$(mktemp -d $HOME/agent-work/scratch/smolagents-rerun.XXXXXXXX)
mkdir "$scratch/home" "$scratch/tmp"
uv venv --offline --python "$(command -v python)" "$scratch/venv"
py="$scratch/venv/bin/python"
uv pip install --offline --python "$py" \
  'huggingface-hub>=0.31.2' 'pillow>=10.0.1' python-dotenv requests rich jinja2 \
  pytest numpy pandas docker websocket-client boto3 ipython 'mcp<2'

run_offline() {
  unshare --user --map-root-user --mount --net bash -eu -c '
    repo=$1; scratch=$2; py=$3; shift 3
    mount --bind "$repo" "$repo"
    mount -o remount,bind,ro "$repo"
    cd "$scratch"
    exec env -i PATH="$(dirname "$py"):/usr/bin:/bin" HOME="$scratch/home" \
      TMPDIR="$scratch/tmp" XDG_CACHE_HOME="$scratch/cache" TZ=UTC \
      PYTHONPATH="$repo/src:$scratch" PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 \
      HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 AWS_EC2_METADATA_DISABLED=true \
      PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$py" "$@"
  ' _ "$repo" "$scratch" "$py" "$@"
}

run_offline -c 'import socket, smolagents; print(socket.if_nameindex(), smolagents.__file__)'
```

The only substitute fixture was `shared_datadir`. Save this module in the temporary directory as `tracked_image.py` if the repository's pytest-datadir extra is unavailable.

```python
from pathlib import Path
from shutil import copytree
import pytest

@pytest.fixture
def shared_datadir(request, tmp_path):
    return copytree(Path(str(request.node.path)).parent / "data", tmp_path / "data")
```

The broad suite uses the stock modules and this filter. Pytest config `addopts` and its cache provider are disabled for these runs. A separate run whose only change was removing the first four selections from the deselection filter is the initial broad result in section 7.

```bash
modules=(agents models tools memory monitoring function_type_hints_utils tool_validation
         remote_executors local_python_executor final_answer serialization types utils default_tools)
paths=()
for module in "${modules[@]}"; do paths+=("$repo/tests/test_$module.py"); done
exclude='not (test_multiagents_save or streaming_agent_image_output or streaming_agent_text_output
or streaming_with_agent_error or transformers_toolcalling_agent or init_agent_with_different_toolsets
or missing_import_triggers_advice or local_python_executor_with_custom_functions or TestOpenAIModel
or AzureOpenAIModel or LlamaCppModel or streaming_agent_final_answer_cannot_be_called
or toolcalling_agent_final_answer_cannot_be_called_with_parallel_tool_calls
or toolcalling_agent_stream_logs_multiple_tool_calls_observations or call_different_providers_without_key
or test_passing_flatten_messages or TestLiteLLMRouterModel or TestTransformersModel or transformers_message
or flatten_messages_as_text_for_all_models or tool_calls_json_serialization or TestToolCollection
or launch_gradio_demo or TestE2BExecutorUnit or TestModalExecutorUnit or TestBlaxelExecutorUnit
or TestLocalPythonExecutorSecurity or dangerous or unauthorized or check_import_authorized
or additional_imports_are_installed or additional_imports or test_imports or explicitly_authorized
or all_imports_authorized or get_safe_module or TestSafeSerializationSecurity or test_visit_webpage
or test_ddgs or TestSpeechToTextTool or wikipedia_search or TestWebSearchToolExa)'
run_offline -m pytest -o addopts='' -p no:cacheprovider -p tracked_image \
  --basetemp "$scratch/pytest-broad" "${paths[@]}" -k "${exclude//$'\n'/ }" -q -ra --tb=short

run_offline -m pytest -o addopts='' -p no:cacheprovider -q --tb=short \
  -W error::pytest.PytestUnraisableExceptionWarning \
  "$repo/tests/test_agents.py::TestToolCallingAgent::test_toolcalling_agent_passes_both_tools_and_managed_agents"

# This slice also requires the real OpenAI SDK in the chosen venv.
run_offline -m pytest -o addopts='' -p no:cacheprovider -q -ra --tb=short \
  "$repo/tests/test_models.py" "$repo/tests/test_agents.py" \
  -k 'TestOpenAIModel or TestAzureOpenAIModel or TestLlamaCppModel or toolcalling_agent_stream_logs_multiple_tool_calls_observations or toolcalling_agent_final_answer_cannot_be_called_with_parallel_tool_calls or (tool_calls_json_serialization and openai)'
```

For the base install, `git -C "$repo" archive HEAD | tar -x -C "$scratch/packaging"` produced a separate tree. I ran its `tests/test_import.py` with `uv` accessible inside the namespace, `UV_OFFLINE=1`, and the existing uv cache explicitly pointed to by `UV_CACHE_DIR`. The pytest driver added the archive's `src` to its own Python path and removed `PYTHONPATH` from the environment inherited by the subprocess under test. The nested install therefore imported its installed distribution. The command confirmed package build and installation from the archive. [tests/test_import.py:6–30][src-59].

### 10.3 Minimal public-entry-point reproductions

Copy this Python block into a scratch file and run it with `run_offline`. The assertions characterize the behavior observed at the pinned commit. Every model output and tool effect is local and predetermined.

```python
from inspect import getgeneratorstate
from threading import Event, Thread

from smolagents import CodeAgent, Tool, ToolCallingAgent
from smolagents.agents import ToolOutput
from smolagents.local_python_executor import ExecutionTimeoutError, LocalPythonExecutor
from smolagents.memory import ActionStep, PlanningStep, ToolCall
from smolagents.models import ChatMessage, ChatMessageToolCall, ChatMessageToolCallFunction, Model
from smolagents.monitoring import LogLevel
from smolagents.utils import AgentError, AgentMaxStepsError


def reply(content=None, calls=None):
    return ChatMessage(role="assistant", content=content, tool_calls=calls)


def code(source):
    return reply(f"<code>\n{source}\n</code>")


def call(name, args, identifier):
    return ChatMessageToolCall(ChatMessageToolCallFunction(args, name), identifier, "function")


class Script(Model):
    def __init__(self, *outputs):
        super().__init__(model_id="local-fixture")
        self.outputs = iter(outputs)
        self.inputs = []

    def generate(self, messages, **kwargs):
        self.inputs.append(messages)
        return next(self.outputs)


class Record(Tool):
    name = "record"
    description = "Record a fixture value."
    inputs = {"value": {"type": "integer", "description": "Value to record."}}
    output_type = "integer"

    def __init__(self, gate=None):
        super().__init__()
        self.gate = gate
        self.effects = []

    def forward(self, value: int) -> int:
        if value == 2 and self.gate is not None:
            assert self.gate.wait(5)
            raise ValueError("fixture failure")
        self.effects.append(value)
        return 7000 + value


def agent(cls, model, tools=None, **kwargs):
    return cls(tools=tools or [], model=model, verbosity_level=LogLevel.OFF, **kwargs)


# L1 and L2: close a pending action, then compare stream and memory on exhaustion.
for cls in (CodeAgent, ToolCallingAgent):
    rec = Record()
    first = code("record(1)") if cls is CodeAgent else reply(calls=[call("record", {"value": 1}, "z")])
    a = agent(cls, Script(first), [rec])
    g = a.run("close at proposal", stream=True)
    assert isinstance(next(g), ToolCall)
    try:
        g.close()
    except RuntimeError as error:
        assert str(error) == "generator ignored GeneratorExit"
    else:
        raise AssertionError("expected close error at this pin")
    assert getgeneratorstate(g) == "GEN_SUSPENDED" and not rec.effects
    g.close()

    a = agent(cls, Script(first, reply("fallback")), [rec], max_steps=1)
    events = list(a.run("exhaust", stream=True))
    live = [step for step in events if isinstance(step, ActionStep)]
    assert live[0] is live[1] and [step.step_number for step in live] == [1, 1]
    assert isinstance(a.memory.steps[-1].error, AgentMaxStepsError)
    assert a.memory.steps[-1].step_number == 2 and events[-1].output == "fallback"

# L3: cancel from the plan callback, then observe the action that followed it.
rec = Record()
a = agent(CodeAgent, Script(reply("plan"), code("record(9)")), [rec],
          max_steps=2, planning_interval=1,
          step_callbacks={PlanningStep: lambda step, agent: agent.interrupt()})
try:
    a.run("cancel after planning")
except AgentError as error:
    assert str(error) == "Agent interrupted."
else:
    raise AssertionError("expected eventual interruption")
assert rec.effects == [9]

# C1: complete and publish one tool, then allow its sibling to fail.
gate = Event()
rec = Record(gate)
request = reply(calls=[call("record", {"value": 1}, "z"), call("record", {"value": 2}, "a")])
finish = reply(calls=[call("final_answer", {"answer": "done"}, "f")])
m = Script(request, finish)
a = agent(ToolCallingAgent, m, [rec], max_tool_threads=2)
g = a.run("two-call action", stream=True)
try:
    assert [next(g).id, next(g).id] == ["z", "a"]
    first_result = next(g)
    assert isinstance(first_result, ToolOutput) and first_result.output == 7001
finally:
    gate.set()
assert list(g)[-1].output == "done"
assert rec.effects == [1] and a.memory.steps[1].observations is None
assert "7001" not in repr(m.inputs[1])

# E1: an ordinary gated function exceeds its deadline and its caller waits for release.
entered, gate, done = Event(), Event(), Event()
errors = []


def block():
    entered.set()
    assert gate.wait(5)
    return 77


def invoke():
    executor = LocalPythonExecutor([], additional_functions={"block": block}, timeout_seconds=0.02)
    executor.send_tools({})
    try:
        executor("block()")
    except ExecutionTimeoutError as error:
        errors.append(type(error).__name__)
    finally:
        done.set()


worker = Thread(target=invoke)
worker.start()
try:
    assert entered.wait(3) and not done.wait(0.12)
finally:
    gate.set()
    worker.join(3)
assert errors == ["ExecutionTimeoutError"] and not worker.is_alive()
print("Pinned stream, cancellation, batch and timeout behaviors reproduced")
```

For E4, a directly executable, no-service transfer fixture can be appended to the same file. It stands in for the remote kernel while using the repository's real transfer and final-tool rewrite. The separate measured WebSocket and E2B controls used [remote_executors.py:374–402,481–529][src-157] for decoding. The kernel fixture produced SDK-shaped execution results or matching WebSocket error and idle frames.

```python
from smolagents.default_tools import FinalAnswerTool
from smolagents.local_python_executor import CodeOutput
from smolagents.monitoring import AgentLogger
from smolagents.remote_executors import RemotePythonExecutor


class MemoryKernel(RemotePythonExecutor):
    def __init__(self):
        super().__init__([], AgentLogger(level=LogLevel.OFF))
        self.namespace = {}
        self.transfers = []

    def install_packages(self, imports):
        # All imports used in this fixture are locally present.
        return imports

    def run_code_raise_errors(self, source):
        self.transfers.append(source)
        try:
            exec(compile(source, "<local kernel fixture>", "exec"), self.namespace)
        except BaseException as error:
            if type(error).__name__ == self.FINAL_ANSWER_EXCEPTION:
                return CodeOutput(self._deserialize_final_answer(error.value), "", True)
            raise
        return CodeOutput(None, "", False)


kernel = MemoryKernel()
m = Script(code("final_answer(seed)"), code("final_answer(seed)"),
           reply("fallback"), code("final_answer(seed)"))
a = agent(CodeAgent, m, executor=kernel, max_steps=1, return_full_result=True)
r1 = a.run("first", additional_args={"seed": 5})
r2 = a.run("second", additional_args={"seed": 11})
assert r1.output == 5 and r1.state == "success"
assert r2.output == "fallback" and r2.state == "max_steps_error"
assert "allow_pickle_setting" in str(a.memory.steps[1].error)
assert type(a.tools["final_answer"]).__mro__[1].__name__ == "_FinalAnswerTool"
definitions = [source for source in kernel.transfers if "class _FinalAnswerTool" in source]
assert "allow_pickle_setting" not in definitions[0] and "allow_pickle_setting" in definitions[1]
a.tools["final_answer"] = FinalAnswerTool()
r3 = a.run("fresh final tool")
assert r3.output == 11 and r3.state == "success"
print("Pinned remote transfer reuse behavior reproduced")
```

This extra block checks the two model payload findings through the installed adapter and the SDK's local validation data. It uses the same `agent` and `reply` helpers above. The injected interfaces have no network implementation.

```python
from types import SimpleNamespace as NS

from botocore.session import get_session
from botocore.validate import validate_parameters
from smolagents.models import AmazonBedrockModel, InferenceClientModel, OpenAIModel
from smolagents.utils import AgentGenerationError


def complete(**payload):
    content = ('{"thought":"done","code":"final_answer(17)"}'
               if "response_format" in payload else "plain output")
    message = NS(role="assistant", content=content, tool_calls=None)
    return NS(choices=[NS(message=message)], usage=NS(prompt_tokens=4, completion_tokens=2))


client = NS(chat_completion=complete, chat=NS(completions=NS(create=complete)))
for adapter, kwargs, expected in (
    (InferenceClientModel, {"provider": "cerebras"}, "max_steps_error"),
    (OpenAIModel, {}, "success"),
):
    model = adapter(model_id="local-contract", client=client, **kwargs)
    a = agent(CodeAgent, model, use_structured_outputs_internally=True, max_steps=1)
    assert a.run("structured", return_full_result=True).state == expected

shape = get_session().get_service_model("bedrock-runtime").operation_model("Converse").input_shape


def bedrock_payload(**payload):
    validate_parameters(payload, shape)
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": "<code>final_answer(15)</code>"}]}},
        "usage": {"inputTokens": 4, "outputTokens": 3},
    }


m = AmazonBedrockModel(model_id="local-fixture", client=NS(converse=bedrock_payload))
assert agent(CodeAgent, m).run("valid text request") == 15
try:
    agent(ToolCallingAgent, m).run("tool request")
except AgentGenerationError as error:
    assert 'Unknown parameter in input: "tools"' in str(error)
    assert 'Unknown parameter in input: "tool_choice"' in str(error)
else:
    raise AssertionError("expected request-shape mismatch at this pin")
print("Pinned model payload behaviors reproduced")
```

### 10.4 Final evidence checks

```bash
GIT_OPTIONAL_LOCKS=0 git -C "$repo" rev-parse HEAD 'HEAD^{tree}'
GIT_OPTIONAL_LOCKS=0 git -C "$repo" status --porcelain=v1 --untracked-files=all --ignored=matching
GIT_OPTIONAL_LOCKS=0 git -C "$repo" diff --check
```

The checkout was checked at intake and during probing. An additional comparison matched 17 working files, including the core modules and representative tests, byte for byte against the pinned Git blobs. The closing check and UTC elapsed time are recorded in section 1. Only this report is a retained evaluation deliverable.

[src-1]: repos/huggingface__smolagents/pyproject.toml:5
[src-2]: repos/huggingface__smolagents/CONTRIBUTING.md:35
[src-3]: repos/huggingface__smolagents/src/smolagents/agents.py:294
[src-4]: repos/huggingface__smolagents/src/smolagents/agents.py:436
[src-5]: repos/huggingface__smolagents/src/smolagents/agents.py:540
[src-6]: repos/huggingface__smolagents/src/smolagents/memory.py:92
[src-7]: repos/huggingface__smolagents/src/smolagents/agents.py:569
[src-8]: repos/huggingface__smolagents/src/smolagents/memory.py:126
[src-9]: repos/huggingface__smolagents/src/smolagents/utils.py:92
[src-10]: repos/huggingface__smolagents/src/smolagents/agents.py:498
[src-11]: repos/huggingface__smolagents/src/smolagents/agent_types.py:254
[src-12]: repos/huggingface__smolagents/src/smolagents/agents.py:1260
[src-13]: repos/huggingface__smolagents/src/smolagents/models.py:193
[src-14]: repos/huggingface__smolagents/src/smolagents/tools.py:228
[src-15]: repos/huggingface__smolagents/src/smolagents/agents.py:1335
[src-16]: repos/huggingface__smolagents/src/smolagents/prompts/toolcalling_agent.yaml:5
[src-17]: repos/huggingface__smolagents/src/smolagents/agents.py:1527
[src-18]: repos/huggingface__smolagents/src/smolagents/models.py:43
[src-19]: repos/huggingface__smolagents/src/smolagents/utils.py:189
[src-20]: repos/huggingface__smolagents/src/smolagents/local_python_executor.py:332
[src-21]: repos/huggingface__smolagents/src/smolagents/local_python_executor.py:1445
[src-22]: repos/huggingface__smolagents/tests/test_local_python_executor.py:644
[src-23]: repos/huggingface__smolagents/tests/test_agents.py:562
[src-24]: repos/huggingface__smolagents/src/smolagents/agents.py:1593
[src-25]: repos/huggingface__smolagents/src/smolagents/remote_executors.py:53
[src-26]: repos/huggingface__smolagents/src/smolagents/serialization.py:45
[src-27]: repos/huggingface__smolagents/src/smolagents/agents.py:369
[src-28]: repos/huggingface__smolagents/src/smolagents/monitoring.py:81
[src-29]: repos/huggingface__smolagents/tests/test_agents.py:2511
[src-30]: repos/huggingface__smolagents/src/smolagents/agents.py:758
[src-31]: repos/huggingface__smolagents/src/smolagents/memory.py:50
[src-32]: repos/huggingface__smolagents/src/smolagents/models.py:282
[src-33]: repos/huggingface__smolagents/src/smolagents/agents.py:256
[src-34]: repos/huggingface__smolagents/src/smolagents/models.py:203
[src-35]: repos/huggingface__smolagents/src/smolagents/memory.py:280
[src-36]: repos/huggingface__smolagents/src/smolagents/monitoring.py:36
[src-37]: repos/huggingface__smolagents/src/smolagents/models.py:123
[src-38]: repos/huggingface__smolagents/src/smolagents/agents.py:1276
[src-39]: repos/huggingface__smolagents/src/smolagents/agents.py:577
[src-40]: repos/huggingface__smolagents/src/smolagents/memory.py:51
[src-41]: repos/huggingface__smolagents/src/smolagents/agents.py:582
[src-42]: repos/huggingface__smolagents/src/smolagents/local_python_executor.py:1658
[src-43]: repos/huggingface__smolagents/src/smolagents/agents.py:328
[src-44]: repos/huggingface__smolagents/src/smolagents/agents.py:1373
[src-45]: repos/huggingface__smolagents/src/smolagents/models.py:239
[src-46]: repos/huggingface__smolagents/src/smolagents/agents.py:449
[src-47]: repos/huggingface__smolagents/src/smolagents/local_python_executor.py:1743
[src-48]: repos/huggingface__smolagents/tests/test_agents.py:417
[src-49]: repos/huggingface__smolagents/src/smolagents/models.py:468
[src-50]: repos/huggingface__smolagents/src/smolagents/local_python_executor.py:1698
[src-51]: repos/huggingface__smolagents/src/smolagents/local_python_executor.py:1666
[src-52]: repos/huggingface__smolagents/tests/test_agents.py:664
[src-53]: repos/huggingface__smolagents/src/smolagents/agents.py:1416
[src-54]: repos/huggingface__smolagents/src/smolagents/tools.py:106
[src-55]: repos/huggingface__smolagents/src/smolagents/_function_type_hints_utils.py:204
[src-56]: repos/huggingface__smolagents/src/smolagents/memory.py:25
[src-57]: repos/huggingface__smolagents/src/smolagents/agents.py:416
[src-58]: repos/huggingface__smolagents/tests/test_agents.py:1429
[src-59]: repos/huggingface__smolagents/tests/test_import.py:6
[src-60]: repos/huggingface__smolagents/tests/test_memory.py:52
[src-61]: repos/huggingface__smolagents/tests/test_agents.py:1651
[src-62]: repos/huggingface__smolagents/docs/source/en/guided_tour.md:627
[src-63]: repos/huggingface__smolagents/docs/source/en/examples/plan_customization.md:10
[src-64]: repos/huggingface__smolagents/examples/plan_customization/plan_customization.py:62
[src-65]: repos/huggingface__smolagents/src/smolagents/local_python_executor.py:279
[src-66]: repos/huggingface__smolagents/src/smolagents/agents.py:1723
[src-67]: repos/huggingface__smolagents/tests/test_local_python_executor.py:2240
[src-68]: repos/huggingface__smolagents/src/smolagents/models.py:934
[src-69]: repos/huggingface__smolagents/tests/test_agents.py:1815
[src-70]: repos/huggingface__smolagents/src/smolagents/agents.py:468
[src-71]: repos/huggingface__smolagents/src/smolagents/tools.py:126
[src-72]: repos/huggingface__smolagents/src/smolagents/agents.py:490
[src-73]: repos/huggingface__smolagents/src/smolagents/remote_executors.py:94
[src-74]: repos/huggingface__smolagents/src/smolagents/tools.py:1335
[src-75]: repos/huggingface__smolagents/src/smolagents/utils.py:285
[src-76]: repos/huggingface__smolagents/src/smolagents/agents.py:1702
[src-77]: repos/huggingface__smolagents/tests/test_agents.py:2346
[src-78]: repos/huggingface__smolagents/tests/test_local_python_executor.py:2189
[src-79]: repos/huggingface__smolagents/src/smolagents/local_python_executor.py:285
[src-80]: repos/huggingface__smolagents/src/smolagents/tools.py:231
[src-81]: repos/huggingface__smolagents/src/smolagents/remote_executors.py:481
[src-82]: repos/huggingface__smolagents/src/smolagents/local_python_executor.py:1705
[src-83]: repos/huggingface__smolagents/tests/test_agents.py:501
[src-84]: repos/huggingface__smolagents/tests/test_monitoring.py:65
[src-85]: repos/huggingface__smolagents/src/smolagents/agents.py:505
[src-86]: repos/huggingface__smolagents/src/smolagents/models.py:214
[src-87]: repos/huggingface__smolagents/tests/test_agents.py:739
[src-88]: repos/huggingface__smolagents/src/smolagents/models.py:38
[src-89]: repos/huggingface__smolagents/src/smolagents/agents.py:1655
[src-90]: repos/huggingface__smolagents/src/smolagents/models.py:518
[src-91]: repos/huggingface__smolagents/tests/test_models.py:812
[src-92]: repos/huggingface__smolagents/src/smolagents/models.py:79
[src-93]: repos/huggingface__smolagents/src/smolagents/utils.py:528
[src-94]: repos/huggingface__smolagents/src/smolagents/agents.py:1383
[src-95]: repos/huggingface__smolagents/src/smolagents/_function_type_hints_utils.py:291
[src-96]: repos/huggingface__smolagents/tests/test_tools.py:973
[src-97]: repos/huggingface__smolagents/src/smolagents/agents.py:1284
[src-98]: repos/huggingface__smolagents/src/smolagents/memory.py:57
[src-99]: repos/huggingface__smolagents/src/smolagents/models.py:1177
[src-100]: repos/huggingface__smolagents/src/smolagents/utils.py:497
[src-101]: repos/huggingface__smolagents/src/smolagents/memory.py:112
[src-102]: repos/huggingface__smolagents/src/smolagents/models.py:348
[src-103]: repos/huggingface__smolagents/src/smolagents/agents.py:1293
[src-104]: repos/huggingface__smolagents/src/smolagents/models.py:220
[src-105]: repos/huggingface__smolagents/src/smolagents/memory.py:228
[src-106]: repos/huggingface__smolagents/src/smolagents/agents.py:970
[src-107]: repos/huggingface__smolagents/src/smolagents/models.py:612
[src-108]: repos/huggingface__smolagents/src/smolagents/agents.py:772
[src-109]: repos/huggingface__smolagents/docs/source/en/tutorials/memory.md:97
[src-110]: repos/huggingface__smolagents/src/smolagents/agents.py:268
[src-111]: repos/huggingface__smolagents/src/smolagents/memory.py:214
[src-112]: repos/huggingface__smolagents/src/smolagents/agents.py:110
[src-113]: repos/huggingface__smolagents/src/smolagents/tools.py:144
[src-114]: repos/huggingface__smolagents/src/smolagents/memory.py:236
[src-115]: repos/huggingface__smolagents/src/smolagents/monitoring.py:57
[src-116]: repos/huggingface__smolagents/src/smolagents/tools.py:292
[src-117]: repos/huggingface__smolagents/tests/test_local_python_executor.py:2230
[src-118]: repos/huggingface__smolagents/tests/test_agents.py:176
[src-119]: repos/huggingface__smolagents/pyproject.toml:13
[src-120]: repos/huggingface__smolagents/tests/conftest.py:9
[src-121]: repos/huggingface__smolagents/tests/utils/markers.py:17
[src-122]: repos/huggingface__smolagents/.github/workflows/tests.yml:19
[src-123]: repos/huggingface__smolagents/pyproject.toml:92
[src-124]: repos/huggingface__smolagents/tests/test_agents.py:633
[src-125]: repos/huggingface__smolagents/tests/test_models.py:279
[src-126]: repos/huggingface__smolagents/tests/test_telemetry.py:25
[src-127]: repos/huggingface__smolagents/tests/test_monitoring.py:100
[src-128]: repos/huggingface__smolagents/tests/test_agents.py:2382
[src-129]: repos/huggingface__smolagents/src/smolagents/default_tools.py:129
[src-130]: repos/huggingface__smolagents/src/smolagents/mcp_client.py:103
[src-131]: repos/huggingface__smolagents/src/smolagents/local_python_executor.py:1321
[src-132]: repos/huggingface__smolagents/tests/test_local_python_executor.py:1338
[src-133]: repos/huggingface__smolagents/tests/test_serialization.py:798
[src-134]: repos/huggingface__smolagents/src/smolagents/agents.py:523
[src-135]: repos/huggingface__smolagents/tests/test_agents.py:717
[src-136]: repos/huggingface__smolagents/src/smolagents/local_python_executor.py:1775
[src-137]: repos/huggingface__smolagents/src/smolagents/monitoring.py:100
[src-138]: repos/huggingface__smolagents/src/smolagents/agents.py:570
[src-139]: repos/huggingface__smolagents/src/smolagents/models.py:965
[src-140]: repos/huggingface__smolagents/src/smolagents/models.py:1586
[src-141]: repos/huggingface__smolagents/src/smolagents/models.py:434
[src-142]: repos/huggingface__smolagents/src/smolagents/tools.py:1361
[src-143]: repos/huggingface__smolagents/tests/test_agents.py:145
[src-144]: repos/huggingface__smolagents/src/smolagents/agents.py:1299
[src-145]: repos/huggingface__smolagents/src/smolagents/utils.py:512
[src-146]: repos/huggingface__smolagents/tests/test_agents.py:484
[src-147]: repos/huggingface__smolagents/src/smolagents/models.py:288
[src-148]: repos/huggingface__smolagents/tests/test_agents.py:1678
[src-149]: repos/huggingface__smolagents/tests/test_tools.py:934
[src-150]: repos/huggingface__smolagents/tests/test_agents.py:1090
[src-151]: repos/huggingface__smolagents/tests/test_remote_executors.py:27
[src-152]: repos/huggingface__smolagents/tests/test_agents.py:2104
[src-153]: repos/huggingface__smolagents/tests/test_models.py:50
[src-154]: repos/huggingface__smolagents/src/smolagents/agents.py:892
[src-155]: repos/huggingface__smolagents/tests/test_agents.py:1496
[src-156]: repos/huggingface__smolagents/tests/test_serialization.py:95
[src-157]: repos/huggingface__smolagents/src/smolagents/remote_executors.py:374
