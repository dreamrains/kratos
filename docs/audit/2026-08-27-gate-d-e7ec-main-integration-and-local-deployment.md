# Gate D `e7ec4011` 主分支集成、推送与本机部署收据

日期：2026-08-27

## 结论

用户授权提交、合并到主分支、推送并部署后，Route A 本地发布候选已完成候选提交、主分支无覆盖合并、普通快进推送与当前主机 Web 进程部署。部署后真实浏览器烟测通过。

仓库没有 Dockerfile、云平台 manifest、CI/CD workflow、deployment branch、目标主机或 staging / production 凭据；实际 Web 入口也明确使用 Flask development server。因此本收据只证明**当前主机部署**，不把它表述为 staging 或 production 部署。

## Git 集成与历史保护

| 项目 | 结果 |
|---|---|
| 候选源码提交 | `9af4a9aa6cd0bfaae44261fb3b1eb7c2fd9c9481`（`feat: complete route a gate d release candidate`） |
| 主分支 merge commit | `f750a72762c679424a4bc07e41e2c55eae82cdb8`（`merge: route a gate d release candidate`） |
| merge parents | `b162f04ee621cbc12c613aada51f281f83d3e714` + `9af4a9aa6cd0bfaae44261fb3b1eb7c2fd9c9481` |
| 首次推送结果 | `origin/main`：`b162f04… → f750a727…`，普通 fast-forward；无 force push |
| release source digest | `sha256:e7ec4011ecced91664cbb492e7ccf0d1cfe6d13c16ab2facf0a20f165b14f1dc`（346 项） |
| 合并树核对 | `HEAD` 与 `rebuild` tree 完全一致 |
| 旧本地 main 保护 | `codex/main-pre-route-a-20260827` 保留 `e45c1e87…`；同一历史也已存在于 `origin/archive/july-recovery-m2c` |

远端 `main` 在集成前是 `b162f04…` 的“回到 7/13 基线”提交，tree 与共同基线 `1d570617…` 完全一致；本地旧 `main` 则是已被该远端重置替代的恢复线。先保留旧本地引用、再从 `origin/main` 合入 `rebuild`，避免把已替代的 28 个本地提交重新带回主线，也没有删除任何历史。

## 本机部署与真实浏览器烟测

| 项目 | 结果 |
|---|---|
| 部署提交 | `f750a72762c679424a4bc07e41e2c55eae82cdb8` |
| 进程 | PID `13716`，后台运行 |
| URL | `http://127.0.0.1:5001/` |
| HTTP | `200` |
| 页面 | title `Data Agent`；“观澜”、任务输入框、分析工作台均可见 |
| 刷新 | 通过；输入框与工作台刷新后仍可见 |
| browser warning / error | `[]` |
| runtime | 生命周期初始化成功；75 个 native tools 注册 |
| Provider 边界 | 进程固定 `API_BASE=http://127.0.0.1:9`，本烟测没有真实 Provider 调用 |

服务日志位于系统临时目录 `C:\Users\duguy\AppData\Local\Temp\data-agent-main-f750a727-deploy\`。服务仍在运行；本轮没有处理 `artifacts/`、`tmp/`。

## 外部部署边界

当前仓库唯一可执行的部署入口是 `python -m data_agent.web.entry` / `start.bat` / `start.sh`，并且入口日志明确警告它不是 production WSGI server。由于不存在可识别的外部环境、主机、容器、域名或平台配置，本轮无法诚实声称 staging / production 已部署。

如果需要外部部署，后续必须先给出或落地至少一个明确目标及运行合同：目标主机 / 平台、进程管理方式、反向代理与域名、持久化目录、密钥注入方式、健康检查及回滚入口。该工作会产生新的环境级收据；若修改 release source，则同时使当前 digest 的相关源码证据过期。
