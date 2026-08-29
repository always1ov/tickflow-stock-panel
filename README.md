# TickFlow Stock Panel（fork）· Dokploy 部署分支

这是 `always1ov/tickflow-stock-panel` 的**专用部署分支**（孤儿分支，
不含应用代码，只有部署文件，克隆只有几 KB）。应用代码在
`claude/upstream-clean`，镜像由 CI 从那个分支自动构建。

## Dokploy 部署步骤

1. 面板 → 新建 **Compose** 项目 → Provider 选 **GitHub**（或 Git）
2. Repository 选 `always1ov/tickflow-stock-panel`，**Branch 选 `deploy`**
3. Compose Path 保持 `./docker-compose.yml`
4. Environment 页粘贴 `env.example` 内容，改三处：
   - `HOST_IP`：NAS 内网 IP
   - `HOST_PORT`：未占用端口
   - `AUTH_PASSWORD`：首次登录密码（别含 `$`）
5. Deploy。启动预热一两分钟（健康检查已给 120s 预算）
6. 打开 `http://<HOST_IP>:<HOST_PORT>` 登录 → 设置里填 TickFlow key、
   AI 配置 → 数据页点「立即同步」

## 从旧栈迁移(一次性)

旧栈的 `./data` 就是全部家当(密码/keys/自选/策略/操盘手账本/行情数据),
拷过来即完成迁移, 什么都不用重配:

```bash
# 1. 停两边
docker stop tickflow                      # 旧容器
# Dokploy 面板里把本项目 Stop

# 2. 拷数据(源路径改成旧 compose 所在目录; 目标项目目录名以面板实际为准)
mkdir -p /etc/dokploy/compose/<项目目录名>/files
cp -a /旧compose目录/data /etc/dokploy/compose/<项目目录名>/files/data

# 3. 面板 Deploy, 用旧密码登录, 确认自选/策略/数据都在

# 4. 确认无误后, 从旧栈 compose 里删掉 tickflow 服务并 docker rm tickflow
#    (旧容器的 Traefik 标签随之消失, 域名由新容器接管)
```

迁移后 `AUTH_PASSWORD` 环境变量被忽略(密码在旧 data 的 secrets 里),
TickFlow key / AI 配置也全部沿用。

## 数据

挂载 `../files/data:/app/data`（Dokploy 把仓库克隆到 code/，files/ 在旁边，
重新部署只重建 code/，files/ 保留）。TickFlow key、AI key、自选、策略、
AI 操盘手账本、行情数据全在里面。部署完看数据页：出现红色"未挂载持久化卷"
警告说明挂载没生效，先别同步。

## 更新 / 回滚

- **应用更新**：代码推到 `claude/upstream-clean` → CI 自动出新镜像 →
  面板点 Deploy 重拉 `latest`。本分支不用动
- **部署配置更新**：改本分支的 compose/env → push → 若开了 Autodeploy
  (On Push) 自动重部署
- **回滚**：Environment 里 `IMAGE_TAG` 改成 FORK_NOTES.md 存档表的提交号
  （如 `24ce014` = v6 存档）→ Deploy

## 注意

- 若 GHCR 包是私有的：Dokploy → Registry 配 ghcr.io 凭据（PAT, read:packages）
- `TZ=Asia/Shanghai` 别改（盘后 15:30 自动同步靠它）
- 内存限制 4G 起步，数据量涨了往上调
