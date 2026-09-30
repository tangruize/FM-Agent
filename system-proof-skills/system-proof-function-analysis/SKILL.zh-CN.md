---
name: system-proof-function-analysis
description: "在 system-proof campaign 中使用 FM-Agent 进行有界、source-bound 的函数 contract 和 obligation 分析。当一个 caller 所需事实被某个选定函数或 callee 阻塞时使用；跨 shared state、lifecycle、concurrency 或多个 operation 的性质应升级为 protocol analysis。"
---

# System-proof 函数分析

将 `analyze-function` 作为 advisory specialist 使用。它提出 contract、abstraction、counterexample 和 proof obligation；它不负责选择充分的 specification、建立 invariant、确认 bug、关闭 proof-map edge 或批准 intent。

本文件足以完成常规调用。需要完整 evidence contract、术语、refinement 规则和 trust limits 时再阅读 [GUIDE.zh-CN.md](GUIDE.zh-CN.md)。

## 何时使用

当 active caller 需要以下事实时使用本 skill：

- 一个函数精确的成功或失败行为；
- concrete representation 投影出的 abstract state；
- 一个选定 callee 应提供的 frame condition；
- 带有区分场景的 stronger/weaker contracts；
- 一个 blocking proof obligation 下一步需要的 lemma、test 或 source audit。

不要仅因为某个函数 reachable 就使用它。如果所需性质跨越多个 writer 或 operation，例如 lifecycle phase、callback、concurrency、跨 `await` 的时间区间、save/restore composition、ownership conservation 或 failure compensation，应使用 `analyze-protocol`。Function analysis 可以发现这类性质，但不能建立它。

## 必需输入

- 保持不变的顶层 system-proof goal；
- 一个精确的 source file 和 function symbol；
- direct caller 当前需要的事实；
- observation boundary 和相关 assumptions；
- 一个需要调查的 proof-map obligation；
- 一个新的 session path；需要保留的实验还应使用隔离的 source worktree 或 copy。

不要把 campaign goal 替换成更容易的局部 helper claim。模型建议的 callee 不是 authority；只有当某个 callee 阻塞当前 caller obligation 时才选择展开它。

## 基本用法

创建并检查一个 source-bound session：

```sh
analyze-function analyze \
  --repo /path/to/isolated-project \
  --session /path/to/new-session.json \
  --file src/module.rs \
  --symbol Type::method \
  --intent intent.txt \
  --caller-context caller-context.txt

analyze-function show --session /path/to/new-session.json
```

从 `show` 中选择一个 open obligation，然后展开一个 blocking callee 并返回结果：

```sh
analyze-function expand \
  --session /path/to/new-session.json \
  --parent method \
  --obligation O1 \
  --file src/callee.rs \
  --symbol selected_callee

analyze-function reintegrate \
  --session /path/to/new-session.json \
  --parent method \
  --child selected_callee
```

只有新的 source、proof、test 或已批准 domain evidence 会改变分析时，才使用 `refine --node NODE --feedback FILE`。进行独立 Rust/Verus contract 实验时，在 `analyze` 和 `expand` 中加入 `--strip-verification-annotations`。

Reintegration 后，报告 session path、分析的 source identity、selected obligation、supported/challenged claims、remaining gaps、global-invariant candidates 和下一项 authoritative check。不要把 session 作为 proof evidence attach。

## 操作流程

1. 对一个显式指定的函数运行 `analyze-function analyze`。
2. 使用 `show` 检查 node；把 contract、abstraction、variants 和 obligations 视为 proposals。
3. 下一步最多选择一个 blocking obligation 和一个 callee。
4. 运行 `expand`。只有获得具体 source、proof、test 或 domain feedback 时才使用 `refine`，并保留旧 revision。
5. 运行 `reintegrate`，说明 child 结果如何影响其 direct caller。
6. 将剩余局部 obligations 返回 proof map。如果一个 premise 跨越多个 writer、lifecycle phase、callback、await、save/restore 两侧或 ownership domain，将其记录为 global-invariant candidate，并使用 `analyze-protocol` 或 authoritative proof work。

当 caller fact 已被收敛为一个 proof/test/Human-intent check、继续扩大 scope 却没有明确 blocking obligation，或下一步已经是 specification adequacy 判断而不是 source analysis 时停止。

## Evidence 边界

保留 session JSON 及其 artifacts。报告 source identity、分析 span、analysis transform、caller obligation、child edge、contract/abstraction revisions、candidate variants、uncertainties 和 reintegration disposition。

FM session 内的 `open`、`conditional`、`discharged` 和 `refuted` 只是 analysis dispositions。没有独立且 admissible 的 evidence，它们绝不能成为 authoritative system-proof status。source-supported narrative 仍然只是 advisory；`MATCH`、未发现 counterexample 和模型 confidence 都不是 proof。
