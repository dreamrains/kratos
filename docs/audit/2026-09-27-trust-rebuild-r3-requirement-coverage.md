# R3.5 明确需求与来源检索命中的边界

代码基线 `0eb5c36`，目标树 `codex/trust-rebuild-20260927`。控制路线预先选 `local_http_api`；这是 Provider 禁用的正常 app 路径，不是浏览器视觉或真实模型证据。

## 问题与修正

原发布包将问题文本的中文双字检索命中写入 `coverage`，把未命中的字组标为 `missing`，导出收据又逐项写为“未覆盖子问题”；同一词命中还可把 `evidence_coverage` 提升为 `supported`。检索命中只能帮助挑选来源，不能确定用户实际提问身份或证据成立。修正只保留 `_question_terms` 在来源与事实组排序中的作用；发布包中的兼容字段 `coverage` 为空，普通需求的 `evidence_coverage` 和 `context_coverage` 均为 `unassessed`。经过宿主回执验证的确认映射仍可独立写 `supported`。用户可见的需求交付状态从活跃 `answer_requirements` 的 `coverage_check` 与 `answer_coverage` 读取：已校验回答不显示缺口；已校验的未计算或证据不足保留各自状态；未评估和未完成不能被检索命中提升为已回答。正文的逐项验证仍由现有发布门承担，收据状态不替代正文或补救错误结论。

## 验证

- 定向测试：`tests/test_publication_synthesis.py` 与 `tests/test_answer_content_coverage.py`，最终代码 153 passed。测试覆盖检索词不生成子问题或证据成立判断、明确需求身份、未评估与真实缺口状态的导出，以及现有回答覆盖检查。
- 新目录 `tmp/r3m01coverage1`，端口 5234，监听 PID 24616，长时 exec session 62869，结束后通过该 session 停止。入口 `scripts/testing/run_p7_browser_rehearsal.py`；启动前 worktree、`.venv`、入口、空目录和端口均核对。健康返回 `ok=true`、`provider_enabled=false`。
- 固定六轮 M01 HTTP 控制脚本 `tmp/r3_m01_http_probe.py` SHA-256 `CD607059FCFD3C10415E273188B928FD74F45FBCF6FD953EFC747FB7C8EF9BED`；上传 `F-SALES.csv`，票据 SHA-256 `1e6629876a79225fceac0b2dc0f1d16071e532ca989b842c0489afc082f8e59d` 与文件相符。会话 `839c2ea5f92f`，六轮均一个 `turn_end` 且 durable 状态 completed。结果文件 SHA-256 `80CE9DCBE94465929B332C0FBEE7C414AFDC9E15048BE0DB1E2B346FF295D582`。
- 实际导出 Markdown 六轮均保留源表 12 行、派生表 1 行、amount_sum 120、amount_count 12、方法与未知单位；没有“未覆盖子问题”伪缺口。`runtime.jsonl` 无 `forbidden_provider_transport`，实际 Provider initiated calls 0。上传 picker、视觉呈现、刷新均 `unassessed`。
- 发现同根因的 `evidence_coverage=supported` 词面误判后，在同一子项内改为未评估，并用全新目录 `tmp/r3m01coverage2` 重跑同一控制路线/六轮输入。端口 5234，PID 12696，exec session 21164，结束后按该 session 停止；健康仍为 `ok=true/provider_enabled=false`。会话 `532228cb8269` 六轮均单个 `turn_end` 且 durable completed；实际导出六次均有 12/120 表行和方法，伪缺口 0。结果 JSON SHA-256 `CD1C71DB3552ED33183D55E2066ECEFE4A041BBC46917CF7A247C5F69A5730D7`，导出 Markdown SHA-256 `4FFC3D46484AE19A9CF9715AC9CD09DB9CE339DDC77A0F91A3F1DD76E03D053B`。`runtime.jsonl` 禁止传输事件 0，Provider initiated calls 0。第一批只证明改动前半段，不作为最终代码验收。

本子项只纠正需求身份、伪证据状态与导出错误；M01 六种语气仍复用同一宿主正文，条件建议未交付，不能将此批记为 M01 通过。M06 的未算与证据不足分类、跨轮 plan 身份及 R4 解释结构仍待完成。首次完整 E2 `tmp/r3coveragefo` 为 2891 passed / 1 skipped，发生在同根因第二处修正前。最终代码完整 E2 `tmp/r3coveragefo2` 为 2891 passed / 1 skipped / 16 warnings / 0 failed，JUnit SHA-256 `42FBDDA49DCDE68BC35616151BB49611026E2AC73EC237ED710255F811E1C987`，runner `provider_calls=forbidden`，实际 Provider initiated calls 0。
