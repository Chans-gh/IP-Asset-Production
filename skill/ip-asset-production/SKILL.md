---
name: ip-asset-production
description: Create, transform and manage visual IP characters, plan reusable assets for digital humans, anime characters and mascots, and produce image/application kits with explicit resolution and QA requirements.
---

# IP Asset Production — Skill Entry (开发草案)

**当前阶段：规范和 Prompt 示例；执行脚本、Provider 与宿主集成将在 Codex 迭代中完成。不要声称本 Skill 已经具有可用的图像生成工具。**

## 使用场景

用户希望原创/导入/微调数字人、动漫人物、动物或拟人化物体；规划角色资产、生成多视图/表情/动作/服装图；生成表情包、会议室门牌等直接可用产品时调用。

## 执行规则

1. 读取 `prompts/skill-core.md` 的核心流程（打包时将相对资源复制入 skill 包）及 `docs/SPEC.md` 的要求。
2. 识别图片直用、图片微调、文字原创三种模式。给每张参考图标记身份/风格/姿态/配饰用途；若冲突需确认。
3. 非数字人明确风格后，生成定妆候选并取得用户批准。
4. 采用 `catalogs/asset_catalog.json` 中资产类型和用途，对缺少专业知识的用户主动推荐资产；可直接制作成品包的最小依赖，不要强制全套。
5. 使用 `prompts/common-and-legacy.md`、`prompts/new-assets.md`、`prompts/application-kits.md` 编译完整可执行 Prompt。
6. 指定目标尺寸、格式、透明背景和 QA；只有具备实际图像工具时才能生成，成功后检查真实文件与交付 manifest。
7. 公开 Git 绝不可提交真人原始参考、用户图片和密钥。

## 依赖与缺失能力

本 `SKILL.md` 是 **Codex 开发起点**，部署时应将相对参考文件按宿主规则放入技能包，并由 `HostAdapter` 接通脚本/Provider。若当前只有文本模型，则只输出计划和 Prompt 并明确限制。

## Visual style previews
For non-digital characters, use the versioned `styles/catalog.json` (STYLE-001..STYLE-048) and `docs/STYLE_LIBRARY_AND_PREVIEWS.md` to recommend appropriate visual styles. Show only actual approved preview images; when none are available, provide text descriptions and state previews are unavailable. Never substitute planned manifest entries for generated images. Confirm selected style_id before canonization.
