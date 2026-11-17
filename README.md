# IP Asset Production Skill — SPEC & Codex Starter

这是面向腾讯 **WorkBuddy** 与 **DeepSeek Harness** 的 IP 角色资产生产 Skill 开发规范包（**非已完成可部署产品**）。

## 从哪里开始

1. 产品与技术唯一需求基线：[`docs/SPEC.md`](docs/SPEC.md)
2. 给 Codex 的仓库常驻约束：[`AGENTS.md`](AGENTS.md)
3. 按里程碑开发：[`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)
4. 来源档案 41 组迁移：[`docs/SOURCE_AUDIT.md`](docs/SOURCE_AUDIT.md)
5. 风格库与样例预览规范：[`docs/STYLE_LIBRARY_AND_PREVIEWS.md`](docs/STYLE_LIBRARY_AND_PREVIEWS.md)
5. 模板与提示词：[`prompts/`](prompts/)
6. 结构化目录：[`catalogs/asset_catalog.json`](catalogs/asset_catalog.json)
7. Schema：[`schemas/`](schemas/)
8. 验收测试集：[`tests/acceptance_cases.json`](tests/acceptance_cases.json)

## 范围

- 三种 IP 创建方式：多图直接、多图微调、文字原创。
- 数字人／动漫人类／卡通动物／拟人化物体／幻想角色。
- 基于角色定妆和应用目的推荐资产。
- 41 历史资产记录、14 新资产模板、10 个直接可用应用包。
- 图像输出像素、比例、格式、打印尺寸与质量验收。
- 可配置 Provider、双宿主安装与能力发现。

## 使用 Codex 的第一条任务

> 阅读 `AGENTS.md` 与 `docs/SPEC.md`，严格按照 `docs/IMPLEMENTATION_PLAN.md` 只实现 M0：仓库基础、Schemas、catalog validator、MockProvider 最小合同及离线测试。不得接入真实生图或上传任何用户原图。每个 PR 附测试结果与已完成验收项。

## 本地开发（M0）

```bash
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -e '.[dev]'
```

每次提交前运行（与 CI 相同；全程离线，不需要任何图像服务凭证）：

```bash
.venv/bin/python scripts/secret_scan.py      # 隐私 / 密钥扫描
.venv/bin/python scripts/validate_spec.py    # SPEC ↔ 数据交叉一致性
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy
.venv/bin/python -m pytest
```

`scripts/check_style_release.py` 是 v1 发布门禁，在 M2A 产出 48 张真实审核样例之前**必然失败**。

## 安全与发布

**严禁提交原始用户参考图、AIKate 原始 HTML/图片、真实真人照片、密钥、缓存与内部日志。** 本仓库的 41 组素材仅保留来源编号、标题与参数化模板映射，未纳入原始成图和逐字提示词。

公开仓库的组织名、License、真实图片 Provider、WorkBuddy 运行版本等需用户在发布前最终确定。发布前请阅读 `docs/SECURITY_AND_PUBLISHING.md`。

## 状态

本版本为 `v1.2.0-draft` SPEC。除原有文档/模板/Schema/验收用例外，已将 **48 种风格 / 8 个家族 / 样例预览与风格选择** 纳入首版范围，风格库列表和完整 Prompt 已写入 `docs/SPEC.md` 和 `styles/catalog.json`；尚未完成真实图像模型接入、风格样例批量产出或双宿主安装测试。

## 风格库第一版

- `styles/catalog.json`：48 种带类型适配与 Prompt 的风格条目。
- `styles/taxonomy.json`：风格属性维度。
- `styles/prototypes.json`：标准对照原型。
- `styles/preview_manifest.json` 与 `styles/preview_requests.jsonl`：可直接供 Codex 读取的样例生产任务（目前计划态，不含成图）。
- 样例交付最低要求：48 张真实生图并通过 QA，随后上线画廊。

### 风格预览发布验收

开发期静态校验：`python scripts/validate_spec.py`。真实图片生成完毕、审核并确认可再分发后，运行 `python scripts/check_style_release.py`；没有真实图片时该命令**应该失败**。
