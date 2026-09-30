# 面向 system-proof agent 的 FM 函数分析

`analyze-function` 暴露了 `system_proof` 使用的 bounded FM-Agent workflow。它分析一个选定函数，只展开一个选定的 blocking callee，保留 refinement history，并把 child 结果返回 direct caller。

使用它改进 candidate contract 或 proof decomposition。不要用它判断 specification 是否充分、implementation 是否正确、bug 是否已确认或 proof-map edge 是否关闭。

## 输入

准备两个简短文本文件：

- **intent**：待调查的 caller-visible behavior，包括明确不在 claim 中的内容；
- **caller context**：direct caller fact、当前 blocking obligation 和已批准 assumptions。

保持原始 system goal 不变。选择一个精确的 repository-relative source file 和 function symbol。line number 是可选参数，只用于区分重复 symbol；复制到其他 revision 后行号可能变化。

需要保留的实验应使用新的 target worktree/copy 和新的 session path。命令会拒绝覆盖已有 session，以保留历史。

Intent 示例：

```text
成功时，snapshot-owned projection 与已接受的 snapshot 相等，
而 destination-owned resources 保持独立。观察点位于 execution resume 之前。
不假设 failure atomicity。
```

## 命令

创建 session：

```sh
analyze-function analyze \
  --repo /path/to/isolated-project \
  --session /path/to/evidence/restore-session.json \
  --file src/worker.rs \
  --symbol Type::restore_snapshot_state \
  --intent /path/to/intent.txt \
  --caller-context /path/to/caller-context.txt
```

检查 session 和 root node：

```sh
analyze-function show --session /path/to/evidence/restore-session.json
analyze-function show --session /path/to/evidence/restore-session.json \
  --node restore_snapshot_state
```

把一个 obligation 展开到一个显式 callee：

```sh
analyze-function expand \
  --session /path/to/evidence/restore-session.json \
  --parent restore_snapshot_state \
  --obligation O1 \
  --file src/worker.rs \
  --symbol restore
```

模型可能建议多个 callees。该列表只是 navigation advice，不代表可以全部展开。只有当 callee 阻塞 active proof-map obligation 时才选择它。

使用保留的 feedback refine node：

```sh
analyze-function refine \
  --session /path/to/evidence/restore-session.json \
  --node restore \
  --feedback /path/to/refinement-feedback.md
```

Feedback 应引用具体 source behavior、proof failure、test evidence 或已批准的 domain distinction。Refinement 会保留 previous analysis；不能通过反复调用模型来删除不方便的结果。

把 child 结果返回 direct caller：

```sh
analyze-function reintegrate \
  --session /path/to/evidence/restore-session.json \
  --parent restore_snapshot_state \
  --child restore
```

进行独立 Rust/Verus contract 实验时，在 `analyze` 和 `expand` 中加入 `--strip-verification-annotations`。它会从模型输入中移除 inline Verus specification/verification attributes，同时保留原始 source span hash 和 line identity。它不会隐藏普通 comments、相邻文件或 intent/feedback 中显式提供的事实；声称 independent recovery 时必须记录这一 information boundary。

## 产生的 evidence

Session 包含：

- repository revision、source file、line span 和原始 source SHA-256；
- 对模型输入应用的 transform；
- caller intent 和 context；
- proposed precondition、postcondition 和 failure condition；
- abstraction：abstract state、projection、preserved state、hidden representation 和 observation boundary；
- implementation assessments 和 uncertainties；
- 带区分场景的 stronger/weaker candidate variants；
- 可选择的 obligations 和 suggested callees；
- 显式 parent-child edges；
- refinement history 和 prior analyses；
- reintegration rationale、remaining gaps 和 proposed proof-map updates；
- 相邻 `.artifacts/` 目录中的 structured prompts、responses 和 rejected retries。

这些是 **source-bound advisory evidence**：它记录哪个 source span 和 analysis method 产生了某个 proposal。它不是 implementation proof、specification completeness、executable bug confirmation 或 Human acceptance。

Source 或 contract 变化后复用 session 前，应比较记录的 revision/source hash 与当前 target。FM session 会记录这些 identities，但当前不会自动把 stale status 传播到 system-proof proof map。

## 如何阅读结果

### Contract

在选定 observation boundary 上提出的 behavior。即使 contract 与函数 body 一致，它仍可能过强、过弱或依赖未声明 assumption。

### Abstraction 和 projection

**Abstraction** 命名 caller 关心的 logical state；**projection** 把 concrete fields 和 representation objects 映射到该 logical state。例如 VM snapshot 通常是 snapshot-owned guest state 的 projection，而不是整个 runtime object 的 equality。

### Frame condition

必须保持不变的 state。Wrapper 把 mutation 委托给 callee 时尤其需要 frame condition；wrapper 中没有直接 assignment 并不能证明 preservation。

### Blocking obligation

阻止 caller claim 建立的精确 missing fact。它可能要求 callee contract、representation lemma、failure test、ownership fact 或 Human intent decision。

### Refinement

根据新 evidence 或明确 semantic distinction 修订一个 node。Refinement 应缩小 ambiguity 或修正 overclaim，而不是反复询问模型直到得到同意。

### Reintegration

说明 child analysis 如何改变其 direct caller 的步骤。Reintegration 可以保持 obligation open；当它把模糊 uncertainty 转化为明确 proof dependencies 时，这仍然是有价值的结果。

### Global-invariant candidate

必须跨多个 operation、representation 或 lifecycle phase 持续成立的 premise。典型例子包括 snapshot capture 期间 membership 稳定、restore 期间持续 stopped、logical mapping 与 hardware page table 一致，以及 ownership authority conservation。

应将这类 premise 提升到 system-proof map，或使用 `analyze-protocol` 调查。不要把它复制成每个函数下面互不关联的局部 preconditions。

## Agent 可以和不可以得出的结论

Agent 可以：

- 提出 candidate contracts 和 abstractions；
- 标记 source-supported 或 challenged claims；
- 创建 proof-map obligations；
- 推荐成本最低且有区分力的 proof、test、source audit 或 Human-intent check；
- 报告 child analysis 加强、削弱或未能支持 caller claim。

Agent 不可以：

- 仅根据 FM output 选择 adequate specification；
- 把 `MATCH`、`discharged`、model confidence 或没有 counterexample 解释为 proof；
- 把 FM session 作为关闭 proof-map edge 的 evidence；
- 静默地把 global-invariant candidate 变成 assumption；
- 没有 executable/formal evidence 就确认 bug；
- 为了让局部 contract 更容易而改变原始 system goal。

## 返回 system-proof campaign

返回以下 compact handoff：

```text
goal and direct caller
analyzed source identity
selected obligation and child
supported, challenged and unresolved proposals
global-invariant candidates
cheapest next authoritative check
session and artifact paths
```

使用 `map declare` 记录真实 remaining obligations，而不是认证 FM narrative。使用 source audit、native tests、implementation proof、model checking 或 bounded Human intent judgment 改变 authoritative status。继续向 top-level caller reintegrate；一组局部看似合理的 contracts 不等于 global proof progress。

## Trust 和操作限制

- FM-Agent 使用 permissive tool flags 调用 authenticated coding-agent CLI。Bounded prompt 和 isolated worktree 不是 operating-system sandbox。
- Strict JSON validation 会拒绝 malformed/incomplete model output，但 retry 只增加成本，不增加 epistemic authority。
- Suggested callees 可能不完整或错误；proof map 仍然是 scope authority。
- 如果不显式从模型输入中移除 embedded specifications，它们会污染 independent recovery。
- `open` 不是失败：当它暴露出精确的 invariant、callee contract 或 verification step 时，它仍然有价值。
