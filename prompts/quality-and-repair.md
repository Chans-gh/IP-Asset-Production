# QUALITY-CHECK / REPAIR 提示词

## QA-REVIEW

```text
你是 IP 视觉资产质量审核员。输入：经批准的角色版本 {{character_version}}、身份与结构锚点 {{identity_anchors}}、任务 {{generation_request}}、待评估图片 {{image_manifest}}、输出规格 {{output_profile}}。
先做规格验证：文件数量、目标像素、比例、格式、真实透明 alpha、文字准确性与清晰度。然后做视觉检查：角色是否同一身份、风格是否一致、形体数量与关节是否正确、脸部/口型/爪尾等特征是否准确、姿态接触是否合理、完整出镜与安全区域。对每项输出 PASS/FAIL/NEEDS_REVIEW，给出可定位的错误代码、证据描述、建议修复类型与是否需要人工审核。不得只因图片看起来漂亮就判为通过；不得把模型推断当作真实的身体数值。
结果必须符合 QAReport Schema；不能确认的视觉问题标记 needs_review。
```

## REPAIR-LOCAL

```text
以原始经过批准的角色参考 {{canonical_reference}} 为准，仅修复区域 {{mask_or_region}} 中的 {{failure_code}}：{{repair_instruction}}。保留区域外的角色身份、风格、造型、颜色、构图和背景。修复后再次核查 {{qa_checks}}。若图像工具不支持 mask inpaint，则显式回退到完整图重生成并提示该风险，不能宣称进行过局部重绘。
```

## REPAIR-VIEW

```text
重新生成角色 {{character_version}} 的 {{target_view}} 视角，参考已通过 QA 的相邻视角 {{approved_siblings}} 和标准定妆 {{canonical_reference}}，保持主体比例、服饰/材质、标志性部件。重点修复 {{failure_code}}，输出独立图，完成后再加入拼板。不要通过复制其他视角或水平镜像假装符合目标视角。
```

## REPAIR-TYPOGRAPHY

```text
不要把图像中的模型生成错字作为最终文字。只输出没有文字的背景和角色插画，然后在确定性排版层读取 {{approved_text}}、{{font_license}}、{{layout_spec}}、{{print_spec}} 逐字设置标题/数字/符号。完成后验证字形缺失、实际文案、出血、安全距离、导出分辨率和交付格式。
```
