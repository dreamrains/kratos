# 验收控制、浏览器与真实调用操作规程

本文件承接原 AGENTS.md 的详细验收操作；日常规则见[AGENTS.md](../../AGENTS.md)，阶段身份与进度只见[唯一计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)。原文移出前的完整字节保留于 artifacts/s5fix03/AGENTS-before.md。

## 当前规则（2026-10-20 用户补充，优先于下文历史 HTTP 条款）

- S4 与 S5 必须实际使用浏览器验证正常用户链。可冻结 browser_ui 或 combined_http_api_browser；HTTP 可创建会话、上传、发送原提示及核对持久化，浏览器须检查同一会话的正文、表格、公式、图表、确认、工作台、刷新、导出及必要窄屏/键盘行为。HTTP-only 仅是引擎/接口诊断，不能签 S4/S5 通过。
- 每批执行整个冻结矩阵、全部场景和可安全继续的原轮次。普通语义、工具、呈现或本会话投影失败记录后继续其他独立场景；不能安全继续的同会话依赖轮次保留分母并标 blocked。不得第一次普通失败就整批退出，不以仅重跑失败场景代替完整对比；整批结束后再修复。
- 仅在系统性全局问题或无法证明全局安全/身份时整批停止：Provider/记账/额度/冻结身份异常、SHA 或归属/权限异常、跨会话/跨版本串用、SSE/持久化终态矛盾或在途状态未知、整服务不可用。无法证明为局部的未知异常保守停止。普通 Browser 控制桥故障不阻塞独立离线工作；受影响视觉记 unassessed，本批不能获完整浏览器通过。
- 下一次真实调用测试上限为 800 次物理调用，所有主调用/辅助调用/现有一次审核共享计数；此数值是新的冻结上限，不是执行授权，也不继承旧批次余量。新 .env 的模型、端点和完整非秘密参数必须重新核定。执行前仍须冻结精确候选、原输入/提示/独立 oracle、完整矩阵、组合路线、浏览器检查点、有限预算及账本路径，并取得用户对该精确清单的新授权。不重试、回退、续跑或自动加额。
- 现行批次不得采用下文“仅 M06 补充”的历史例外。历史材料、旧授权和旧补充收据保留原身份，只读追溯，不转成当前可执行授权。
- 详细服务、浏览器操作、安全终态、原件保全程序沿用下文。若浏览器不可用，先核服务、再修控制运行时；不得用非视觉结果或旧确认代签当前候选。

## 当前组合路线检查点

沿既有 HTTP driver 的同一进程、同一账本使用 closed_ledger_stdin_v2：每个实际冻结确认卡在 HTTP 提交前暂停只读浏览器观察；每个场景结束再次暂停，核正文、工作台、刷新及该场景要求的导出。检查点显式回传 scenario/session_id/checkpoint，绑定本批目录内 JSON 原件 SHA；原件记录 status（passed/failed/unassessed）、具名 checks 和实际截图/DOM证据路径。确认检查为 confirmation，场景终点为 answer/workbench/refresh，要求导出时另加 exports。缺记录、未核或检查未全过均不能签浏览器通过；视觉失败本身记录后继续独立场景，不重新发送已执行提示。浏览器不代 HTTP 二次提交确认，不增加 Provider 或审核调用。

## 迁入的详细流程与历史规则

以下保留迁入内容。与上述当前规则冲突时，以当前规则及用户最新明确指令为准。

# Data Agent repository instructions

## Local acceptance control routes

Choose and record the control route **before** a batch: built-in browser UI,
existing app HTTP API, or a combined HTTP-created session plus browser visual
inspection. A route change requires a fresh run directory and a new result
identity; never merge sessions or call a nonvisual run a browser pass. Preserve
the same frozen scenarios and independent oracles across routes. Ordinary
control-tool failures must not block unrelated engine, receipt, or Provider-
disabled work; mark the affected UI oracle `unassessed` and continue on a
labelled route. This is an evidence-level choice, not a product upload defect.

The P08 real-Provider HTTP matrix below remains a separate, frozen batch with
its own authorization and Provider ledger. The local control-route flexibility
does not authorize a real Provider call or change formal publication defaults.

### 1. Verify the rehearsal service before touching the browser

- Before launching, run `git worktree list --porcelain` and verify the selected
  worktree contains both `.venv\Scripts\python.exe` and
  `scripts\testing\run_p7_browser_rehearsal.py`.  Check that the chosen run
  directory does not exist and that the port is not already listening.  These
  are launch preconditions, not reasons to invent a different entry point.
- Use the existing Provider-disabled entry point only:

  ```powershell
  .venv\Scripts\python.exe scripts\testing\run_p7_browser_rehearsal.py --port <port> --run-dir tmp\<fresh-run-dir>
  ```

- The run directory must not already exist. Prefer starting the command as a long-lived Codex exec session and retain both its exec-session ID and the listening OS PID. Poll that same exec session during the batch. A detached `Start-Process -WindowStyle Hidden` may be used only when its PID and redirected stdout/stderr are retained; do not assume it survived a turn interruption or context compaction.
- On Windows, `CreateProcessWithLogonW failed: 1909` is a command-host launch
  failure: the rehearsal child did not start.  Do not retry the same default
  command channel, change ports, switch launch methods, or debug the browser.
  First verify that no PID/listener/run directory was created, then rerun the
  exact command once through the approved elevated exec channel and retain its
  exec-session ID.  If an interruption occurs after a launch returned a
  session ID, poll that session and the health endpoint before considering any
  restart.
- Verify `http://127.0.0.1:<port>/__p7__/health` before navigating. The response must contain `"ok": true` and `"provider_enabled": false`.
- Recheck the health endpoint before every major matrix group and immediately after any interrupted turn. If the page says the site cannot be reached or shows `Failed to fetch`, check the retained exec session/PID, listening port, health endpoint, stdout, and stderr first. Those messages mean the frontend could not reach the local service until proven otherwise; do not troubleshoot the page, upload control, fixture, or browser security policy until the service is healthy.
- Never enable Provider transport for this rehearsal. At the end, verify `runtime.jsonl` has zero `forbidden_provider_transport` events and report actual Provider initiated calls as 0.

### 2. Select an available visual control capability

- Prefer the installed Browser capability for the existing Codex in-app browser
  tab at `http://127.0.0.1:<port>/`. After a REPL reset, reacquire that tab by
  URL before creating another. If `cua_repl` is the available interface, its
  first call in a fresh session is:

  ```javascript
  let tab = await cua.getTab(
    { url: "http://127.0.0.1:<port>/" },
    { browser: "iab" },
  );
  ```

  Check the returned browser identity and URL. Use fresh accessibility/DOM
  state and role/name locators where available. Do not substitute an unrelated
  Chrome/Edge profile or add Playwright CLI/Selenium.
- If this binding is unavailable, check the installed Browser plugin/runtime
  once. The Computer Use skill prohibits operating the Codex desktop UI, so
  it is not a fallback for the in-app browser. Mark visual oracles `unassessed`
  and use the existing HTTP app path for nonvisual oracles. Do not infer that
  a nearby click succeeded from pointer position alone.
- HTTP may create/upload/chat in a session and the browser may subsequently
  inspect that same session's visible answer, chart, export, and refresh. Such
  a combined run assesses those visual oracles, while the upload picker remains
  `unassessed`. Keep session IDs and control actions in one run record.
- For a Provider-disabled HTTP-only run, use the same healthy rehearsal
  service and its existing `/api/upload`, `/api/chat`, SSE, session, and export
  endpoints. A bounded run-dir script may drive those endpoints; record its
  digest, scenario inputs, upload ticket filename/SHA, session IDs, one
  terminal per turn, persisted state, and `provider_calls=0`. This is app-path
  evidence, not E3 visual evidence. Do not use the frozen real-Provider P08
  driver against the rehearsal service or call the route a browser pass.

### 3. Upload and verify through the selected route

For a browser-upload oracle, first use the visible upload control with the
Browser tool's `filechooser`. Attach the rejection handler when creating the
promise so a timeout cannot reset the browser kernel:

```javascript
const chooserPromise = tab.playwright
  .waitForEvent("filechooser", { timeoutMs: 10000 })
  .catch(error => ({ error: String(error) }));
await tab.playwright
  .locator('label:has(input[type="file"])')
  .first()
  .click();
const chooser = await chooserPromise;
if (chooser.error) throw new Error(chooser.error);
await chooser.setFiles(paths, { timeoutMs: 10000 });
```

- Resolve fixtures to absolute paths first and attach all files for a scenario
  together. After any upload action, fetch fresh visible state and confirm each
  filename and the returned upload ticket before sending the prompt.
- If the visible control click misses or the filechooser bridge fails, capture
  fresh UI evidence once. An official Browser `setFiles` on a verified file
  control is permitted as a **new labelled UI procedure**; verify filenames
  and tickets afterward. Do not repeatedly click guessed coordinates or use
  Computer Use to operate the Codex window. If Browser upload is unavailable,
  use the existing `/api/upload` HTTP route and mark the picker oracle
  `unassessed`; do not call the product upload broken from automation alone.

### 4. Stable chat and confirmation operations

- Fill the visible `textarea`, then click the button named `发送消息`.
- Start a fresh scenario with the button named `新建会话`; preserve same-session chains such as B02 -> B02-NEG and IC-B03 -> IC-B04-REUSE -> IC-B04-CHANGE.
- Select clarification options by their visible radio label and click `提交`. Use `跳过` only where the matrix explicitly requires it.
- Observe completion through a scenario-specific final sentence, clarification card, or fail-closed notice, then confirm `run_state.json` or the existing task/session API before starting the next session. `思考中...` can disappear while a tool is still running, so its disappearance alone is not a completion signal. Visible and hidden copies of text can coexist, so do not depend on an exact-text locator that requires a single match.

### 5. Execute and evaluate the matrix consistently

- Run the whole frozen matrix in order. For ordinary scenario failures, record the session ID and evidence and continue; diagnose and repair only after the batch finishes.
- Preserve the established multi-turn browser sequences: B04 uses its frozen initial prompt followed in the same session by `【B04】继续第2步` through `【B04】继续第13步`; B03 and CONTENT-B03 send `好的，继续。` in the same session before using the compression dialog, because a single short turn is intentionally not compressible.
- Stop a dependent path only for session/data isolation failure, incomplete event transport, evidence-level escalation, or whole-service unavailability.
- Do not locally rerun only a failed scenario and present it as an uninterrupted complete batch. A separately frozen and authorized supplement may cover only an unfinished scenario when the earlier scenarios have intact, independently reviewable receipts and the interruption is an explicit Provider call cap. Record the two result identities and the supplement boundary; a code or route change affecting product behavior still needs the relevant complete batch again.
- At the end, inspect browser console warnings/errors, refresh the required sessions, verify exports and persisted state, check unique terminal events, and reconcile the runtime trace.
- Local scripted-browser evidence is not real-Provider, staging, production, or deployment evidence. A real-Provider batch requires a newly frozen exact commit, model, endpoint, fixture/prompt/oracle digest, matrix, budget, ledger path, and new explicit user authorization.

### 6. Preserve evidence and repository state

- Record the service PID, port, run directory, session IDs, stdout/stderr paths, matrix results, and Provider initiated call count in the existing implementation/audit record.
- Do not add a new browser test framework, model-review call, probe family, or duplicate ledger mechanism.
- Preserve unrelated dirty or untracked user files. Stage only named files and never reset or bulk-stage the worktree.

## P08 HTTP-controlled matrix when browser automation is unusable

The user authorized changing the control path on 2026-09-26 after confirming
that manual upload works while automated clicks missed the control. Do not call
this a product upload failure. A Provider-disabled local probe of the existing
`/api/upload` → `/api/chat` → SSE → persisted session path completed with one
terminal event and zero Provider calls in `tmp/phase9-http-probe-20260926-r1`.

- Keep the existing `run_p08_real_matrix.py` isolated service and authoritative
  `provider-calls.jsonl` ledger. The frozen contract must identify
  `control_route=local_http_api` and include the HTTP driver's digest. Freeze a
  new HEAD, launcher/driver/contract, model, endpoint, fixtures, all M01–M06
  prompts/oracles, a finite call cap and ledger path. Obtain explicit authorization
  for that exact batch; the earlier browser-protocol r2 freeze is invalid for
  this route. No real call may precede that authorization.
- Use only `scripts/testing/run_p08_http_matrix.py` against the existing local
  app endpoints. The driver posts frozen files to `/api/upload`, checks returned
  filename and SHA256, passes those tickets to `/api/chat`, consumes SSE, checks
  the single terminal against durable run state, and records session IDs. M04
  uploads v1 and v2 in the frozen order within one session. M06 resumes only
  the frozen business option. Do not silently retry a partial batch.
- Run the whole matrix in order. Continue ordinary scenario failures; stop for
  event/session isolation, Provider/accounting, or whole-service failures. Keep
  the Provider ledger separate from HTTP control evidence. At the end reconcile
  started/dispatched/failed counts, persisted sessions, exports and actual
  Provider calls.
- This route tests real model behavior through the normal app/AgentLoop/tools,
  upload ticket binding, SSE and persistence. It does **not** test whether an
  automated or human click opens the upload picker, visual claim rendering, or
  a browser refresh. Mark those UI oracles `unassessed`; do not report full
  browser E4 or Phase 5–8 exit from this batch alone. The user-confirmed manual
  upload is context, not an auditable matrix receipt.

### Call-cap supplement after an otherwise intact matrix

If a frozen matrix reaches its explicit Provider call cap during its final
scenario, keep the original freeze, ledger, sessions and failure record
immutable. A user-authorized supplement may run only that unfinished scenario
through the same app path, with its own fresh directory, freeze, finite cap,
ledger and exact authorization. Freeze the prior freeze, ledger and HTTP result
digests and the scenario scope; verify that the old ledger ended at the cap and
the failed session has no resumable confirmation. Keep the original scenario
fixtures, prompts and oracles. An already failed turn starts in a fresh isolated
session; never mutate its old run state or restart an old ledger counter.

Report a composite assessment as two labelled result identities. Previously
completed scenarios may retain their receipts, but the supplement cannot turn
the original atomic batch into a pass or assess its visual oracles. If product
code, model, endpoint, fixture, prompt, oracle or control route changes, do not
splice results; run the relevant complete matrix on one new identity. Diagnose
any ordinary semantic failures separately from this cost-saving supplement.
