# 41 组源资产迁移映射（公开安全版）

> 本表仅公开 ID、模板族与输出变体；原始角色照片、原始提示词以及具体原始标题保留在用户私有档案，不随公共仓库发布。

| 源资产 ID | 通用类别 | Prompt 族 | 变体 |
|---|---|---|---|
| `foundation-01` | A01 | `BASE_VIEW` | clean |
| `foundation-02` | A06 | `BASE_OUTFIT` | clean |
| `foundation-03` | A01 | `BASE_VIEW` | clean |
| `foundation-04` | A01 | `BASE_VIEW` | clean |
| `foundation-05` | A07 | `BASE_PROFILE` | clean |
| `foundation-06` | A01 | `BASE_VIEW` | clean |
| `foundation-07` | A01 | `BASE_VIEW` | clean |
| `foundation-08` | A01 | `BASE_VIEW` | clean |
| `complete-01` | A03 | `BASE_EXPRESSION` | clean |
| `complete-02` | A01 | `BASE_VIEW` | clean |
| `complete-03` | A04 | `BASE_POSE` | clean |
| `complete-04` | A04 | `BASE_POSE` | clean |
| `complete-05` | A01 | `BASE_VIEW` | clean |
| `complete-06` | A01 | `BASE_VIEW` | clean |
| `complete-07` | A06 | `BASE_OUTFIT` | clean |
| `complete-08` | A06 | `BASE_OUTFIT` | clean |
| `complete-09` | A06 | `BASE_OUTFIT` | clean |
| `detail-01` | A02 | `BASE_DETAIL` | clean |
| `detail-02` | A02 | `BASE_DETAIL` | annotated |
| `detail-03` | A02 | `BASE_DETAIL` | clean |
| `detail-04` | A02 | `BASE_DETAIL` | annotated |
| `detail-05` | A05 | `BASE_STRUCTURE` | clean |
| `detail-06` | A05 | `BASE_STRUCTURE` | annotated |
| `detail-07` | A05 | `BASE_STRUCTURE` | clean |
| `detail-08` | A05 | `BASE_STRUCTURE` | annotated |
| `detail-09` | A05 | `BASE_STRUCTURE` | clean |
| `detail-10` | A05 | `BASE_STRUCTURE` | annotated |
| `detail-11` | A04 | `BASE_POSE` | clean |
| `detail-12` | A04 | `BASE_POSE` | annotated |
| `detail-13` | A06 | `BASE_OUTFIT` | clean |
| `detail-14` | A06 | `BASE_OUTFIT` | annotated |
| `detail-15` | A03 | `BASE_EXPRESSION` | clean |
| `detail-16` | A03 | `BASE_EXPRESSION` | annotated |
| `detail-17` | A04 | `BASE_POSE` | clean |
| `detail-18` | A04 | `BASE_POSE` | annotated |
| `detail-19` | A05 | `BASE_STRUCTURE` | clean |
| `detail-20` | A05 | `BASE_STRUCTURE` | annotated |
| `detail-21` | A06 | `BASE_OUTFIT` | clean |
| `detail-22` | A06 | `BASE_OUTFIT` | annotated |
| `detail-23` | A06 | `BASE_OUTFIT` | clean |
| `detail-24` | A06 | `BASE_OUTFIT` | annotated |

## 维护原则

- 原档案共有 41 个 ID：`foundation-01..08` 8 个；`complete-01..09` 9 个；`detail-01..24` 24 个。
- `detail-01..24` 中 12 对标注与无标注归入同一模板的不同输出变体。
- 任何真人身高、体型、发色、衣物、鞋履数字设定都必须读取用户本地批准的 `character_profile`，绝不能嵌入公共通用 Prompt。
- 未来用户若授权公开具体案例，需另行审查素材来源和许可。
