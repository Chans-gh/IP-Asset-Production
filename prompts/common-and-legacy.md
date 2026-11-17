# COMMON-LOCK、COMMON-OUTPUT 与 AIKate 41 条记录的通用模板族

## PROMPT: COMMON-LOCK

```text
你正在生成一个已审批 IP 角色的标准视觉资产。角色 ID={{character_id}}，批准版本={{character_version}}；类型={{ip_type}}；形体结构={{body_topology}}；视觉风格={{style_profile}}；主体及关键附属结构={{identity_anchors}}；固定颜色与材质={{palette_and_material}}；参考图清单={{reference_manifest}}。务必保持经审批的身份锚点。仅可更改={{allowed_changes}}。禁止不同人物身份混合、不符合拓扑的手脚部件、人类规范强加到动物/拟人物体、擅自增加Logo或配饰。人物写实风格保留可信肤质与人体结构；动漫与非人形风格遵循已确认的线条、材质和比例，不强加写实毛孔或九头身。背景={{background}}，光照={{lighting}}，镜头={{camera}}。
```

## PROMPT: COMMON-OUTPUT

```text
交付资产类别={{asset_template_id}}，输出变体={{output_variant}}，最终尺寸={{width_px}}×{{height_px}} 像素，画幅={{aspect_ratio}}，文件格式={{format}}，颜色模式={{color_mode}}，透明背景={{alpha_required}}，安全留白={{safe_margin}}。角色必须完整且位置正确，不裁掉重要结构。独立图片优先，总览拼板由程序合成；真实输出规格由工具验证。准确文字={{exact_text}}、标注={{annotations}} 须由布局程序叠加，不准让生成模型猜测或伪造尺寸与汉字。若模型原生能力不足，记录实际原生尺寸、后处理步骤与质量检查结果。
```

## PROMPT: CANONICAL

```text
使用 COMMON-LOCK、STYLE-BRANCH、COMMON-OUTPUT。为待批准角色生成一张定妆候选图（G3）：完整单角色、自然站姿或其形体的标准姿态，正面或三分之四正面，身份锚点={{identity_anchors}} 全部清晰可见，配色={{palette_and_material}}。角色描述={{character_brief}}。简洁中性背景，主体居中、四周留白，不添加文字、Logo 或水印。该图只是候选，用户明确批准后才成为不可变的角色版本。
```

## PROMPT: STYLE-BRANCH (仅选择一个匹配分支)

```text
DIGITAL_HUMAN：写实数字人，按批准的脸型、年龄印象、五官、肤色、发型、体型和摄影表现进行一致性控制。不要将艺术风格误切为动漫。
ANIME_HUMAN：按批准的二维/三维动漫造型、头身比例、轮廓、描线、上色法则保持一致，不强制真实毛孔、真实人体测量或摄影棚光照。
CARTOON_ANIMAL：按角色物种、肢体数、耳尾翼爪、纹理花色与拟人程度生成；四足角色不强制双脚站立或人类手势。
ANTHROPOMORPHIC_OBJECT：保留物体本体轮廓、材质及功能识别特征；仅使用档案中批准的脸、手、脚等拟人部件。
FANTASY_OR_CUSTOM：以批准拓扑和身份锚点优先，允许非标准生物结构；不要将它们误判为人体缺陷。
```

## 原档案对应模板族（以模板变量渲染，不保留写死的 AIKate 参数）

### BASE_VIEW — 标准视图／三四／六视图
```text
使用 COMMON-LOCK、STYLE-BRANCH、COMMON-OUTPUT。为角色生成 {{views}} 的独立正交或明确指定镜头角度，视角必须可辨、主体同一尺度，保证正、侧、背、斜视角的颜色、结构、衣装/表面纹理一致。严格的背面视角不出现正脸，四足/无肢体角色使用其自身正确姿态。每视角独立输出 {{single_width}}×{{single_height}} PNG，然后合成版式为 {{contact_sheet_grid}} 的总览板；标签由排版层负责。优先使用简洁中性背景。
```
映射：`foundation-01/03/04/06/07/08`、`complete-02/05/06`。其中 `complete-05` 作为身份锁定视图的特殊子模板，加入面部特征对照区域。

### BASE_DETAIL — 面部及识别部位精细图
```text
使用 COMMON-LOCK、STYLE-BRANCH、COMMON-OUTPUT。对 {{feature_regions}} 生成清晰局部近景或多个视角，保持结构和颜色，不增添未设计的细节。对数字人强调真实骨相与肤质，对动漫强调已批准绘画比例，对动物/物体展示鼻口、喙、触角、尾部或其他有定义的关键特征，不强制人类五官。需标注时交由后期布局合成。
```
映射：`detail-01..04`。

### BASE_EXPRESSION — 表情九宫格及情绪系列
```text
使用 COMMON-LOCK、STYLE-BRANCH、COMMON-OUTPUT。根据 {{emotion_list}} 分别生成清晰区分的独立表情图；情绪强度={{emotion_intensity}}。所有图保持相同主体范围、身份锚点与风格。无嘴/抽象角色按既定可表现情绪的元素（眼睛、体态、轮廓、符号）表达，不擅自创造人类嘴巴。单张 {{single_width}}×{{single_height}} PNG，网格合成及文字标记在后处理完成。
```
映射：`complete-01`、`detail-15..16`。

### BASE_POSE — 常用动作／手势／头颈动作
```text
使用 COMMON-LOCK、STYLE-BRANCH、COMMON-OUTPUT。分别生成 {{pose_list}}，画面展示角色整体或 {{focus_region}} 的清晰动作，保持身份、比例、支撑关系、关节拓扑。若无手、脚、颈部则使用其自然可行的动作表达，不得人为增加身体部位。各动作单图输出，禁止单个肢体姿态错误通过重复角色掩饰。
```
映射：`complete-03/04`、`detail-11/12/17/18`。

### BASE_STRUCTURE — 解剖、局部手足爪翼结构
```text
使用 COMMON-LOCK、STYLE-BRANCH、COMMON-OUTPUT。根据 {{body_topology}} 和批准的 `parts_manifest` 渲染 {{requested_parts}} 的正面、背面与必要旋转视角；仅生成真实存在的部位。人形遵循相应手足/身体结构；动物遵循爪、蹄、翼、尾、触角等批准形体；无肢体角色应返回 SKIPPED_NOT_APPLICABLE。标注、尺寸、数值必须来自已批准的角色参数并由外部排版叠加。
```
映射：`detail-05..10`、`detail-19..20`。

### BASE_OUTFIT — 服饰、鞋履和造型适配
```text
使用 COMMON-LOCK、STYLE-BRANCH、COMMON-OUTPUT。为 {{character_id}} 生成 {{outfit_or_accessory}} 的正面、侧面和背面适配参考。仅在角色具备相应可穿戴/可附着部位时启用。保持形体结构、服饰材质和配色一致；可替换鞋履，但不能让无脚角色生成人类高跟鞋。各视角独立单图输出，必要时输出独立道具特写。
```
映射：`foundation-02`、`complete-07..09`、`detail-13/14/21..24`。

### BASE_PROFILE — 角色资料卡与介绍
```text
使用 COMMON-LOCK、STYLE-BRANCH、COMMON-OUTPUT。生成含可识别角色图、配色示例、标志性姿态的角色介绍页面底图，预留名称、故事、性格标签与品牌说明区域。所有事实字段读取 {{approved_profile_fields}}，无事实基础的信息标记为用户待确认，不要虚构身份资料。准确文字和色值使用后期排版程序添加。
```
映射：`foundation-05`。

## 41 条来源的变体映射

详情见 `../catalogs/legacy_41_mapping.json`。对 `detail-02/04/06/08/10/12/14/16/18/20/22/24` 使用 `annotated`，对应奇数使用 `clean`；这两类是输出变体，不是两种模型能力。其余历史资产按 `legacy_id` 选定模板族并传入场景/造型参数。
