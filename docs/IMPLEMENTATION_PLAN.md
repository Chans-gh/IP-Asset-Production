# Codex 分阶段实施计划

> 原则：每个里程碑独立开分支、独立验收、产出测试日志；在 M2 前不得声称完整可用。

## M0 — 规范固化与仓库基础

- 初始化 src/、pyproject.toml、测试、lint/type-check、GitHub Actions。
- 校验 41 个 legacy_id 唯一、NEW-01..14 唯一、APP-01..10 唯一，且每项都有关联 Prompt。
- 从 `schemas/` 生成/校验类型合同；创建无网络 mock fixture。
- 实现 `CapabilityRegistry`、`ImageProvider` 抽象协议与 `MockProvider`，严禁真实 API 默认开启。
- **验收**：规范静态校验、所有 Schema 解析、离线 smoke test、secret scan 无错误。
- **状态**：本地完成，验收记录见 `CHANGELOG.md`；待推送远端后由 GitHub Actions 复核。

## M1 — 创建入口、角色档案、风格库骨架与规划器

- Intent router 支持 3 种输入模式；多图 reference_manifest 可设置用途和冲突优先级。
- 建立 `styles/` 目录骨架、taxonomy/catalog/compatibility 数据结构，以及风格推荐接口。
- 完成风格确认 `G2`、定妆批准 `G3`、资产计划批准 `G4` 的状态机。
- 13 类目录适配 `ip_type/topology/capabilities`，编排 P0/P1/P2 DAG 与复用缓存。
- **验收**：T01/T02/T03/T04/T05/T17/T18/T19/T20；支持保存、重载角色和计划。


## M1A — 风格数据与预览任务准备（无需真实 Provider）

- 验证固定 **48 个风格预设**及分类、Prompt 和适用对象；准备 `styles/preview_manifest.json` 和待执行样例 Prompt JSONL，不在该阶段伪称已生成真实图像。
- 实现并测试 `docs/STYLE_LIBRARY_AND_PREVIEWS.md` 的样例任务生成、QA 字段、以及按适用对象筛选。
- 实现风格候选筛选与本地 HTML 画廊骨架；正式画廊只展示 approved 样例，不展示计划中的占位图。
- 用户确认风格后，保存 `style_id`、`style_profile` 与预览引用。
- **验收**：T21/T22/T23/T24/T25，48 条数据均可编译任务；样例未生成时显示清晰的缺失状态。

## M2 — 可插拔生成 Provider、图像后处理与 QA

- 选择**一种**明确可授权的真实图像 Provider；根据实际能力适配 API，切勿伪造支持项。
- 先单视角再拼板、透明 alpha / 尺寸检查、可选超分、英文/中文文本叠加。
- 任务队列/有限重试/结果 manifest/可恢复任务；自动 hard checks + soft QA/manual review。
- **验收**：T08/T09/T10/T11/T12/T13；至少 3 类独立真实基础资产正确导出。

## M2A — 48 种真实风格样例生成、审核与画廊（v1 必交付）

- 依赖 M2 已接入的真实图像 Provider；逐条执行 `styles/preview_manifest.json` 中规划的样例任务。
- 最低每个风格 1 张：**48 张真实合格的样例**；同一角色原型对比时尽量稳定构图与基础形体。
- 审核可用性、风格差异、实际像素、文件有效性和公开分发权限；不合格可有限次重试，失败必须保留状态。
- 从 `approved` 样例构建本地 HTML 风格画廊，并支持选择 style_id、筛选类型/家族/关键词。
- 在两个宿主中优先以图片消息展示；若宿主不支持交互，用本地 HTML 画廊及编号反馈作为降级。
- **验收**：T20/T21/T22/T23/T26/T27/T28/T29。

## M3 — 直接可用应用成品

- 优先 APP-01 表情包、APP-02 会议室门牌：单图数量、文字、打印 trim/bleed、PDF、manifest。
- 再扩展 APP-03..10；各应用指定交付模板、正确规格和渠道可替换配置。
- **验收**：T06/T07；同一角色两组应用包可独立交付。

## M4 — DeepSeek Harness 集成

- 使用官方发现根目录与 `SKILL.md` 格式，验证 provider 启用和加载。
- 验证实际工具访问、脚本权限、资源定位、用户工作区输出路径。
- **验收**：T14 + 真实版次、配置文件、成功任务日志；失败也记录具体限制。

## M5 — WorkBuddy 集成

- 先做官方技能包导入 Spike：确认可接受包结构、是否 ZIP、脚本运行权限、网络权限、传图授权。
- 将已验证机制封装进 HostAdapter 与打包脚本。
- **验收**：T15 + 实际 WorkBuddy 版本、安装/执行/导出结果；不要仅用“导入成功”代表端到端成功。

## M6 — 安全、发行、维护

- 文档、升级路径、变更日志、Semantic Versioning；安全/隐私/CI 失败检测。
- 授权确认后建立公开 GitHub 仓库，正式 Release 添加安装说明与安装产物 hash。
- **验收**：T16、所有回归测试、两个宿主各有真实端到端记录。

## Codex 分工指令（按阶段逐步下发）

1. `只执行 M0，先列计划和目录变更，再实现，跑离线测试；发现需求冲突写 ADR。`
2. `执行 M1/M1A：实现路由、风格筛选、48 风格数据验证与预览任务清单；不伪称已有真实样例。`
3. `先执行 M2 接入一个真实 Provider，随后执行 M2A 批量生成至少 48 张经审核样例和 HTML 画廊；记录生成能力与实际规格。`
4. `只执行 M3，先做 APP-01 与 APP-02，严格验像素与印刷。`
5. `只执行 M4/M5，必须宿主实测，再做兼容声明。`
6. `执行 M6，检查仓库发布安全、安装包和说明，不擅自发布用户私有素材。`
