# 标准知识图谱静态网站使用说明

本目录用于 GitHub Pages 发布。网站只读取以下两个静态数据文件：

- `docs/data/graph_data.json`
- `docs/data/search_index.json`

静态网站不需要数据库、不需要后端服务、不需要任何外部访问密钥，也不会连接 Neo4j。

## 本地查看

双击打开 `docs/index.html` 即可查看展示页面。若浏览器限制本地 JSON 读取，可以把仓库发布到 GitHub Pages 后访问。

## 发布到 GitHub Pages

1. 将 `docs/` 提交到仓库。
2. 打开 GitHub 仓库的 Settings。
3. 进入 Pages。
4. Source 选择 `Deploy from a branch`。
5. Branch 选择主分支，目录选择 `/docs`。
6. 保存后等待 Pages 部署完成。
