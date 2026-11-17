# Git 公共仓库与用户照片安全

**发布前检查清单**

1. 选择公开仓库所属账号/组织、名称、代码 License、样例素材使用许可。
2. 用户原始 HTML（内嵌 41 张图片）、私人多参考图、Prompt 对话、实际生成结果不可默认公开。
3. 检查 `.env` / API key / token / cookie / 账户地址、凭证路径、真实人脸与专有字体。
4. `git status --short`、`git diff --cached --name-only` 审查已暂存文件，使用 secrets scanner 检查历史及当前提交。
5. 发布任何真人素材需要对应肖像授权、使用范围及平台传输权限。
6. 公开发布使用合成的、可证明已获授权的测试素材；未取得相应授权不发布。
7. 封装发布包时仅包含运行必需文件、安装说明、所需权限、版本与 SHA256；CI 不使用用户个人凭证。

**建议工作流**：`feature branch -> PR -> tests + safety scan -> human review -> merge -> tagged release`。

`git remote add origin ...` 和 push 操作必须由实际获得权限的 Codex 环境/用户完成，本 SPEC 包未连接任何远程仓库，也未代替用户建立仓库。
