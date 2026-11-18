# Architecture Decision Log

| ID | 决策 | 状态 | 备注 |
|---|---|---|---|
| ADR-001 | 一份业务核心 + 双 HostAdapter + ProviderAdapter | 暂定 | 减少业务逻辑复制 |
| ADR-002 | 角色类型、形体、风格、用途独立建模 | 确认 | 避免错误人类拓扑套用 |
| ADR-003 | 41 历史记录转换为模板族与变体 | 确认 | 保留 41 条追溯 |
| ADR-004 | 单图先行、组合板后处理 | 部分被 ADR-016 取代 | 支持独立素材与可测分辨率 |
| ADR-005 | 文字与精确数据交由排版 | 暂定 | 中文精确性及印刷要求 |
| ADR-006 | 先 mock 后真实 Provider | 暂定 | CI 可离线执行 |
| ADR-007 | 公共仓库不含用户私有图片/原始 HTML | 默认 | 需用户明确允许才可变更 |
| ADR-008 | 具体服务商、许可证、Git 远端 | 部分确认 | 许可证：Apache-2.0（仓库根目录 `LICENSE`）；Git 远端：`github.com/Chans-gh/IP-Asset-Production`（公开）；真实图片服务商与宿主版本仍待决定 |
| ADR-009 | 风格全集单独建设 | 确认预留 | v1 先具备可扩展 taxonomy |
| ADR-010 | 代码布局：`src/ip_asset_production`，Python ≥ 3.11；运行依赖仅 pydantic / jsonschema / Pillow，开发依赖 pytest / ruff / mypy | 确认（M0） | `schemas/*.json` 是契约唯一来源；Pydantic 模型是运行时实现，`test_schemas_and_models.py` 保证两者字段集一致、导出实例可通过 Schema |
| ADR-011 | Mock 产物隔离 | 确认（M0） | MockProvider 恒为 `data_egress=local`、`is_mock=True`，PNG 内嵌 `ipap:mock=true`；`validate_spec.py` 与 `check_style_release.py` 拒绝把 provider=mock 或带标记的图片计入 48 样例门禁 |
| ADR-012 | 参考图外发默认拒绝 | 确认（M0） | `permission_scope` 缺省为 `private_local`；适配器声明 `data_egress`；external 适配器遇 private 参考图抛 `EgressBlockedError`（T11）；`CapabilityRegistry` 默认拒绝注册 external 适配器，需显式 `allow_external=True`。`data_egress` 暂为适配器属性、未写入 provider-capability schema，M2 接入真实 Provider 时再决定是否入 Schema |
| ADR-013 | v1.2 样例只覆盖 3 个核心原型 | 记录 | `prototypes.json` 定义 4 个原型，但 `preview_manifest.json` 的 138 条 = 48×3 − 6 个不适用组合，不含 FANTASY_PROTO；与 `STYLE_LIBRARY_AND_PREVIEWS.md`“幻想精灵可在下一轮补齐”一致。校验器据此固定核心原型集合，扩展时需同步更新 |
| ADR-014 | 生成结果状态 | 确认（M0） | `generation-result` 使用小写状态，对应 SPEC §9.2；SPEC 的 `DRAFT/APPROVAL_PENDING` 属于计划/请求层（`approval_status`），不进入结果。`passed/exported` 必须带真实文件（模型强制）；M0 的 `execute_once` 只到 `qa_pending`，QA 在 M2 |
| ADR-015 | 公开仓库扫描策略 | 确认（M0） | `scripts/secret_scan.py` 无行内豁免标记；媒体文件只允许位于 `styles/previews/`（且须被 manifest `actual_file` 引用）与 `tests/fixtures/synthetic/`；扫描 tracked + 未忽略的新文件，`--staged` 仅扫暂存区 |
| ADR-016 | 基础组整组一张设定图 | 确认（需求方定） | BASE_VIEW / BASE_EXPRESSION / BASE_POSE 每组只调用一次模型，直接生成一张设定图（默认 2048×1536，4:3，与模型原生 1360×1024 画幅一致），网格由 `prompting.sheet_layout` 按条目数算出；不再逐项单出再拼板。表情包 APP-01 每 8 个大头贴式胸像一张 4:3 透明设定图（2×4），程序切成独立贴纸（全身构图每格太小、表情看不清，需求方定为胸像）；其他成品包的单项图各自生成。真实测试：逐张出 22 张 vs 设定图 3 张，身份一致性相当 |
| ADR-017 | 设定图无缝网格 + 程序文字标注版 | 确认（需求方定） | 凡含多个子图的一组（ADR-016）都生成一张无缝网格设定图：格子严格等分且紧贴，不留白边、不画分隔线或边框，模型图内不写字。设定图用作视频/生图参考或知识库时，由 `annotate.annotate_sheet` 在图上加标题条和每格编号+名称，另存 `*_labeled.png`，干净版保留。文字由程序画，保证逐字准确；只有整幅成品（海报、横幅、壁纸、介绍页）各自单独生成 |
| ADR-018 | 整幅设计成品的文字由模型排版 | 确认（需求方定） | 头像横幅、封面、海报、介绍页等整幅设计成品，标题和文案逐字写进提示词，由图像模型连同画面一起设计并选择相称字体；程序后贴的文字与画面风格脱节。交付前逐字核对（`model_text_exact` 软检查），错字带准确文案重出。门牌、导视、印刷标牌和设定图标注仍由程序排版 |
