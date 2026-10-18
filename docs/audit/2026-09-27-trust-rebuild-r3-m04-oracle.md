# R3.3 M04：同版本关系、版本失效与当前观察

日期：2026-09-27。重建树 `codex/trust-rebuild-20260927`，起点 `d0a2614`，本切片实施前 `634ae98`；供体固定 `main@b181646`，未在供体追加产品补丁。此处是 Provider 禁用的正常 app `/api/upload` → `/api/chat` → SSE → 会话/导出 HTTP 路线，不是可视浏览器、真实 Provider、正式 P08 或默认发布策略验收。

## 独立判据与控制身份

- v1 `F-HYP.csv` 三行，2026-09-01/02/03 的 `amount` 为 10/20/20；首两日差额 +10，后两日差额 0。v2 `F-HYP-FLAT.csv` 同日期为 10/10/10；新版本首两日差额 0。单位未授权，不能称因果或统计显著。
- 第一轮必须从持久假设集读取真实 ID；支持与反证提议各绑定一个当前原始 `compare_periods` detail receipt，由宿主复核 metric、delta、方向、plan、dataset 和版本。第一个主假设在 v1 应为 `contested`，其余仍可未决。
- 同一会话上传 v2 后，v1 的有效关系必须失效且记录保留；当前 v2 数值独立交付。每轮唯一 SSE 终态，落盘及导出正文一致，真实 Provider initiated calls 0。
- 路线 `local_http_api`；控制器为忽略目录 `tmp/r3_m04_http_probe.py`，最终 SHA-256 `B3F885F5B7C13CE790281A02877F02A6E48159EBB0F055455318A11DF943D70B`。只使用现有 Provider 禁用 `run_p7_browser_rehearsal.py` 服务，最终脚本 SHA-256 `5675601C322FD7FC86D4331859D4EFB99A5384CEDF5909F0EFC53D42DF636EA0`。端口 5234，每批均新目录、健康响应 `ok=true/provider_enabled=false`、会话独立。

## 批次与设计裁决

| 批次 | 身份与实际结果 |
| --- | --- |
| A | `tmp/r3m04a`，PID 15488、exec 34760、会话 `bfa91a9d9692`。13 轮单会话，但旧 scripted transport 将提议拆到不同 plan，v2 重载后未比较。两个都不能作为 M04 通过证据。 |
| B | `tmp/r3m04b`，PID 18144、exec 98602、会话 `1a53039180ca`。v1 同轮提议、v2 10→10 当前观察；支持提议自动绑定多个同名回执而无法唯一复核，旧计划状态未随版本失效。 |
| C | `tmp/r3m04c`，PID 14608、exec 32906、会话 `a76c009db32f`。提议显式绑定真实单回执；旧版三条证据获 `data_version_changed` 排除，但多次刷新后旧假设由 `stale` 回到 `inconclusive`。 |
| D | `tmp/r3m04d`，PID 20296、exec 30070、会话 `4fa83d2d9057`。修订既有假设状态机后，旧主假设在 13 轮末维持 `stale`；v2 10→10，零 Provider。 |
| E | `tmp/r3m04e`，PID 25208、exec 30702、会话 `cd9636ac98d1`。控制器逐轮快照证明第 1 轮主假设有两条不同原始回执 `tr_088e06863bc9` / `tr_838f0e737e6e` 验证的 `supports` / `refutes`，状态 `contested`；第 2—13 轮旧主假设持续 `stale`，三条旧证据均带 `data_version_changed` 排除，新计划没有继承其关系。 |
| F | `tmp/r3m04f`，PID 1972、exec 78938、会话 `31f64d59501f`。同 plan 异 route 失效范围修正后的**最终代码身份**完整复跑：首轮主假设两条宿主验证关系分别绑定 `tr_ba05a9da219d` / `tr_428bdbd1c062`，状态 `contested`；其后 12 轮均 `stale`，旧证据 3 条排除，v2 10→10、差额 0、两期各 1 行。每轮单一 `turn_end`，末轮正文与持久态相等且包含于导出，票据 SHA 一致，Provider 0。结果 JSON SHA-256 `fd336fe6d83b6e4b4c1bea6a6249e20be13abefb3d36e64d3c853c8b3ae8ccde`。 |

B/C 为同一历史假设刷新根因的两轮未收敛，随后作状态机设计裁决：旧计划的已判定假设在当前数据版本失去全部同计划证据时转 `stale`；无新同计划证据的重复刷新保持 `stale`，若有新有效证据再按关系重算。刷新范围是同数据集所有受旧版证据影响的集合（包括同 plan 的其他 route），当前正在重算的同一集合只处理一次。实现在现有 `trust_workflow_runtime.maybe_create_hypothesis_set` 的历史集刷新和 `hypotheses.update_hypotheses_from_evidence` 状态转移，不增 planner、账本或关系事实通道。scripted transport 只提供真实单 receipt ID 和当前版工具调用，不替宿主决定关系。

E 的两个上传票据 SHA-256 分别为 `f4e08a4807168b1c0adea09ed4caeaa31661571bc3baa6460a7ef7c4a87d29b4`、`397e67926b263a70188e4730208575a1e6c4567f5e93a2cb084c8e9da17dfea0`，与文件一致。13/13 轮均一 `turn_end`；末轮 SSE 正文等于持久 assistant 正文，导出包含同一正文。E 结果文件 SHA-256 `acf5af5cdedc296790d45430715849448adbdfb958f5ca412a8a2a3c2040a52f`；导出 SHA-256 `f425acb3f6e9e618cf6a858fa290d8174ee09ad688a71bc9fe78a86f735835a7`。A—F 六批 `runtime.jsonl` 均无 `forbidden_provider_transport`，真实 Provider initiated calls 0；服务均已按保留 exec session 停止。

## 验证边界与后续

定向 `test_trust_workflow_runtime.py`、`test_hypotheses.py`、`test_analysis_quality_guard_scope.py` 为 68 passed；新增跨计划、同 plan 异 route 版本替换及重复刷新反例。首轮 full-offline `tmp/r3m04fo` 为 2889 passed / 1 skipped（JUnit SHA-256 `44BCEE59E6AF1BB47A7EA5D64EE0652D706EDDAD1E4374A50730866CE101A859`）；随后修正同 plan 异 route 刷新范围。**最终代码**的 `tmp/r3m04fo2` 为 2890 passed / 1 skipped / 16 warnings / 0 failed，JUnit SHA-256 `09D651B5B23BD824CF4A5709D413AFEB444A2C3DDF6E50DBCCDDEFBCF07688E8`，runner `provider_calls=forbidden`，实际真实 Provider initiated 0。F 是此最终代码的 app 收据。

此演练把 v1 的工具链放在同一分析轮，避免脚本逐轮创建新 plan；这不证明自然模型或任意跨轮提议会正确保留计划身份。当前每条 B04 续问仍生成新 plan；真实业务的跨轮续做语义需要单独的结构决策。E 只证明 v1 的一个描述性假设有冲突关系，另外三个仍未决；不声称因果假设得到支持，也不把 HTTP 证据升级为可视 E3/E4。正式两轮 P08 M04、完整矩阵、浏览器刷新及新真实 Provider 均未执行，后者需新精确冻结和授权。

## 后续正文闭环：G（同一发布绑定路径）

`2242f14` 完成版本关系切片后，发现 v1 首轮三个 `compare_periods` 回执与三个 `record_evidence_record` 回执共同进入正常 publication packet，原 comparison builder 因辅助证据来源存在而不构造 `answer_bindings.v1`；结果用户只看到模型说“已记录反证”，看不到已核的原值。这不满足保留独立正确观察的要求。

在既有 `build_comparison_host_claims` 允许 `record_evidence_record` 作为辅助来源，只把 `compare_periods` 作为观测 block；相同 dataset、version、fingerprint、structured-result SHA 的重复执行只渲染一次。其他工具混入仍不走该 builder；损坏的一个比较回执只影响自身，不吞独立结果。AgentLoop 继续使用同一 `answer_bindings.v1` 渲染、验证、持久化流程，不另建字段权威或发布路径。

G 批次 `tmp/r3m04g`：Provider 禁用服务端口 5234，PID 16948、exec 5267；控制器仍为上述 SHA-256，13 轮同会话 `a3faa9973743`，各轮唯一 `turn_end`。首轮宿主正文恰有两段 `observed_comparison`：2026-09-01→02 `amount 10→20`、差额 10、100%、两期各 1 行；2026-09-02→03 `amount 20→20`、差额 0、0%、两期各 1 行。重复的前一窗口比较没有重复展示；单位保持未确认，仅作描述性比较。首轮同一真实假设的两个回执核验关系仍为 `contested`，此后 12 轮旧主假设持续 `stale`，v2 当前正文 `10→10`。首轮与末轮回复均在 canonical history 及导出中，末轮 SSE 与持久正文相等；两票据 SHA 一致，`forbidden_provider_transport=0`，实际 Provider initiated 0。G 结果 JSON SHA-256 `56147cf9ea11a1b01ae2ae9e5e282226b33c87a5aa74e7dafdc9e43078dcef5b`，导出 SHA-256 `aac7b8c3881a9ae00b0da26774c93a5c8351378ae6533ea867c9a095ddf66742`。

`test_r3_comparison_host_claims.py` 新增混合来源、重复结果去重及无关工具拒绝反例；相关定向 30 passed。此新代码身份的完整离线收据 `tmp/r3m04pubfo` 为 **2891 passed / 1 skipped / 16 warnings / 0 failed**，JUnit SHA-256 `77FD23EEBF891043D57EF852A01F3D88D8624ACB25BE19B61C45AB7B2D21C712`；runner `provider_calls=forbidden`，实际 Provider initiated 0。G 仍为 scripted Provider 禁用 HTTP app 证据；当前短句续问每轮新建 plan 的范围问题归 R3.5 多轮需求与任务身份，不把本批等同自然模型或可视验收。
