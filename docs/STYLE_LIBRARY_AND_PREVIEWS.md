# STYLE-007 — 风格分类库与可视化样例生成开发规范

> 版本：1.2.0-draft | 状态：v1 首发范围（计划已制定，真实样例需 Codex 执行）

## 范围与交付

- 风格预设：**48 种，分为 8 个家族**。
- 对外最低验收：**每种风格至少一张真实生成、经 QA 审核通过的预览**。
- 预览目标尺寸：1024×1024 PNG，统一角色原型与场景参数，图中不含文字、水印和 logo。
- 标准原型：动漫青年（HUMAN_PROTO）、橘红狐狸（ANIMAL_PROTO）、奶油色咖啡杯（OBJECT_PROTO）、幻想精灵（FANTASY_PROTO）。前 3 类作为核心预览模板；幻想精灵可在下一轮补齐。
- 仅在所支持的角色类型中生成预览；对不适用的物种结构要跳过或设计适配模板。
- 不使用未经授权的影视人物、商标角色或在世艺术家明确作品作为公开预览。

## 八个家族与 48 项完整清单

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


## 提示词编译

`PREVIEW_PROMPT = PROTOTYPE.subject_en + STYLE.prompt_fragment_en + COMMON_PREVIEW_LAYOUT + STYLE.negative_prompt_en`

其中：

- `PROTOTYPE` 来自 `styles/prototypes.json`；同一主体跨风格的身份特征、姿态、构图尽量保持一致。
- `STYLE` 来自 `styles/catalog.json`；该文件是 48 种风格 Prompt 数据源。
- `COMMON_PREVIEW_LAYOUT`：`centered full-body subject, neutral warm white background, clean square composition, no words, no logos, 1024x1024 PNG output target`。
- 一旦生成特定角色的风格预览，应以用户授权的参考图/已确认角色版本取代标准原型，不能将标准狐狸或咖啡杯原型混入真实用户角色。
- 严格验证输出像素与格式，不得把原生分辨率与后处理分辨率混同。

## 样例生产步骤（Codex）

1. 读取 `styles/catalog.json`，验证 48 个唯一 style_id。
2. 读取 `styles/preview_manifest.json` 的 planned 项，优先选择每个 style 的一张符合适用性的样例；额外样例根据成本逐步生成。
3. 调用具备生成权限的真实 Provider。记录 Provider/Model、原始参数、生成时间和文件 hash。
4. 保持角色基准稳定，只变化风格；发现不适用或生成错误时重试不超过可配置上限。
5. 图片写入 `styles/previews/<subject>/`，实际存在且 QA 合格后再填写 `actual_file` 和状态 `approved`。
6. 校验安全与可再分发性，不可把用户私有图片、受限第三方作品提交公共 Git。
7. 构建 HTML 画廊：按家族、主体与风格关键词搜索，支持大图、Prompt 摘要、选择样式 ID；宿主支持图片消息时优先在对话内展示。
8. 仅展示 `approved` 样例；未通过的条目不可向用户承诺有样例。

## 数量验收

- `catalog`: 48 个条目，8 个组，各 6 条；ID `STYLE-001` ... `STYLE-048`。
- `preview_manifest`: 应包含每个风格至少 1 项计划；正式验收时每个风格至少 1 项 `approved` 且文件真实存在。
- 每个被展示的样例必须可通过 manifest 找到本地实际文件、尺寸、Prompt、生成来源和 QA 记录。
- 可选全覆盖目标为每个风格对应人、动物、拟人物体的适用原型，而不是强制所有条目都能用于所有主体。

## 用户流程

用户创建非数字人 IP → Skill 根据角色种类筛选样式 → 每轮推荐 6–8 个差异明显的视觉样例 → 用户选择/对比 → 绑定 `style_id` 到角色版本 → 生成定妆图及后续资产。

## 实现注意

当前仓库只提供**风格数据、预览任务和 Prompt**，不包含已生成的可展示图片。开发者必须在图像 Provider 可用后执行真实生图与审核。
