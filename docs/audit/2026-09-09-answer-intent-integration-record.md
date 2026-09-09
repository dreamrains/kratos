# 回答内容优化与必要澄清整合记录

日期：2026-09-09｜整合分支：`codex/answer-intent-local-acceptance-20260909`｜基线：`d6e478005b4b7d375a99e6e3c278b5c31e3abc75`

## 1. 范围与分支

- 在独立 worktree 中从 `vp-analysis-value@d6e4780` 建立整合分支；原 dirty 主工作树未被清理、覆盖、reset 或批量暂存。
- 按顺序 cherry-pick 回答内容优化提交 `61e7b47`、`bd42678`，生成整合提交 `1cd415e`、`5446e1a`。
- 复用既有浏览器演练入口扩展提交 `0eb3111`，生成 `e494261`；未新增测试框架、探针、模型审核调用或重复记录机制。
- Git 未产生文本冲突；整合树与先前同基线的两提交整合结果逐字节一致。`loop.py` 与 `tests/test_execution_control.py` 仍按函数和回归检查确认两侧契约并存。

## 2. 关键不变量核对

- 必要澄清：只有范围绑定的业务语义缺口才悬挂；方法许可降级为非阻塞响应；已解决决定按业务范围复用，范围或相关数据版本变化后重新判断。
- 工具协议：续传序列化保留 `assistant.tool_calls` 与 `tool.tool_call_id`；Provider 投递副本剔除孤立消息并在发送前校验完整块。
- 发布闭环：质量门前候选仅以 `publication_rejected` 内部保存；正式正文在发布包、来源 artifact、回复级 binding 和 session 保存成功后公开。
- 失败与终态：artifact/session 写入失败回滚本轮公开消息和 packet；同步与流式路径复用同一最终化入口，保持一次终态。
- 内容完整性：FactGroup、detail_ref、需求生命周期、`answered` / `not_computed` / `evidence_insufficient` 和类型化派生量值契约均保留。
- 证据边界：竞争假设的支持、反证、冲突、未决和失效状态继续由结构化关系、范围和数据版本约束；没有放宽因果、预测或零值解释门槛。

## 3. 本地测试证据

| 范围 | 结果 | 证据边界 |
|---|---|---|
| 回答内容定向 | 129 passed | E1/E2；Provider 禁用 |
| 必要澄清与意图定向 | 301 passed | E1/E2；Provider 禁用 |
| full-offline 第一次 | 2492 passed、56 failed、62 skipped | 失败集中于独立 worktree 缺 Git 忽略 Excel 夹具和 Windows 长路径；整套已跑完 |
| full-offline 第二次 | 2608 passed、1 failed、1 skipped | 缩短 worktree、补齐夹具后唯一失败为多复制了清单外 `游戏C改版.xlsx`；用户接受当前结果用于合并，不记作 full-offline 全绿 |

隔离运行目录分别为 `tmp/integration-20260909-target-content`、`tmp/integration-20260909-target-intent`、`tmp/integration-20260909-full-offline` 和 `tmp/f1`。runner 设置 loopback API、禁用真实 Provider 网络；本阶段没有发起真实 Provider 调用。

## 4. 未完成项

- IC4：合并后 `main` 上的 B01—B06、IC-B01—IC-B06、CONTENT-B03/B07 浏览器矩阵未执行。
- IC5 / AC40：真实 Provider 未冻结、未授权、未执行；历史授权和旧账本不得复用。
- 未 push、未部署。后续以合并后的 `main` 提交重新核对源码与运行身份。
