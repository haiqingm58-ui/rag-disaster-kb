# GitHub Actions 部署接入手册

目标：从 GitHub Actions 一键 SSH 到阿里云服务器，执行 `git pull → pip install → systemctl restart → /api/health` 检查。**只通过 workflow_dispatch 手动触发**，避免合入 main 后立刻上线。

## 一、阿里云服务器准备

### 1. 建一个专用部署用户（推荐）

不要直接用 root 跑部署。建一个 `deployer` 用户，加入 sudo 组：

```bash
sudo adduser deployer --disabled-password --gecos ""
sudo usermod -aG sudo deployer
```

让 `deployer` 能免密 restart 应用服务（**仅这一条命令免密**，其他 sudo 仍然要密码）：

```bash
echo 'deployer ALL=(root) NOPASSWD: /bin/systemctl restart rag-fastapi, /bin/systemctl status rag-fastapi, /bin/journalctl -u rag-fastapi *' \
  | sudo tee /etc/sudoers.d/deployer-rag
sudo chmod 0440 /etc/sudoers.d/deployer-rag
sudo visudo -cf /etc/sudoers.d/deployer-rag   # 校验语法
```

让 `deployer` 拥有项目目录的读写权限：

```bash
sudo chown -R deployer:www-data /opt/rag-disaster-kb
sudo chmod -R g+rwX /opt/rag-disaster-kb
```

> 不想做这一步？也可以直接用 `root` 走 SSH，下面密钥的 `ALIYUN_USER` 填 `root`，但安全风险更大。

### 2. 生成部署专用 SSH key

**在本机**生成一对**专门用于部署**的 ed25519 密钥（不要复用日常 SSH key）：

```bash
ssh-keygen -t ed25519 -C "github-actions deploy" -f ~/.ssh/aliyun_deploy -N ""
```

会得到：

- `~/.ssh/aliyun_deploy`：私钥，待会粘到 GitHub Secrets
- `~/.ssh/aliyun_deploy.pub`：公钥，待会拷到服务器

### 3. 把公钥加到服务器

```bash
ssh-copy-id -i ~/.ssh/aliyun_deploy.pub deployer@你的服务器公网IP
```

或手动：

```bash
ssh deployer@你的服务器公网IP
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "<aliyun_deploy.pub 的全部内容>" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

测试免密登录：

```bash
ssh -i ~/.ssh/aliyun_deploy deployer@你的服务器公网IP "echo ok && sudo systemctl status rag-fastapi --no-pager | head -5"
```

应该不需要输入任何密码，输出 `ok` 和服务状态。

## 二、GitHub Secrets / Environment

### 1. 建 Production environment

GitHub 仓库 → Settings → Environments → New environment → 名字 `production`。可选打开 “Required reviewers”（部署前需人工点击 Approve）。

### 2. 加 Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret，加 4 条：

| Secret 名 | 值 |
|---|---|
| `ALIYUN_HOST` | 阿里云公网 IP，例如 `1.2.3.4` |
| `ALIYUN_USER` | `deployer` 或 `root` |
| `ALIYUN_SSH_KEY` | 整个 `~/.ssh/aliyun_deploy` 文件内容，包括 `-----BEGIN` 和 `-----END` 两行 |
| `ALIYUN_PORT` | 22（如果改过 SSH 端口，填实际端口） |

把这些 secret 添加到刚才建的 `production` environment 里（Environment secrets），而不是 Repository secrets，权限隔离更干净。

## 三、触发部署

GitHub 仓库 → Actions → Deploy → Run workflow：

- **要部署的分支或 commit**：默认 `main`，可以填 PR 分支名或具体 commit
- **跳过 pip install**：纯代码变动可勾选，省 30–60 秒；改了 `requirements-server.txt` 必须留 `false`

点 Run workflow，约 1–2 分钟完成。失败会在最后打印 `journalctl -u rag-fastapi` 末尾 80 行。

## 四、典型问题

### Permission denied (publickey)

公钥没有正确加到 `deployer` 的 `~/.ssh/authorized_keys`，或文件权限不对（必须 600）。本机用 `ssh -vvv` 看一遍：

```bash
ssh -vvv -i ~/.ssh/aliyun_deploy deployer@<host>
```

### sudo: a password is required

`/etc/sudoers.d/deployer-rag` 没写或 `visudo -c` 没通过。重新执行第一节第 1 步。

### git pull 报 untracked files would be overwritten

服务器上有人手动改过文件。可以临时 `git stash` 备份，或登录服务器查清楚再决定。workflow 用了 `git reset --hard origin/<ref>`，所以一旦确认服务器没有未提交工作要保留，就会强制对齐远端。

### Health check 一直 502

`journalctl -u rag-fastapi -n 80 --no-pager` 看 traceback。常见：
- `.env` 缺 `DEEPSEEK_API_KEY`
- `assert_production_safety` 拦下了弱密码 / 弱 JWT_SECRET
- venv 里没装 `uvloop` / `httptools`，启动 flag 报错
