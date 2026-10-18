# P5 修复后完整真实批次准备收据

日期：2026-10-09。实施树为 C trust-rebuild，分支 `codex/trust-rebuild-20260927`；D 供体 `b181646` 仅读。阶段状态仍只在[唯一总计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)维护。本文件记录准备边界，不是新计划或真实通过收据。

## 1. 修复与本地出口

修复及逐项责任审查见[批后修复](2026-10-08-p5-repair-implementation.md)，原需求诊断见[诊断](2026-10-08-p5-requirements-diagnosis.md)。本次将已验证的39个命名在途文件连同本准备收据保存为本地候选提交；精确提交号取新冻结 `source_commit`，不以旧882df1c标记新源码。

完整离线 `tmp/p5-repair-full-20261008-r6` 为 **3427 passed / 2 skipped / 17 warnings**，421.79秒。401个源/测试文件清单 SHA256 `f279f9ff12f99765fdd2ab927bc063f14c758efd353c283af05b39673f3aeebd`；JUnit SHA256 `3cdb0c61be594ec728f128f7e7a2ec2438f85b4a060a84015fabbfb2fe96cd08`。两项skip仍为未授权live smoke及Windows symlink；未改为通过。

正常app Provider禁用 HTTP `tmp/p5-repair-local-http-20261008-r5` 为 **47组/90回合，检查0失败，实际Provider0**；原案例、独立数值oracle、SSE终态、持久状态、压缩和导出核对保留。服务exec17937/PID2084及8781已关闭；重启检查两端口8780/8781无监听。固定协议输入不证明自然生成/审核质量。HTTP picker、视觉、浏览器刷新及console未评估。

提交前再次精确核对401个文件和791份原批材料；保护39文件原字节、命名清单及补丁于 `tmp/p5-candidate-preparation-20261009-r1`。本地通过源与新候选的逐文件字节关系在该目录记录，无代码修改时无需以新提交元数据为由重复完整回归。

架构继续采用一次意图、结构化原文目标、Workspace版本权威、既有确认与一次局部审核；合并核心及所有替代helpers相对P4净增576行，相对重建前净减4931行。没有新散文词表、平行发布路径、兼容wrapper、调度器、探针族或账本。

## 2. 新批次精确冻结提案

| 项目 | 内容 |
| --- | --- |
| 新结果目录 | `tmp/p5-real-20261009-r1`，零调用准备前确认不存在 |
| 路线 | `local_http_api`；原 `run_p08_real_matrix.py` 隔离服务与 `run_p08_http_matrix.py`，正常app/AgentLoop/上传票据/SSE/持久化/导出 |
| 范围 | 完整M01—M06，原6会话、13CSV、20提示及3次冻结业务恢复；原合同SHA `e7b8e274e64869ffd15c6f1b0c0429669aef0662ddfedc51b90b70b5b44537f9` |
| 预期模型/端点 | `openai/deepseek-flash` / `https://api.deepseek.com`；以新freeze中的实际非秘密配置重新核对 |
| 调用预算 | 最多180次物理调用，包含主、辅助、流式和既有一次审核；每次最多65,536输出token，可用原较小辅助预算 |
| 账本 | `tmp/p5-real-20261009-r1/provider-calls.jsonl`，预检时不得存在 |
| 隔离 | 新空workspace/sessions，MCP与skill自动发现关闭，one_shot，bounded_once |
| 精确身份 | 新候选、原始字节源及ignored运行资源、运行环境、非秘密配置、launcher/driver、计划、CSV/全部提示/确认/oracle、预算及账本路径 |
| 停止 | 首次Provider/流/记账或身份隔离/事件/全服务失败即停止；不重试、fallback、复用原批或局部拼接通过 |

凭据仍仅在进程内由既有 `D:/Project/Daily/data-agent/tmp/p5_frozen_launcher_env_20261008.py` 从D `.env`导入MODEL_ID/API_BASE/API_KEY；不打印或复制凭据，不修改D配置。辅助文件摘要写入预检收据。提案端口8780，预检不启动服务或网络。

新freeze的完整原始字节SHA和候选号在零调用收据记录。原批未触顶且六场景失败，不适用call-cap supplement。M04保留同会话先v1后v2，M06只恢复冻结业务选择；普通内容失败按原矩阵继续，未冻结确认停止该依赖路径并保留材料。实际上下文、响应/流chunk及请求/响应SHA沿用唯一Provider账本和原捕获机制。

## 3. 独立评估与授权

M01咨询、真实值与未来AND行动；M02原精度/未确认尺度/外推边界；M03六来源无跨源总额及真实压缩保留原答案；M04当前版本竞争假设；M05六种表达需求；M06缺口/业务口径/同版复用及换版重确认，均按原VP/IC/CP与现有完整合同评估。结构化claim是事实权威，开放内容按整篇事实及局部解释核对。不得用随机措辞解析、数字子串或旧散文扫描签收自然质量；不增加付费judge。

用户最新继续实施及调用授权已收到，候选保存和零调用准备继续执行。本树 `AGENTS.md` 仍要求新批次精确冻结身份的明确授权；冻结完成后仅提交具体候选/完整SHA/模型端点/180预算/账本问题。此前882df1c批次及ddb9daa/71e23d0授权不续用。正式默认、部署和外部Git分别授权。本收据生成时新增Provider为0，P5修复后的自然质量尚未评估。


## 4. 合同调整后第二完整批次准备（2026-10-09，r2）

用户已批准需求—执行—发布合同调整及原材料零调用重放。本节追加新的准备身份，前述r1候选/授权/132调用失败收据保留；r1已关闭，不能续跑。唯一状态入口仍为总计划§0.5。

本次命名保存34项在途文件及本准备收据，备份、原始字节与patch位于 `tmp/p5-candidate-preparation-20261009-r2`。候选号以新freeze的source_commit为准。本次只保存本地提交。保存前重新逐字节核对404份完整源/测试资产与最终本地出口一致；原两真实批次823/791份封存材料全部一致。完整离线r3为3470 passed/2 skipped/17 warnings；正常app HTTP r3为47组/90回合、检查0失败、Provider0。Git保存后再次核对这些字节，保存元数据不替代测试。

新结果目录为 `tmp/p5-real-20261009-r2`，路线 `local_http_api`，沿用原launcher/HTTP driver/合同和13 CSV、20原提示、3项冻结业务恢复以及独立oracle。完整M01—M06，不是补充批次。提案端口8780；最多180次物理Provider调用，每次最多65,536输出token；包含主、辅助、流式和既有一次局部审核。模型 `openai/deepseek-flash`，端点 `https://api.deepseek.com`；精确非秘密配置、运行环境、source_inventory、当前矩阵计划、launcher/driver、提示/oracle、预算和账本均由现有预检冻结。凭据仍仅经既有D环境辅助入口在进程内读取，不输出或复制。

生产源码沿用已验收合同，较3e079b7净增254行、loop净0；本次准备不改生产源码、工具、测试或验收oracle。真实验收继续核对咨询、多轮目标等价复用和独立目标覆盖、当前版本/确认/血缘、竞争假设实际测量关系、完整专业交付以及一次局部审核。原M04其余三假设缺口不等于竞争解释完成；原M03重放预算成功不等于自然审核通过。结构化claim保持事实权威，不增加模型散文词表解析、付费judge或平行路径。

账本 `tmp/p5-real-20261009-r2/provider-calls.jsonl`；零调用预检后仍不得存在账本、会话或Provider请求。首次Provider/流/记账、事件/隔离或全服务失败即停止，不重试或fallback；普通语义失败按完整矩阵继续，不在批中修复。完整新freeze通过后，依AGENTS.md请求一次绑定候选/完整SHA的精确授权。用户泛化调用授权不冒充新身份授权。picker、视觉、浏览器刷新和console在HTTP路线仍unassessed，P5自然质量尚未签收；正式默认及外部Git/部署另授权。


## 5. 架构重构后完整自然批次准备（2026-10-09，r3）

用户要求继续实施并授权必要调用；本树AGENTS要求精确冻结身份授权，因此先完成可审查候选和零调用准备。唯一计划§0.7 D1—D4已完成本地出口，D5进入准备；本节不是自然测试通过收据。

本地出口为arc-final-full-r3的3530通过/2跳过/17警告，以及arc-final-http-r3的47组90回合检查0失败、90唯一SSE/持久终态和Provider0。408项运行资产逐字节与原收据一致，三批2348份历史材料再次完整核验。原收据tmp/arc-final-r1/final-receipt.json SHA256为62c20c6603700943068e06570f7a54b4f870f16be1de8c36f0dea308bbc6ef33。当前生产代码较本轮保护基线净减884行、较旧HEAD净减609行；有界多输入和Python参数声明按已批准设计实施，不以声明证明方法正确。原2729个测试函数和77个工具名保留。

保存范围为已审查的94个在途文件，加本准备记录；逐文件原字节、patch和命名清单保留于tmp/p5-candidate-preparation-20261009-r3。只作本地候选提交，保存后复核408资产原字节，不借提交元数据重复无变化的完整回归。供体D main/b181646只读。

新批次tmp/p5-real-20261009-r3，采用既有run_p08_real_matrix.py及run_p08_http_matrix.py，路线local_http_api，正常app/AgentLoop/工具/上传票据/SSE/持久化/导出。复用完整M01—M06原13CSV、20提示和3次冻结业务恢复以及原独立oracle；逐项对照上一批scenario_inputs、fixtures、合同和driver摘要。没有添加模型散文词表、付费judge、兼容路径或平行账本。

提案模型openai/deepseek-flash，端点https://api.deepseek.com；最多180次物理调用，包含主/辅助/流及既有一次审核，每次最多65536输出token。空隔离workspace/sessions，MCP/skill自动发现关闭，one_shot、bounded_once；端口8780。账本tmp/p5-real-20261009-r3/provider-calls.jsonl。旧批次132/111及最早133调用结论保持失败，余额恢复尚未经网络验证，不调用余额探针。既有D环境辅助入口仅在进程内导入MODEL_ID/API_BASE/API_KEY；摘要记入预检，不打印或复制凭据。

首次Provider/流/记账、隔离/事件/全服务失败立即停止，不重试、fallback、续跑或部分拼接。普通语义失败完整记录后继续矩阵，批中不修源码、提示或oracle。M04同会话v1后v2，M06只提交冻结业务选项。以结构化claim/真实回执证明事实，以原需求人工评估完整业务交付、合理解释和风格，不用数字子串或随机措辞扫描签收。HTTP路线的picker/视觉/浏览器刷新/console仍unassessed；正式默认、部署、外部Git分别授权。

精确source_commit、freeze原字节SHA、环境与helper摘要、原输入同一性和调用0证明，在本次preflight-receipt.json中生成。原批次授权已关闭；新freeze通过后依AGENTS绑定新身份请求授权。本次准备不启动服务或网络，若预检失败则不得继续调用。
