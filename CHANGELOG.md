# Changelog

## [Unreleased] — M0 规范固化与仓库基础

### 新增
- Python 包 `src/ip_asset_production`（Python ≥ 3.11）与 `pyproject.toml`；`ruff` + `mypy --strict` + `pytest`。
- `SchemaRegistry`：8 个 JSON Schema 的加载、元校验（Draft 2020-12）与实例校验。
- 运行时契约模型 `models.py`：`GenerationRequest`（拒绝未替换的 `{{变量}}`）、`OutputSpec`、`ReferenceImage`（缺省 `private_local`）、`ProviderCapabilities`、`GenerationResult`（`passed/exported` 必须有真实文件）。
- Provider 层：`ImageProvider` 协议、`check_request_allowed`（G4 审批、外发拦截、参考图能力上限）、`choose_native_size`（只报告真实原生尺寸）、`CapabilityRegistry`（默认仅离线 Mock，外部适配器需显式开启）。
- `MockProvider`：确定性 PNG、可注入超时、带 mock 标记，不读参考图像素、不联网。
- `workspace.py`：`temp → validate → commit` 原子落盘，文件尺寸 / 格式 / alpha 均为实测值，并计算 SHA-256。
- `units.print_pixels`（SPEC §8.2 公式）。
- `scripts/validate_spec.py`：由起始脚本扩展为 13 项交叉一致性检查（见下）。
- `scripts/secret_scan.py`：公开发布前的隐私 / 密钥扫描（T16 / T23）。
- `.github/workflows/ci.yml`：Python 3.11 / 3.13 矩阵；打 `v*` tag 时运行风格发布门禁。

### 变更
- `scripts/check_style_release.py`：额外拒绝 provider=mock 的条目和带 `ipap:mock` 标记的 PNG（ADR-011）。
- 移除 `spec-validation.yml`，其检查已并入 `ci.yml`。

### M0 验收（IMPLEMENTATION_PLAN）
| 验收项 | 状态 | 证据 |
|---|---|---|
| 规范静态校验 | ✅ | `validate_spec.py`：schemas、asset_catalog、legacy_mapping、legacy_prompt_coverage、source_audit、prompt_coverage、style_catalog、spec_style_table（SPEC 4A.7 与 STYLE_LIBRARY 表格逐字对照 catalog.json）、style_support_files、preview_manifest、preview_requests、acceptance_cases、skill_entry |
| 41 / 14 / 10 唯一且都有 Prompt | ✅ | 同上，另有逐项篡改测试 `tests/unit/test_spec_static.py` |
| 所有 Schema 可解析 | ✅ | `test_schemas_and_models.py` |
| Capability / Provider 协议 / MockProvider | ✅ | `test_providers.py`、`test_workspace.py` |
| 离线 smoke test | ✅ | 无网络、无凭证：MockProvider → 真实 PNG → 可通过 Schema 校验的 `GenerationResult` |
| secret scan 无错误 | ✅ | `test_secret_scan.py::test_real_repository_is_clean` |

契约层已覆盖的验收用例（完整流程在后续里程碑）：T10（无 Provider 时明确报错）、T11（私有参考图禁止外发）、T16、T24、T25、T26（门禁在无真实样例时必然失败）。

### 未完成 / 未验证
- 未接入任何真实图像 Provider；未在 WorkBuddy / DeepSeek Harness 上测试。
- 尚无 Git 远端，GitHub Actions 未实际运行，仅在本地 Python 3.11 下验证。
