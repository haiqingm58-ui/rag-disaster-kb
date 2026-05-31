# 行业标准知识图谱 GitHub Pages 数据包

这个目录可以直接作为 GitHub Pages 的 `docs/` 发布目录使用。

## 文件说明

- `index.html`：知识图谱内容浏览器，可查看标准、章节、条款、术语、要求、指标。
- `network.html`：节点—关系网络图版本。
- `data/graph_data.json`：图谱数据。
- `data/search_index.json`：搜索索引。
- `browser_export_summary.md`：导出说明。

## 本地打开

双击 `index.html` 或在浏览器打开：

```bash
open docs/index.html
```

Windows 可直接双击 `docs/index.html`。

## GitHub Pages 发布

把整个 `docs/` 文件夹复制到你的仓库根目录，然后提交：

```bash
git add docs
git commit -m "add knowledge graph GitHub Pages site"
git push
```

然后在 GitHub 仓库：

Settings → Pages → Deploy from branch → main → /docs → Save

发布后访问：

https://你的用户名.github.io/rag-disaster-kb/

## 注意

这是从当前聊天里已有的导出文件恢复出的基础 GitHub Pages 数据包。
如果要生成更清晰的 showcase 展示型图谱，请让 Codex 基于 `docs/data/graph_data.json` 重新生成 `docs/index.html` 和展示 SVG。
