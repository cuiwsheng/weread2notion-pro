# 将微信读书划线和笔记同步到 Notion

本项目通过 GitHub Actions 定时同步微信读书书架、划线与笔记到 Notion。

预览效果：[malinkang Notion 示例](https://malinkang.notion.site/9a311b7413b74c8788752249edd0b256?pvs=25)

## 认证方式（WeRead Skills API）

自 `feature/weread-skills-api` 分支起，使用微信读书官方 **Agent API Gateway**（WeRead Skills），不再依赖 Cookie / CookieCloud。

1. 在微信读书 App 中获取 API Key（格式：`wrk-xxxxxxxx`）。
2. 在 GitHub 仓库 **Settings → Secrets and variables → Actions** 中新增：
   - `WEREAD_API_KEY`：微信读书 API Key
   - `NOTION_TOKEN`、`NOTION_PAGE`：与原先相同
3. （可选）阅读时长热力图相关：`HEATMAP_BLOCK_ID`、`NAME`，以及 `vars` 中的颜色配置。

Skills 文档与接口说明见：[weread-skills.zip](https://cdn.weread.qq.com/skills/weread-skills.zip)

## GitHub Actions

| Workflow | 说明 | 默认调度 |
|----------|------|----------|
| `weread.yml` | 书架元数据 + 划线/笔记同步 | 每天 00:00 UTC |
| `read_time.yml` | 阅读时长同步 + 热力图 | 每 3 小时 |

也可在 Actions 页手动 **Run workflow**。

### 分支说明

建议在仓库 `cuiwsheng/weread2notion-pro` 使用分支 **`feature/weread-skills-api`** 进行配置与测试，验证通过后再合并到 `main`。

## 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt

export WEREAD_API_KEY=wrk-xxxxxxxx
export NOTION_TOKEN=secret_xxx
export NOTION_PAGE=https://www.notion.so/...

python scripts/book.py
python scripts/weread.py
python scripts/read_time.py
```

## 已移除的配置

以下 Secrets **不再需要**：

- `WEREAD_COOKIE`
- `CC_URL` / `CC_ID` / `CC_PASSWORD`

## 常见问题

### `Could not find block with ID` / 404

1. **NOTION_PAGE** 必须是包含「书架」「日」等子数据库的**父页面**完整 URL（浏览器地址栏复制），不是单个数据库的链接。
2. 在 Notion 打开该父页面 → 右上角 **⋯** → **Connections** → 添加你的集成（如 WeReadPro）。
3. 子数据库也需在同一集成下可见（通常授权父页面即可）。
4. 若页面 ID 无法遍历，脚本会自动改为按数据库名称搜索；请确保 `BOOK_DATABASE_NAME` 等 `vars` 与 Notion 中数据库标题一致（默认为「书架」）。

## 捐赠

如果你觉得本项目有帮助，欢迎支持作者持续维护。

| 支付宝 | 微信 |
|--------|------|
| <img src="https://images.malinkang.com/2024/03/7fd0feb1145f19fab3821ff1d4631f85.jpg" width="200"> | <img src="https://images.malinkang.com/2024/03/d34f577490a32d4440c8a22f57af41da.jpg" width="200"> |

## 相关项目

- [WeRead2Notion-Pro](https://github.com/malinkang/weread2notion-pro)
- [WeRead2Notion](https://github.com/malinkang/weread2notion)
- [Podcast2Notion](https://github.com/malinkang/podcast2notion)
