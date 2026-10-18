# 可信重构候选接回main

日期：2026-10-19。状态：文件接管完成，本地提交和新的完整离线回归待完成。唯一现行计划为总计划；本页仅记接管身份、保全及验证。用户明确授权本地提交和完整离线回归，不推送、不启用Provider、不进入S5。

## 来源与接管

当前实施根D:/Project/Daily/data-agent，分支main。来源是C:/Users/duguy/.codex/worktrees/trust-rebuild/data-agent完整工作区：codex/trust-rebuild-20260927，HEAD f7210e170d4dd1945abec15d57e364e04942eae4，加全部在途实现；不只HEAD。C原228项dirty/untracked、HEAD和索引c5d7162d88d68139842eca5717fc5ad3bb6f59126aeade8aa5bac01042d653c3保持。

678项物料为627个已跟踪文件当前字节＋50个未跟踪文件＋明确的Plotly忽略资源。全部先按C逐字节核同，随后仅更新当前计划/验收头部/审计状态。426文件摘要dc78093b1264a060d9ddb51726f3fd9f914b08c513670fc63b3366980ad41ded保持；407项launcher清单与426交集402、并集431。具名清单artifacts/mt02/candidate-materials.json，源码身份source426.json，旧23文件不在主线活动树中。

main旧HEAD b181646ff66ea9ea3b0e6a38ffcd3d16b6687312保留为接管提交父历史。不重置或强推，不把81个旧拓扑独有提交当新开发再次混入。23旧文件的Git对象原文保存在artifacts/mt02/old-main23-Git-blobs，并继续存在旧Git历史；不恢复旧散文门、Shadow/typed-trial入口或旧私有依赖测试。

## 保全及用户清理事件

最初tmp/mt01中的D六项原件、索引、patch及569项受控前像已真实保存并核验；之后用户确认“刚清理过tmp”“永久删除／清理命令”，该目录及D历史tmp材料不可见。不得声称最初备份仍在或全部D历史tmp已恢复。

D六项材料现已恢复到artifacts/mt02/D6-recovered并全部匹配清理前独立记录SHA：四项来自C逐字节同原件，一份来自既有Git blob 2478d16f265373a441a10631e6cdaa3addacf382，另一份按此前只读diff的唯一M03行逆转重建，仍匹配原SHA和字节数。来源及校验见D6-recovery.json；原索引当前仍与清理前SHA一致。旧23文件按Git原文保全，不冒称工作区换行前像。

D历史tmp无法完整恢复的缺口保持unassessed。用户明确回复“保留历史清理缺口，继续提交和回归”，见cleanup-incident-accepted.json；这是本轮新增具名缺口，不删除旧失败、不伪造原件。C的S4收据、1249受保护原件和15历史答案已核完整。既有D会话、workspace、reference及其他未列入接管清单的内容不清理、不镜像覆盖。后续保全和运行日志存artifacts/mt02。

## 环境与完整回归

保留D已有Python 3.14.0和D专用虚拟环境，包导入指向D/src；从本机uv缓存以offline模式补齐C已有pytest-asyncio 1.3.0，没有网络下载或依赖升级，D原pip保留。实际.env不改写；仅离线测试子进程固定MODEL_ID=gpt-4o、API_BASE回环拒绝端口、Provider网络0、MCP false、自动发现false。

9份reference/test_doc XLSX已核原SHA，与C一致，无需覆盖。既有31证据变量重定向到全新artifacts/mt02/e00—e30；官方run_regression.py full-offline使用全新短目录tmp/mf1。日志、进程、环境、源码和终局收据保存在artifacts/mt02，JUnit结束后复制到保全目录。新的完整回归待完成；不以C的7953/0/2代签，不删原7955节点或新加skip，不重开105退役审核。

## 证据与后续边界

C原S4 7953/0/2、47/90、52/52、13/13及m07/m08实际视觉按原身份留存；主线只核本批静态/完整离线运行，不冒称新浏览器、真实Provider、部署或进程冷重启。新导出不继承旧精确MD的人工确认。

原180仍118完整/62局部/0待审，不是完成率。F5缺原件ddb9daa/71e23d0、45项自然内容/语义、2项自然方法、Windows符号链接能力、整体自然门及51分钟性能问题保留，A/B/C未批准未实施。原C的p04保持历史原件且不可执行；main将来清洁提交不等于模型/端点/输出上限/物理预算获批准，全部Provider和远端MCP调用0，不推送、不进入S5、不继承历史授权。
