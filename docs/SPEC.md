# IP Asset Production Skill — 产品与技术开发 SPEC

> 版本：`1.2.0-draft` | 日期：2026-11-17 | 语言：中文 | 状态：可交付 Codex 实施的需求基线（未完成宿主集成测试）
>
> 目标宿主：**腾讯 WorkBuddy、DeepSeek Harness**；开发方式：**Codex + Git 公共仓库**。
>
> 源资料：用户提供的《AIKate 角色资产生成清单完整版｜提示词与成图总档案》（41 组提示词+图片），并参考会话中 SPEC-001～007 的需求。原档案中历史提示词为复原稿，不是图像工具隐藏提示词的逐字导出。所有本 SPEC 的新增模板、默认参数和实施架构属于开发提案。

## 0. 摘要 / 执行原则

**目标**：用户不必懂专业视觉资产制作，只需上传 N 张图片或描述意图，Skill 就能完成 IP 创建/导入/改造、角色定妆、按用途规划视觉资产、调用图像工具生成、验证和重试、合成可直接使用的应用套装，并版本化保存所有文件。

**必须做到**：

1. 两种主 IP 系统：数字人 IP；卡通动漫 IP（涵盖人、动物、拟人化物品与幻想角色）。角色大类、形体拓扑、风格、应用用途四个维度独立建模。
2. 三种入口：多参考图直接创建；多参考图微调/衍生创建；纯自然语言原创。
3. 非数字人必须确认视觉风格；有明确图片风格时询问是否沿用；**v1.2 即包含动漫风格分类库、样例预览库、风格推荐与风格选择机制**，并为后续扩展保留 taxonomy 接口。
4. 用户无须自己提供资产清单；Skill 结合用途推荐 P0/P1/P2，并能通过应用成品倒推所需基础资产。
5. 兼容 AIKate 41 个历史资产记录（迁移映射，不生硬复制）；增加至少 14 个基础资产模板能力和 10 个可用应用套装模板。
6. 每个生成任务必须声明目标像素、比例、格式、透明要求、背景、色彩、版式安全区；不可把提示词中的目标像素混同于图像模型可实际输出的原生规格。
7. **优先独立图片，再合成多视图/九宫格**；准确中文、数值标注、品牌字段和印刷裁切线由确定性排版层完成。
8. 宿主 Skill 加载与生图服务执行是两层不同能力；无可用生图工具时只可输出计划/Prompt，不得伪称已生成。
9. 个人真人照片及图像生成凭证不得进入公开 Git 仓库。用户对真人照片的授权、外发同意和可辨认身份风险需要记录。
10. 初版交付可本地离线用 mock 完整演示；真实图像引擎要通过可替换 Provider 接口接入。

## 1. 需求状态、范围与术语

### 1.1 需求来源与优先级

| 需求域 | 状态 | 内容 |
|---|---|---|
| 产品定位 | 已确认 | 一体化 IP 创建 + 资产生产 + 成品交付 + 管理 |
| IP 类型 | 已确认 | 数字人；卡通动漫人或物，包含动物 |
| 入口模式 | 已确认 | 参考直接、参考微调、文字原创；N 张图片 |
| 数字人真人转换 | 已确认 | 允许基于有授权的真人图片微调产生数字人 |
| 非数字人风格 | 已确认 | 必须有风格确认环节，v1.2 同步建设风格分类库与可视化预览 |
| 智能资产规划 | 已确认 | 目录、分类、用途解释与推荐 |
| 原档案 | 已确认 | 41 组审计、改造适配、新增模板及对应 Prompt |
| 应用成品 | 已确认 | 至少表情包、会议室门牌，扩展其他成品 |
| 图片技术规格 | 已确认 | 尺寸、分辨率、比例、格式和一致性 |
| 运行平台 | 已确认 | WorkBuddy / DeepSeek Harness |
| 开发和公开分发 | 已确认 | Codex 实施、Git 公开仓库同步 |
| 风格样例与风格画廊 | 已确认 | v1.2 开发期同步批量生成样例，并用于用户可视化选择 |
| 13 类资产/14 新模板/10 应用包 | 候选默认值 | 允许评审时调整；初版按此数据结构落地 |
| 默认 Python 工具栈 | 实施建议 | Python 3.11+、Pydantic、Pillow、pytest、JSON Schema；不排除更合适实现 |

### 1.2 必须严格区分的术语

- `Character`：角色实例。`CharacterVersion`：一次经用户批准的定妆身份版本。
- `IPType`：数字人、动漫人物、动物、拟人物体等；不是风格字段。
- `BodyTopology`：human-like、quadruped、winged、limbless 等决定可见部位与动作范围。
- `StyleProfile`：2D/3D、材质、造型语言、线条和细节级别的多维配置；不强制单一标签。
- `ReferenceManifest`：每张用户图片的角色/发型/风格/道具等角色和优先级。
- `AssetTemplate`：可生成的一种通用资产能力。`AssetItem`：一次具体实例。`OutputVariant`：clean/annotated/individual/contact_sheet 等。
- `ApplicationKit`：可直接使用的成品套装；不等于纯视觉资产参考图。
- `PromptTemplate`：可参数化的生图任务描述；`ProviderAdapter`：完成真实模型参数映射和调用的执行层。
- `DeliveredFile`：经 QA 检查通过并具有真实文件路径、hash、尺寸的文件。

### 1.3 明确不保证

- 单靠文字提示词不能保证像素级人物身份一致性、真实 3D 模型、可印刷 CMYK、正式法律著作权归属、真实分层 PSD/Live2D 工程。
- 未经过宿主实际部署验证，不能宣称双平台已安装成功。
- 基于真人照片做过微调，并不自动代表该形象已完全脱离原始真人身份。
- 若用户未明确提出动画视频或模型文件，则默认输出的是**静态图像与参考板**，不能以静态预览冒充可播放或可编辑的成品。

## 2. 用户旅程与创建模式

### 2.1 用户入口（不要强迫用户填写多项表单）

用户可输入文字、多张图片或混合输入。系统解析 `mode`：

| mode | 触发 | 定义 | 必需数据 |
|---|---|---|---|
| `REFERENCE_DIRECT` | “以这些图为准，做资产” | 主要保留指定角色特征，仅按任务扩展 | >=1 张图、参考角色声明（模糊时确认） |
| `REFERENCE_TRANSFORM` | “按这些参考改出新角色” | 在保留/修改特征边界内产生新的经批准定妆版本 | >=1 张图、保留/修改目标 |
| `ORIGINAL_CREATE` | “帮我设计一个新 IP” | 从零生成角色方案 | 描述或目标定位 |

`reference_images` 允许 1..N 张，具体 N 不固定，由宿主上传能力、模型限制及预算决定。应可包含多角色示例和多种参考用途，但**不允许未经授权把不同角色的身份特征自动混合**。

### 2.2 参考图冲突与角色来源

每张图至少声明：`ref_id / uri / sha256 / role / subject_id / priority / permission_scope`。
`role` 可为 `identity, face, silhouette, style, pose, outfit, prop, scene, material, product`。
若同一角色的身份与结构参考冲突，先根据用户明确意图和 `priority` 处理；仍冲突时只问一个最影响结果的确认问题。
`REFERENCE_TRANSFORM` 必须保存 `keep_features[]` 和 `change_features[]`；一经用户确认新的角色，后续统一使用新版定妆，不再每次回到原始真人重设计。

### 2.3 确认点（Approval Gates）

- `G1`：意图、类型与关键保留/修改特征清晰；参考图冲突已解。
- `G2`：非数字人 `style_profile` 已确认（从图提取时也要询问是否沿用）。
- `G3`：候选定妆图完成，用户明确批准某个 `character_version`。
- `G4`：资产规划完成，用户选择全套、推荐套装或直接成品需求，确认任务成本/数量。
- `G5`：生产中出现关键身份偏移、授权/数据外发不明确、成本异常时暂停相应任务。
- `G6`：交付前核查规格、完整性和格式；批量产品允许部分成功但必须报告。

默认采用最少必要的追问：若信息足够即可直接继续，不因用户不知道“应生成哪些资产”而阻塞。

## 3. 角色档案与身份锁定

### 3.1 数据结构

`character_profile` 以 `schemas/character-profile.schema.json` 为正式结构契约，关键字段：

- `character_id`, `version`, `approval_status`, `creation_mode`, `ip_type`, `body_topology`, `style_profile`。
- `identity_anchors`: 不可更改的脸/轮廓/配色/尾巴/角/四肢数量/表面材质等。
- `allowed_variations`: 可换的服饰、表情、镜头、照明或指定区域。
- `anatomy`: 人形、四足、有翼、无肢体等结构的显式描述与部件数（按需）；不得臆造真实测量数据。
- `reference_manifest`, `canonical_image_uri`, `canonical_image_sha256`, `palette`, `provenance`, `rights_acknowledgement`。

`CharacterVersion` 必须不可变；修改身份锚点应创建新版本，而非覆盖历史版本。

### 3.2 数字人真人参考的合规要求

- 用户需确认对照片及人物肖像具有相应使用权限；涉及真实可辨认他人时，界面须提醒获得必要同意，不能把“微调”当作身份脱敏。
- 上传/外发第三方模型需呈现服务提供方、数据类别、目的与用户批准方式；配置允许 `no_external_upload`。
- 上传的原图应保存在本地项目的私有数据目录，默认不进日志、Prompt dump、Git 或样例发布包。
- 无授权或不确定时，可以提供通用设计指引，避免主动复用未经许可的真人肖像与商标。

## 4. 风格引擎（非数字人必须确认）

`style_profile` 采用组合维度而不是不可维护的单一“风格名”：

| 维度 | 枚举示例（允许扩展） |
|---|---|
| medium | `2d`, `2_5d`, `3d`, `pixel`, `stop_motion_look` |
| tradition | `anime`, `western_cartoon`, `chinese_animation`, `picture_book`, `graphic`, `original` |
| proportions | `chibi`, `standard`, `super_deformed`, `stylized`, `custom` |
| material | `flat_color`, `cel_shaded`, `watercolor`, `clay`, `plush`, `vinyl`, `ceramic`, `metallic`, `photoreal` |
| linework | `none`, `fine`, `bold`, `hand_drawn` |
| mood | `cute`, `warm`, `minimal`, `retro`, `sci_fi`, `dark`, `playful` |
| detail | `low`, `medium`, `high` |

不得仅根据“动物/动漫”默认某种 3D 效果；明确的风格参考可由用户确认继承。风格库在 **v1.2 首发范围** 中实现第一版：需包含 taxonomy、catalog、compatibility 规则、样例预览图、预览 manifest 以及风格选择交互；同时保留可持续扩展接口，不要求首版穷举所有风格。


## 4A. 动漫风格分类库、样例生成与可视化选择系统

### 4A.1 产品目标

风格库不是只给模型用的隐藏参数，而是**用户可见、可比较、可选择**的能力。对于非数字人 IP，Skill 应在角色创建阶段展示若干风格方向，让用户通过文字说明和预览样例理解差异，再确认目标风格。该机制是 v1.2 首发能力，不再延期到后续版本。

### 4A.2 必备交付物

首版风格系统至少包含以下内容：

| 交付物 | 说明 |
|---|---|
| `styles/taxonomy.json` | 风格多维分类定义，描述 medium/tradition/proportions/material/linework/mood/detail 等维度 |
| `styles/catalog.json` | 风格条目清单，每项有 `style_id`、中文名、描述、适用对象、Prompt 片段、兼容标签 |
| `styles/compatibility.json` | 风格组合兼容性与冲突矩阵 |
| `styles/preview_manifest.json` | 样例图清单，记录预览图文件、角色原型、生成参数、审核状态 |
| `styles/previews/` | 样例图目录，按 human / animal / object 分类 |
| `docs/STYLE_LIBRARY_AND_PREVIEWS.md` | 风格库建设原则、样例生成流程、验收与发布要求 |

### 4A.3 首版样例范围与硬性指标

首版**锁定 48 个高区分度风格条目（8 组，每组 6 个）**，作为 v1.2 的确定性交付清单，不再使用模糊的“30–50 个待选”目标。每个风格在开发期至少要生成一张经审核通过的独立预览图，逐步补齐三类原型。完整列表及可复制 Prompt 片段见 4A.7 与 `styles/catalog.json`。

1. `HUMAN_PROTO`：标准动漫人物原型
2. `ANIMAL_PROTO`：标准卡通动物原型
3. `OBJECT_PROTO`：标准拟人化物体原型

**关键原则**：用户是在“选风格”，不是在“选完全不同的角色”。因此同类原型的样例图应尽量保持构图、姿态、背景和信息密度一致，只改变风格表达。

### 4A.4 样例生成策略

- 样例由 Codex 在开发期按规则批量生成，不能临时从互联网上抓图代替。
- 样例图必须带元数据：`style_id`、`prototype_id`、`provider`、`prompt_version`、`created_at`、`review_status`。
- 任何公开发布的样例必须确认可公开分发；默认使用自生成、可追溯、无第三方版权风险的样例。
- 若某风格在不同 Provider 间差异较大，应优先固定一个样例生成 Provider，并记录能力差异。
- 生成失败或质量不稳定的风格条目，不应直接进入用户可选列表；需先标记为 `draft` 或 `internal_only`。

### 4A.5 用户交互要求

- 非数字人创建流程中，Skill 至少展示 6–8 个最相关风格，而不是一次展示全部库。
- 风格可通过图片消息、编号选择、或宿主可支持的选择控件呈现。
- 若宿主 UI 受限，Skill 应自动生成本地 HTML 风格画廊作为兼容降级方案。
- 用户确认风格后，`style_profile` 和 `style_id` 必须写入 `CharacterVersion`，后续资产和应用成品默认继承该风格。
- Skill 需支持“换风格重做候选图”，并将其记为新的角色版本或新的风格分支。

### 4A.6 风格样例 QA

样例图的 QA 不只检查像素和文件存在，还应检查：

- 是否能清晰体现目标风格差异；
- 是否与该风格中文描述一致；
- 是否保留统一原型的核心结构；
- 是否有明显错误（肢体错位、文字乱码、背景污染、风格混杂）；
- 是否适合作为用户选择参考，而非仅适合作为内部调试图。


### 4A.7 v1.2 首批 48 种预置风格：编号、适用对象与 Prompt 核心片段

下表是**产品/开发团队提出的首版设计目录**，不是来源 AIKate 41 组档案已有的风格清单。`✓` 表示默认适用，`—` 表示首版不主动推荐（不意味着绝对不能设计）。这些是风格“预设”，可叠加兼容的氛围与配色，不应生硬混用相冲突的媒介材质。风格名称采用通用美术描述，避免对特定影视作品或在世艺术家做一比一仿制。

### G01｜日系与东方二维动画

| ID | 风格名称 | 核心特征 | 动漫人 | 动物 | 拟人物体 | 幻想生物 | Prompt 核心片段（英语） |
|---|---|---|:---:|:---:|:---:|:---:|---|
| STYLE-001 | 日系经典赛璐璐 | 清晰色块、标准动画线稿、干净阴影 | ✓ | ✓ | — | ✓ | clean Japanese-inspired 2D cel animation, confident thin ink outlines, flat color blocks, one crisp shadow layer, controlled highlights |
| STYLE-002 | 日系柔彩日常 | 低对比柔色、柔光、日常亲和气质 | ✓ | ✓ | ✓ | — | soft pastel 2D everyday animation, gentle diffuse shading, light delicate contours, subtle warm palette, approachable quiet mood |
| STYLE-003 | 热血夸张动作番 | 动态线条、锐利阴影、运动夸张 | ✓ | ✓ | — | ✓ | energetic action animation design, sharp angular shadows, expressive poses, dynamic ink strokes, high-contrast accent colors, readable silhouette |
| STYLE-004 | 少女浪漫梦幻 | 轻盈线条、柔和闪光、浪漫配色 | ✓ | ✓ | — | — | dreamy romantic 2D animation illustration, graceful flowing linework, delicate luminous accents, soft luminous gradient highlights, elegant color harmony |
| STYLE-005 | 二头身 Q 版萌系 | 大头短身、极简表情、高辨识轮廓 | ✓ | ✓ | ✓ | ✓ | super deformed chibi 2D character, oversized head, compact rounded body, simplified expressive facial features, bright readable colors, clean flat shadows |
| STYLE-006 | 国风工笔动画 | 工整轮廓、装饰纹理、东方配色 | ✓ | ✓ | ✓ | ✓ | Chinese-inspired meticulous brush illustration animation, precise delicate contour lines, elegant layered flat pigments, restrained ornamental details |

### G02｜欧美与经典二维卡通

| ID | 风格名称 | 核心特征 | 动漫人 | 动物 | 拟人物体 | 幻想生物 | Prompt 核心片段（英语） |
|---|---|---|:---:|:---:|:---:|:---:|---|
| STYLE-007 | 欧美经典圆润卡通 | 圆润轮廓、灵活动作、鲜明色彩 | ✓ | ✓ | ✓ | ✓ | classic rounded western cartoon illustration, lively elastic shapes, bold contour lines, squash-and-stretch expression, bright clean cel colors |
| STYLE-008 | 现代欧美扁平动画 | 几何块面、简洁五官、现代排布 | ✓ | ✓ | ✓ | ✓ | modern flat animated character design, geometric color shapes, simplified anatomy, minimal facial marks, flat graphic surfaces without gradients |
| STYLE-009 | 复古橡皮管动画 | 弧形肢体、黑白胶片感、夸张弹性 | ✓ | ✓ | ✓ | ✓ | original 1920s-inspired rubber-hose cartoon aesthetics, noodle-like limbs, curved elastic joints, vintage ink-and-paper contrast, playful rhythmic silhouettes |
| STYLE-010 | 复古报刊四格 | 点阵网纹、报刊色限制、漫画笔触 | ✓ | ✓ | ✓ | ✓ | vintage newspaper comic character illustration, thick pen strokes, halftone dot shadows, limited spot colors, clear expressive staging |
| STYLE-011 | 现代粗线角色 | 粗线条、夸张五官、图标级辨识 | ✓ | ✓ | ✓ | ✓ | bold modern cartoon character art, heavy uniform dark outlines, expressive large shapes, simplified flat palette, highly readable graphic silhouette |
| STYLE-012 | 欧陆清新线描 | 轻手绘线、浅色留白、松弛表情 | ✓ | ✓ | ✓ | — | airy European editorial cartoon illustration, spare hand-drawn strokes, abundant white space, subtle pastel washes, casual gentle expression |

### G03｜绘本与自然手绘

| ID | 风格名称 | 核心特征 | 动漫人 | 动物 | 拟人物体 | 幻想生物 | Prompt 核心片段（英语） |
|---|---|---|:---:|:---:|:---:|:---:|---|
| STYLE-013 | 儿童绘本水彩 | 水彩扩散、纸纹、温暖叙事 | ✓ | ✓ | ✓ | ✓ | children picture-book watercolor illustration, soft pigment blooms, textured watercolor paper, gentle outlines, warm storytelling color atmosphere |
| STYLE-014 | 彩铅素描绘本 | 彩铅笔触、纸张颗粒、渐层线条 | ✓ | ✓ | ✓ | ✓ | colored-pencil storybook drawing, visible layered pencil strokes, toothy paper texture, gentle crosshatching, hand-rendered subtle color variation |
| STYLE-015 | 蜡笔童趣涂绘 | 蜡笔粗糙边缘、童画不规则感 | ✓ | ✓ | ✓ | ✓ | playful crayon children illustration, chunky waxy crayon marks, uneven hand-colored fills, simple childlike shapes, warm paper background |
| STYLE-016 | 拼贴剪贴绘本 | 纸材拼接、可见纤维、不规则轮廓 | ✓ | ✓ | ✓ | ✓ | hand-cut paper collage storybook illustration, mismatched colored paper pieces, visible paper fibers, layered handmade edges, friendly proportions |
| STYLE-017 | 粉蜡笔柔雾画 | 粉化颗粒、轻柔扩散、柔雾光感 | ✓ | ✓ | ✓ | ✓ | soft pastel chalk illustration, dusty pigment edges, velvety diffuse color transitions, subdued dreamy glow, delicate handmade paper grain |
| STYLE-018 | 东方水墨动画 | 浓淡墨韵、晕染、克制色彩 | ✓ | ✓ | ✓ | ✓ | original ink-wash animated character design, flowing expressive ink contours, tonal wash gradations, intentional negative space, subtle mineral pigment touches |

### G04｜图形、贴纸与像素

| ID | 风格名称 | 核心特征 | 动漫人 | 动物 | 拟人物体 | 幻想生物 | Prompt 核心片段（英语） |
|---|---|---|:---:|:---:|:---:|:---:|---|
| STYLE-019 | 极简矢量图标 | 少色块、稳定几何、可缩小识别 | ✓ | ✓ | ✓ | ✓ | minimal geometric vector mascot, limited flat color palette, crisp simple geometric contours, no textures or gradients, strong tiny-icon readability |
| STYLE-020 | 粗描边贴纸插画 | 粗描边、白边贴纸、强烈表情 | ✓ | ✓ | ✓ | ✓ | bold outlined sticker illustration, playful mascot shapes, strong graphic contour, smooth flat color, separate thick white sticker border |
| STYLE-021 | 街头潮流涂鸦 | 喷涂纹理、涂鸦动态、重叠线 | ✓ | ✓ | ✓ | ✓ | original street-art doodle character illustration, expressive marker scribbles, paint splatter accents, loose kinetic outlines, vibrant layered colors |
| STYLE-022 | 波普丝网印刷 | 网点套印、有限专色、强对比 | ✓ | ✓ | ✓ | ✓ | pop screen-print character art, coarse halftone texture, limited vivid spot-color inks, slight ink registration offsets, bold iconic shadow areas |
| STYLE-023 | 8 位复古像素 | 低像素数量、强网格、单像素边缘 | ✓ | ✓ | ✓ | ✓ | authentic low-resolution 8-bit sprite aesthetic, strict pixel grid, hard pixel edges, very limited retro palette, no interpolation or smooth outlines |
| STYLE-024 | 16 位精致像素 | 更丰富色阶、手工像素阴影 | ✓ | ✓ | ✓ | ✓ | detailed 16-bit pixel-art character sprite aesthetic, hand-clustered pixels, distinct small-scale highlights, controlled dithering, crisp non-antialiased edges |

### G05｜2.5D 与手工层叠

| ID | 风格名称 | 核心特征 | 动漫人 | 动物 | 拟人物体 | 幻想生物 | Prompt 核心片段（英语） |
|---|---|---|:---:|:---:|:---:|:---:|---|
| STYLE-025 | 2.5D 等距角色插画 | 等距体块、统一三维投影、扁平景深 | ✓ | ✓ | ✓ | ✓ | isometric 2.5D character illustration, consistent axonometric geometry, soft painted planar shading, clean readable forms, controlled depth cues |
| STYLE-026 | 2.5D 分层纸雕 | 多层纸片厚度、投影、手工裁边 | ✓ | ✓ | ✓ | ✓ | layered paper-cut diorama character, stacked matte cardstock shapes, visible cut paper thickness, gentle between-layer shadows, clean craft composition |
| STYLE-027 | 剪纸皮影戏造型 | 镂空纹样、侧影强、皮影平面结构 | ✓ | ✓ | ✓ | ✓ | Chinese-inspired traditional shadow-puppet silhouette design, thin translucent cutout plates, refined perforated ornaments, planar joint details, warm backlit edges |
| STYLE-028 | 黏土浮雕插画 | 浅浮雕凸起、压印纹理、侧面微阴影 | ✓ | ✓ | ✓ | ✓ | shallow polymer-clay relief illustration, raised molded shapes on a flat board, soft tactile clay texture, subtle directional relief shadows, clean frontal view |
| STYLE-029 | 布艺拼贴角色 | 缝线、毛毡布片、软质重叠 | ✓ | ✓ | ✓ | ✓ | layered textile appliqué character art, soft fabric patches, visible stitched seams, tactile woven and felt surface, gentle fabric-layer shadows |
| STYLE-030 | 立体糖果图标 | 半立体高光、小景深、圆润几何 | — | ✓ | ✓ | ✓ | semi-dimensional candy-like mascot icon, softly extruded rounded shapes, restrained glossy highlights, shallow playful depth, simple friendly icon composition |

### G06｜三维动画造型

| ID | 风格名称 | 核心特征 | 动漫人 | 动物 | 拟人物体 | 幻想生物 | Prompt 核心片段（英语） |
|---|---|---|:---:|:---:|:---:|:---:|---|
| STYLE-031 | 现代三维卡通动画 | 柔和体积光、圆润轮廓、细节平衡 | ✓ | ✓ | ✓ | ✓ | original high-quality modern 3D cartoon character render, friendly rounded modeling, soft global illumination, polished materials, expressive appealing proportions |
| STYLE-032 | 3D Q 版萌系 | 超大头、短四肢、圆鼓鼓形体 | ✓ | ✓ | ✓ | ✓ | stylized 3D chibi mascot, oversized head and tiny compact body, rounded toy-like anatomy, simple readable expression, clean soft shading |
| STYLE-033 | 3D 半写实角色 | 真实结构+动画比例、细腻材质 | ✓ | ✓ | — | ✓ | semi-realistic stylized 3D animation character, credible anatomy with slightly exaggerated features, nuanced subsurface shading, natural material textures |
| STYLE-034 | 3D 低多边形 | 明显棱面、简化多边形、硬边颜色 | ✓ | ✓ | ✓ | ✓ | low-poly faceted 3D character, visible polygon planes, simplified sculptural silhouette, flat-shaded surfaces, restrained color palette, no smoothing |
| STYLE-035 | 3D 圆角软胶简模 | 无纹理软胶、少量零件、平滑转折 | ✓ | ✓ | ✓ | ✓ | minimal 3D soft-rubber mascot, smooth rounded volumes, matte elastomer material, simplified parts, minimal seams, clear graphic geometry |
| STYLE-036 | 3D 未来科幻卡通 | 柔性未来组件、可读科技细节、非写实科技 | ✓ | ✓ | ✓ | ✓ | friendly futuristic 3D cartoon character, sleek simplified tech panels, soft luminous accents, readable stylized mechanical details, bright sci-fi color language |

### G07｜玩具与实体材质

| ID | 风格名称 | 核心特征 | 动漫人 | 动物 | 拟人物体 | 幻想生物 | Prompt 核心片段（英语） |
|---|---|---|:---:|:---:|:---:|:---:|---|
| STYLE-037 | 3D 毛绒玩偶 | 短毛绒、软缝线、饱满轮廓 | ✓ | ✓ | ✓ | ✓ | plush stuffed toy character, short fluffy pile fibers, soft fabric seams, padded rounded silhouette, embroidered facial features, studio product lighting |
| STYLE-038 | 3D 羊毛毡手作 | 针毡纤维、扎实毛束、手工表情 | ✓ | ✓ | ✓ | ✓ | needle-felted wool toy character, densely packed visible wool fibers, handmade felt texture, tiny sculpted details, soft natural shadow |
| STYLE-039 | 3D 黏土定格 | 指压痕、黏土接缝、逐帧定格感 | ✓ | ✓ | ✓ | ✓ | handcrafted clay stop-motion character appearance, subtle finger-pressed fingerprints, sculpted clay seams, tactile matte clay surface, warm studio set lighting |
| STYLE-040 | 3D 搪胶潮玩 | 搪胶高光、精简装饰、工业量产造型 | ✓ | ✓ | ✓ | ✓ | collectible vinyl art-toy character, smooth vinyl shell, crisp painted graphic details, polished toy finish, simplified production-friendly part separation |
| STYLE-041 | 3D 陶瓷摆件 | 釉面反射、陶瓷厚度、微小釉面差异 | ✓ | ✓ | ✓ | ✓ | glazed ceramic figurine character, glossy fired glaze, rounded ceramic thickness, subtle ceramic imperfections, gentle controlled studio reflections |
| STYLE-042 | 3D 木雕玩具 | 木纹走向、手工雕刻、哑光木质 | ✓ | ✓ | ✓ | ✓ | hand-carved wooden toy character, visible natural wood grain, softened carved edges, matte varnished wood, simple craftsmanship-friendly shape |

### G08｜实验材质与主题风格

| ID | 风格名称 | 核心特征 | 动漫人 | 动物 | 拟人物体 | 幻想生物 | Prompt 核心片段（英语） |
|---|---|---|:---:|:---:|:---:|:---:|---|
| STYLE-043 | 3D 透明琉璃糖果 | 半透明彩色折射、晶亮边缘、轻盈体积 | — | ✓ | ✓ | ✓ | translucent candy-glass mascot, colored refraction, delicate glossy edges, clean transparent material volume, bright studio caustic-like highlights |
| STYLE-044 | 3D 金属机甲萌系 | 小型金属装甲、圆润结构、局部机械件 | ✓ | ✓ | ✓ | ✓ | cute chibi mechanized character, rounded modular metal armor, simplified mechanical joints, brushed metallic accents, friendly expressive face |
| STYLE-045 | 3D 纸盒积木玩具 | 纸盒折边、方块结构、少量印刷面 | ✓ | ✓ | ✓ | ✓ | modular cardboard block toy character, folded paperboard edges, boxy geometric parts, visible cardboard texture, clean colored printed panels |
| STYLE-046 | 2D 暗黑童话 | 暗色调、奇想剪影、克制怪诞 | ✓ | ✓ | ✓ | ✓ | dark fairytale character illustration, whimsical eerie silhouettes, rich muted jewel-tone palette, delicate crosshatched details, mysterious storybook lighting |
| STYLE-047 | 2D 赛博霓虹 | 高饱和荧光、轮廓发光、数字都市感 | ✓ | ✓ | ✓ | ✓ | stylized cyber-neon 2D mascot illustration, luminous contrasting edge lights, vibrant magenta-cyan accents, dark crisp graphic background, futurist details |
| STYLE-048 | 2D 复古双色印刷 | 限定两色油墨、错位印刷、粗粝纸张 | ✓ | ✓ | ✓ | ✓ | retro two-ink risograph-style character print, exactly two spot ink colors, misregistered print texture, grainy uncoated paper feel, bold simplified shapes |

**风格 ID 为固定接口。** JSON 中包含所有完整的 `prompt_fragment_en`、中文特征、适用对象与状态；实际生成时还应拼装 `styles/prototypes.json` 的标准角色原型、公共身份锁定规则、镜头/背景规范与 QA 约束。每条风格预设及其示例图均可独立版本化。

### 4A.8 Codex 的首版样例生产与验收数量

- 固定首批 **48 个预设**；对应至少 **48 张已审核可展示样例**（每个风格至少 1 张）。
- 推荐生成覆盖三类原型的样例，实际可生成范围见 `styles/preview_manifest.json` 的 planned 任务。`actual_file=null` 表示未生成，不可将目录占位或预览 URL 冒充真实样例。
- 每张样例均记录 `style_id`、`prototype_id`、Prompt 原文与 hash、Provider/Model、生成时间、图片尺寸、质量审核、可再分发检查。
- 默认目标为 1024×1024 PNG，暖白中性背景、完整单角色、统一构图；模型原生尺寸与交付尺寸必须分别存档。像素艺术必须保留最近邻像素边缘。
- 图像质量未达到标准时应有限次重试，仍失败则标为 `failed`，不进入用户风格选项。不能仅有模拟图就声称首版视觉样例交付完成。
- 用户选择风格后，Skill 存储 `style_id` 和 `style_profile`；之后生成资产和应用成品继承该角色版本风格。
- **时间依赖**：M1 做数据和样例请求清单；M2 接入 Provider；M2A 批量生成真实样例和画廊，不应要求在没有 Provider 的 M1 先产出真实图片。

## 5. 智能资产目录与规划系统

### 5.1 13 个一级目录

| ID | 分类 | 举例 | 用途 |
|---|---|---|---|
| A01 | 身份与标准视图 | 定妆、全身/半身、三四六视图、剪影 | 跨图一致性、建模参考 |
| A02 | 面部与关键特征 | 五官微距、毛发材质、特殊轮廓 | 局部重绘、风格锁定 |
| A03 | 表情与情绪 | 九宫格、独立情绪、表情强度 | 情绪内容、表情包 |
| A04 | 动作与姿态 | 站坐走、标志动作、头颈动作 | 动画、视频、海报 |
| A05 | 身体与局部结构 | 手足/爪/翅、关节、接触点 | 细节修复、动作制作 |
| A06 | 服装配饰与造型 | 日常服、鞋、帽、穿戴适配 | 换装、主题营销 |
| A07 | 角色设定与资料 | 角色资料板、介绍卡、配色 | 角色手册与传播 |
| A08 | 物种与非人形专项 | 尾巴、爪、喙、角、无腿结构 | 动物/物体身份稳定 |
| A09 | 场景与世界观 | 主场景、主题空间 | 漫画、内容世界观 |
| A10 | 道具与交互 | 产品交互、多人关系、接触 | 广告、剧情、短视频 |
| A11 | 传播内容组件 | 头像底图、横幅底图、KV素材 | 社媒、宣传 |
| A12 | 动画视频参考 | 口型、关键帧、二维拆件参考 | 后续动画制作 |
| A13 | 商品化设计参考 | 公仔、毛绒、盲盒外观参考 | 周边开发 |

41 组原始资产在 `catalogs/legacy_41_mapping.json` 完整映射、无遗漏：保留 41 条历史记录，但结构统一为模板族与输出变体。另有 `NEW-01..14` 新基础模板：见 `catalogs/asset_catalog.json` 与 `prompts/new-assets.md`。

### 5.2 结构适配和禁用

- 对人形允许全身、头肩、手足等；对四足角色替换为爪、尾和接触点；对无肢体物体跳过强制手脚、鞋履、九头身。
- 通过 `supports(ip_type, body_topology, capability_tags)` 过滤不适用模板，返回 `applicable / adapt / skip + rationale`。
- `variant` 不是独立模板；对 `annotated` 使用准确文本后处理，不能直接把外观中的乱码当作完成。
- 每个模板有 `use_cases[]`, `priority`, `dependencies[]`, `prompt_id`, `output_profile`, `qa_rules`。

### 5.3 智能规划算法（确定性优先、LLM 辅助）

1. 读取角色与用户目标（没有用途则给出推荐方案，而不是让用户自己发明清单）。
2. 过滤适用性，保留 `skip_reason` 方便解释。
3. 读取已有合格资产，通过内容 hash、`character_version` 与模板版本检测可复用项。
4. 以 `use_case -> required_templates -> dependencies` 求闭包，构建 DAG；禁止环。
5. 将任务分为 `P0 基础必备`、`P1 高频`、`P2 扩展`；实际可根据目标场景动态上调优先级。
6. 生成包含数量、图像规格、用途说明、费用/调用估计（如 Provider 暴露）的计划供用户确认。
7. 按 DAG 执行，任务可跳过、取消、重试；记录部分完成。

**重要**：当用户只要 APP-02 门牌时，不强迫先生成全部基础资产；只补齐最小依赖闭包。

## 6. 即用型应用套装（Ready-to-Use Kits）

| ID | 套装 | 单项交付定义 | 主要依赖 |
|---|---|---|---|
| APP-01 | 聊天表情包 | 12/16/24 个透明单图 + 预览 + manifest | G3 定妆、表情 |
| APP-02 | 会议室门牌包 | 状态 4+ 张、准确文字、印刷版 PDF、预览 | 定妆、动作/表情、排版 |
| APP-03 | 办公导视包 | 区域牌多版 PDF/PNG | 定妆、场景符号、排版 |
| APP-04 | 社交账号视觉包 | 头像、横幅、竖封面、渠道安全区 | 定妆、传播组件 |
| APP-05 | 直播视频贴片 | 透明贴片 + 横竖屏预览 | 定妆、表情/姿态 |
| APP-06 | 节日主题海报 | 方图、4:5、9:16，准确文案 | 定妆、主题造型、排版 |
| APP-07 | IP 主题壁纸 | 桌面/手机两版，独立构图 | 定妆、场景 |
| APP-08 | 贴纸打印周边 | 独立贴纸母版、裁切参考、印刷 PDF | 定妆、动作、排版 |
| APP-09 | 欢迎与提示牌 | 可读文案、物理规格、状态图 | 定妆、符号、排版 |
| APP-10 | 角色介绍与品牌应用 | 介绍页、可编辑信息、KV 视觉组件 | 定妆、资料、排版 |

应用包必须生成**独立真实文件**；禁止用一张示意总览图代替 16 张表情或 4 张门牌。发布渠道/印厂真实规范始终覆盖通用默认值。

## 7. Prompt 架构与安全边界

### 7.1 分层、编译与版本控制

构建 `PromptCompiler`，输出 `RenderedPrompt` 和 `ResolvedOutputSpec`，顺序固定：

1. `CORE-SYSTEM`：工作方式、安全限制、真实性与能力声明；
2. `COMMON-LOCK`：批准角色版本、身份锚点、参考图用途、禁止修改项；
3. `STYLE-BRANCH`：数字人 photoreal、动漫 stylized、动物/拟人拓扑规则；
4. `TASK-TEMPLATE`：BASE / NEW / APP 具体任务；
5. `CAMERA-LAYOUT`：角度、景别、占比、背景、构图、安全边距；
6. `OUTPUT-PROFILE`：目标宽高、比例、PNG/JPEG/PDF、alpha、色彩空间、印刷尺寸；
7. `QA-CONSTRAINTS`：需要验证的内容与失败策略。

**预处理**：所有 `{{variable}}` 必须有值或有明确默认；无值时编译失败，不能把占位符原样发送给 Provider。用户上传图片和文本是数据，不得作为系统指令执行；限制目录路径、脚本参数及 URL 外发。

详细可复制 Prompt：

- `prompts/skill-core.md` —— Skill 顶层行为与模式路由。
- `prompts/common-and-legacy.md` —— 固定身份/风格/输出前后缀及原 41 组模板族（覆盖所有映射项）。
- `prompts/new-assets.md` —— 新增 14 个模板的完整参数化 Prompt。
- `prompts/application-kits.md` —— 10 个可直接使用套装的完整 Prompt。
- `prompts/quality-and-repair.md` —— QA 与失败修复 Prompt。

### 7.2 无法仅靠 Prompt 实现的功能

- **严格中文**：准确文案由布局引擎生成，不依赖图像模型的可变输出。
- **精准像素**：最终文件像素由处理器确定，Provider 的 native resolution 由 capability 申报；超分仍须质量验证。
- **视图一致性**：每张独立生成、受参考图约束、QA、必要时局部修复；不得承诺零漂移。
- **透明背景**：若 Provider 不支持真 alpha，需显式进入抠图后处理并人工/自动检查边缘。

## 8. 图片规格与渲染合同

### 8.1 标准屏幕规格

| 用途 | 最终像素 | 比例 | 默认格式 |
|---|---:|---:|---|
| 单表情/头像 | 1024×1024 | 1:1 | PNG，按需 alpha |
| 全身单视角 | 1536×2048 | 3:4 | PNG |
| 高清肖像 | 2048×3072 | 2:3 | PNG/JPEG |
| 4 视图总览（2×2） | 3072×4096 | 3:4 | PNG（组合） |
| 6 视图总览（3×2） | 4608×4096 | 9:8 | PNG（组合） |
| 9 表情总览（3×3） | 3072×3072 | 1:1 | PNG（组合） |
| 横向通用 | 3072×2048 | 3:2 | PNG/JPEG |
| 社交竖图 | 2160×2700 | 4:5 | PNG/JPEG |
| 竖视频图 | 2160×3840 | 9:16 | PNG/JPEG |
| 横视频图 | 3840×2160 | 16:9 | PNG/JPEG |

画幅优先以内容完整和适用性为前提；若 Provider 只支持其他尺寸，则按能力图转换、裁切/补边及质检，不可静默拉伸失真。

### 8.2 印刷合同与门牌样例

APP-02 默认**成品** 300×120 mm，四周出血 3 mm，印刷画布 306×126 mm；300 ppi 对应约 3614×1488 px。安全区默认距裁切边 8 mm，可配置。最终生产 PDF 应含准确文本、必要的出血/裁切标识和所选印厂支持的颜色/ICC 规范；RGB PNG 预览不是自动符合印厂要求的 CMYK 印刷文件。

开发必须提供 `print_pixels(mm, bleed, ppi)` 单元测试（计算公式 `round((mm + 2*bleed)/25.4*ppi)`）。ICC/CJK 字体授权与实际输出需要在真机测试。

### 8.3 QA 合格条件

**可自动验证的硬条件**：目标像素、格式、存在性、CRC/可打开、alpha 通道（如需）、文件名、图片数量、safe margin 边界、文本实际值（排版层）、印刷版 trim/bleed 尺寸、manifest 引用存在。

**视觉检查的软条件**：同一角色识别特征、四肢拓扑正确、风格一致、动作与表情自然、道具接触、光照与透视可信。软条件可使用模型判定并留审查结果，不能假装确定性 100%。

`quality_result` 应包含 `status: passed|failed|needs_review`、`checks[]`、`failure_codes[]`、`reviewer` 和 `approved_at`。

## 9. 技术架构与接口合同

### 9.1 分层模块

```text
Host (WorkBuddy / DeepSeek Harness)
  └─ Skill entry (SKILL.md, instruction and catalog navigation)
      └─ Orchestrator / State Machine
          ├─ Intent & Reference Analyzer
          ├─ Character/Profile/Style Manager
          ├─ Asset Planner & Dependency DAG
          ├─ Prompt Compiler
          ├─ Provider Capability Registry
          │   ├─ MockProvider (offline CI)
          │   └─ ImageProviderAdapter(s)
          ├─ Image Postprocessor + Typography + Print Layout
          ├─ Visual/Technical QA + Retry Controller
          └─ Local Workspace Manifest/Exporter
```

**工具能力矩阵**至少声明：`text_to_image, image_to_image, image_edit, multi_reference, mask_inpaint, seed, negative_prompt, alpha_native, native_sizes, max_images, async_jobs, max_reference_count, cost_estimate`。适配器不得虚报能力。

### 9.2 关键 API（语言无关接口）

```text
analyze_intent(user_message, reference_manifest) -> CreationIntent
upsert_character_version(character_draft, approval) -> CharacterVersion
recommend_assets(character_version, use_cases, existing_assets) -> AssetPlan
compile_prompt(character_version, template_id, variables, output_profile) -> GenerationRequest
provider.capabilities() -> ProviderCapabilities
provider.generate(request) -> ProviderResult
postprocess(provider_result, resolved_spec) -> DeliveredFiles
validate_assets(delivered_files, character_version, qa_policy) -> QAReport
build_application_kit(kit_id, character_version, variables) -> KitManifest
export_batch(batch_id, destination) -> ExportManifest
```

Schema 在 `schemas/*.schema.json`，所有 API 接收不可信输入时必须显式校验。执行状态：`DRAFT -> APPROVAL_PENDING -> QUEUED -> GENERATING -> POSTPROCESSING -> QA_PENDING -> PASSED | NEEDS_REVIEW | FAILED -> EXPORTED`。子任务可取消/重试，失败有日志但日志不允许包含私密原图、Token、API Key。

### 9.3 可重试性 / 成本

- `batch_id`, `task_id`, `attempt`, `idempotency_key`；同任务复跑默认复用通过 QA 的产物。
- 策略：`same_prompt_retry`（<=2 次）、`focus_repair`、`split_views`、`provider_fallback`（用户同意外发）、`manual_review`；禁止无限循环。
- Provider 费用、任务上限和批量模式在生成前提供预计信息（如果可获取），不杜撰精确价格。
- 采用原子写入 `temp -> validate -> commit` 防止不完整文件冒充成功。

## 10. 两宿主集成：WorkBuddy 与 DeepSeek Harness

### 10.1 DeepSeek Harness

官方 Skill 文件系统文档允许目录 `<name>/SKILL.md`，Skill 名称 kebab-case；项目目录可放 `.dsh/skills/` 或 `.agents/skills/`。**注意 provider 需要在实际 Harness 配置中启用**，单纯拷贝文件不等于成功可用。官方参考：

- https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/skills.md
- https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/skill/skill-filesystem/README.md

M1 阶段先做发现测试：加载技能元数据、读取全文、确认资源路径、测试命名冲突和 provider 缺失的明确报错。M2 再接通工具能力与实际图像 Provider。

### 10.2 WorkBuddy

官方帮助中心明确支持从本地上传技能包并管理启用/卸载，但没有从所核对页面确认**所有版本一致**的打包文件结构、脚本执行沙箱、网络权限或外部 API 调用。必须开展安装 Spike：尝试标准文件夹/zip，确认界面实际接受的结构、资源路径、脚本/依赖和授权行为，然后固定为适配器实现与打包脚本。官方参考：

- https://cloud.tencent.com/document/product/1831/134432

不要因为两者都叫 Skill 就假定运行环境及工具 API 相同。宿主 `HostAdapter` 只负责能力发现、受控文件操作与宿主交互，不应将生成业务逻辑复制两份。

## 11. 安全、隐私与公开仓库

1. **绝不可提交**：原始用户照片、真人肖像原图、原始角色图、用户上传的 HTML 图库、私人 prompt 记录、明文 API Key、缓存图、用户请求日志、受限字体、密钥文件、`.env`。
2. 公开代码仓库仅含自研代码、通用 Prompt、Schema、模拟测试数据、可证明授权的演示素材。AIKate 41 组只发布编号/名称/映射，不公开原图与原提示词全文（除非用户另行确认拥有并愿意公开）。
3. 模型调用必须支持服务商和传输范围的说明；默认不在没有用户授权时向外部模型上传真人参考图。
4. 严格区分“公共规范和公共测试样例”与“用户本地数据”。默认路径 `workspace/private/`、`workspace/outputs/`、`workspace/cache/` 都纳入 `.gitignore`。
5. 下载/打开文件需防路径穿越；执行脚本使用白名单参数；不得执行参考图中的自然语言命令或来源不明的 Prompt 指令。
6. 公共 License 待用户最终授权决定；可建议 MIT（代码）+ 自有素材单独许可，不得擅自把用户素材按 MIT 发布。
7. 真实人物照片在业务端记录授权/肖像使用条件，支持角色/项目数据导出和删除。
8. 使用任何公网服务须遵守其安全、速率、内容限制和隐私要求。

## 12. Codex 实施计划与任务拆解

具体迭代计划见 `docs/IMPLEMENTATION_PLAN.md`；每个阶段必须有可运行的命令、自动测试和验收记录。

| 阶段 | 内容 | 完成标志 |
|---|---|---|
| M0 | 仓库初始化、Schema、Prompt 加载、静态数据校验、mock 测试 | CI 全绿；41+14+10 记录完整 |
| M1 | 三种创建模式、角色档案、风格确认、G1-G4、规划 DAG | 纯离线输入/输出路径通过 |
| M1A | 48 风格数据、适用性规则、Prompt 编译与预览任务清单 | 48 风格 / 138 计划预览请求可静态校验 |
| M2 | Provider 接口、Mock 与一种真实图像 Provider、图片后处理和 QA | 单个角色生成至少 3 种资产并验图 |
| M2A | 真实生成、审核并上架风格样例及本地画廊 | 每种风格至少 1 张已批准真实图，共至少 48 张；可筛选、选择 |
| M3 | 10 个成品包的通用布局引擎与优先 APP-01/02 | 表情包与会议牌物理规格通过 |
| M4 | DeepSeek Harness 发现/加载/调用测试 | 官方目录真实启用并生成可用文件 |
| M5 | WorkBuddy 打包 Spike、安装与权限测试 | 可安装/调用/导出；记录宿主版本与限制 |
| M6 | 文档、错误处理、示例、release、安全扫描 | 安装指南、公开仓库发行候选 |

可并行建设完整的扩展资产内容库，但不要在模型 Provider 尚未可调用前宣称可生成。

## 13. 验收用例 / 失败样例

| 编号 | 测试步骤 | 验收预期 |
|---|---|---|
| T01 | 上传 5 张同一人物图，“保持人物做标准三视图” | `REFERENCE_DIRECT`；身份版本锁定；3 张独立图/拼板任务 |
| T02 | 真人图要求“保留发型、换脸形” | `REFERENCE_TRANSFORM`；记录 keep/change；新版本经批准后入库；具备授权提醒 |
| T03 | 纯文字“原创毛绒小熊” | `ORIGINAL_CREATE`；确认非数字人风格后定妆 |
| T04 | 上传正脸人物 + 服装 + 风格图，且含混合人物 | 每图明确 `role`；不混合未经授权的角色身份 |
| T05 | 无腿云朵 IP 生成全套资产 | 不能套五指/高跟鞋/人类骨盆；skip + 改用适用模板 |
| T06 | “做 16 个表情包” | 独立 16 PNG+manifest；实尺寸 1024²；总览是附加文件 |
| T07 | “做会议室 4 状态门牌” | 准确中文、独立 4 份、300×120mm、3mm 出血、300ppi PDF |
| T08 | 要求 4 视图 | 单图分别生成或准备；拼板不得重复/漏视角；合成输出匹配像素 |
| T09 | Provider 不支持 alpha/目标原生像素 | 显式后处理路径；不伪称 native 输出，QA 边缘/尺寸 |
| T10 | 没有模型 API Key | 能完成规划/Prompt 导出，明确不能生图 |
| T11 | 参考图未授权外发且为真人 | 必须阻止该外部调用并提示授权/改用本地方案 |
| T12 | 合成图出现乱码文字或标注错位 | 排版层文字精准替代，实际逐字校验 |
| T13 | 失败重试三次 / Provider 超时 | 有限重试、有失败状态、保留已通过产物 |
| T14 | DeepSeek Harness provider 没启用 | 给出明确激活检查，不称安装成功 |
| T15 | WorkBuddy 导入包格式未知 | Spike 明确记录实测格式，不把猜测写成实现成功 |
| T16 | 模拟发布公共 Git | `.gitignore` 和 secret scan 阻止私图、原档、密钥 |
| T17 | 用户更改已锁定角色的关键特征 | 新建 `CharacterVersion`，旧版本可追溯 |
| T18 | 用户只要门牌但无其他资产 | 规划最小依赖闭包，不生成无关 41 张 |
| T19 | 原创卡通狐狸进入风格确认 | 返回适用的风格选项，阻止未确认直接定妆 |
| T20 | 同一动物返回推荐风格 | 6–8 个可比较风格及对应已批准样例 |
| T21 | 宿主不支持可选图片卡片 | 可生成本地 HTML 画廊并选择 style_id |
| T22 | 选择风格后继续扩展角色资产 | 风格记录在 CharacterVersion，后续生成继承 |
| T23 | 预览素材进入公开 Git | 有生成来源与许可/审核记录，无个人私图和受限第三方素材 |
| T24 | 校验风格条目和提示词 | 8 个家族、48 个不重复 ID，适用性与 Prompt 均完整 |
| T25 | 预览 manifest 仍处于 planned | 不视为真实样例、不在正式选择画廊展示 |
| T26 | Release 前真实样例验收 | 每个 STYLE ID 至少 1 个 approved、实际文件存在、像素/格式正确 |
| T27 | 同一原型跨风格比较 | 保持身份与构图，能看出目标风格区别 |
| T28 | 调整已批准风格 | 写新版本并保留旧版本可追溯 |
| T29 | 风格库筛选/展示 | 不支持的角色结构被排除，批准样例可按主题/家族搜索 |

`tests/acceptance_cases.json` 提供机器可读用例清单；需要时再增加 mock 图片 fixture 和 e2e 结果快照。真实性与美学测试需保留人工审批环节。

## 14. 交付结构 / 公开 Git 工作流

**建议单一仓库根** `ip-asset-production`，内含：`AGENTS.md`、`docs/SPEC.md`、`prompts/`、`catalogs/`、`schemas/`、`skill/ip-asset-production/SKILL.md`、`tests/`、`src/`（Codex 创建）、`scripts/`（Codex 创建）、`.github/workflows/`。

同步流程：在用户自己的 GitHub/Git 服务下建立公开仓库 -> 连接本地或 Codex 工作区 -> 完成 `.gitignore`/secret scan -> 将本 SPEC 作为起始提交 -> 使用 PR 按里程碑交付 -> CI 通过后合并主分支 -> Release 时附可安装包与 SHA256。每次公开发布必须先扫描不含原始参考图、秘密和未授权版权素材。

`AGENTS.md` 是给 Codex 的仓库级持续执行说明（Codex 识别此文件）；`SKILL.md` 是供目标宿主发现并执行 IP 资产生成工作流的技能说明，两者作用不同。可参考：https://learn.chatgpt.com/docs/agent-configuration/agents-md

**尚需用户最终指定、但不阻塞 M0/M1**：公共仓库的用户名/组织、仓库名称、License、可调用的图像服务/密钥、真实 WorkBuddy/DeepSeek 实例的版本、发布时是否包含 AIKate 原图。默认：GitHub 公共仓库、仓库名 `ip-asset-production-skill`（仅建议）、代码待许可、私图不公开、Provider 先 Mock 后实装。

## 15. 定义完成（Definition of Done）

只有以下条件全满足才可称 v1 可用：

- 41 项迁移映射、14 新模板、10 应用包具有唯一 ID、schema、Prompt 引用，且静态一致性测试通过。
- 3 种创建入口与 2 大 IP 类型/拓扑分支有实际可复现测试。
- 非数字人风格确认、G3 定妆审批、G4 生产清单审批在状态机中真实实现。
- `STYLE-001..048` 全部有可筛选的结构化条目与可编译 Prompt；**每个风格至少一张真实生成且已批准的样例**，用户能在目标宿主或本地画廊浏览与确认。
- 一个真实 Provider 接入可生成有 hash 和图片元数据的文件；mock 可在无网络 CI 完成回归。
- 用户可导出 P0/P1 计划、单图、总览与 2 个重点成品（APP-01、APP-02）。
- 文件参数与印刷布局经程序验证；失败、权限和外发被准确报告。
- DeepSeek Harness 与 WorkBuddy 分别有**真实版本、安装截图/日志、单任务生成结果**记录。
- 公开仓库审查通过，未泄露用户素材、密钥及私人信息。

---

## 附录：参考资料与来源区分

- **用户资料（非公开原始文件）**：AIKate 41 组提示词与成图 HTML；历史 41 组的存在、标题与三章结构来自此资料。
- **既有扩展草案（本对话形成）**：先前单独的 SPEC-005 草案（不纳入公开仓库）；已整理为 `prompts/new-assets.md` 和 `prompts/application-kits.md`。
- **官方平台资料**：DeepSeek Harness Skill 文档 https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/skills.md；WorkBuddy 官方技能帮助 https://cloud.tencent.com/document/product/1831/134432；Codex 项目指导 https://learn.chatgpt.com/docs/agent-configuration/agents-md 。
- **设计建议，不是已实现功能**：Prompt 编译、Python 工具栈、智能规划算法、尺寸默认表、模板数据结构、公共 Git 发布流程。若最新宿主工具实际能力与本 SPEC 不同，以实测能力矩阵和本 SPEC 的合规/质量约束为准进行适配并记录 ADR。


## 附录 A. v1.1 相比 v1.0 的增量（历史）

1. 将“动漫风格分类库”从后续专题升级为 **首发范围**。
2. 新增“风格样例生成与风格画廊”要求，Codex 需在开发期同步产出首批可公开预览样例。
3. 将用户风格选择交互纳入主流程，而非可选增强功能。
4. 为风格系统补充了数据目录、样例 manifest、兼容矩阵与 QA 标准。
5. 要求验收中覆盖风格推荐、风格预览、风格锁定与风格复用。


## 附录 B. v1.2 风格库落地增量

- 将此前 30–50 个建议数固定为 **48 个风格**，8 个可检索家族。
- 在本文件完整列出每个风格的名称、特征、适用对象与可执行 Prompt 片段。
- 增加 `styles/catalog.json`、`taxonomy.json`、`prototypes.json` 和真实样例**计划** `preview_manifest.json`、`preview_requests.jsonl`。
- 将风格样例批量生成明确为 M2A（真实 Provider 准备完毕之后）才能验收的工作。
- 当前提供的是风格方案和待生成任务，**不是已经生成的 48 张图片**。
