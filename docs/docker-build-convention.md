# 镜像构建约定

> 用户定的规矩，**以后这个项目的构建都按这份来**。原话:「以后这个项目构建都要
> 按照这个要求」。动 `Dockerfile` / `.dockerignore` / `.github/workflows/docker.yml`
> 之前先读这份，改完逐条对照自查。

目标只有三个词: **体积更小、构建更快、缓存更稳。**

## 仓库与技术栈

- 仓库 `always1ov/tickflow-stock-panel`，分支 `claude/upstream-clean`（私有）
- 前端 React + Vite + **pnpm 9.10.0**（`frontend/package.json` 的 `packageManager` 声明）
- 后端 FastAPI，依赖用 **uv** 管（`backend/pyproject.toml` + `backend/uv.lock`）
- 架构: **单容器**。前端 `dist` 构建完拷进后端 `python:3.11-slim`，FastAPI 同时托管静态资源
- 关键文件: 根目录 `Dockerfile`、`.dockerignore`、`docker-compose.yml`；`.github/workflows/docker.yml`

## 已定位的构建缓慢根因

这几条是用户自己查出来的，**不要重新论证，直接照着改**:

1. workflow 在单台 `ubuntu-latest`(amd64) 上 buildx 双平台，arm64 全程 QEMU 模拟 ——
   前端 `tsc` + `vite` 这类 CPU 密集步骤慢 5~20 倍。
2. `type=gha` 缓存**没设 scope**，默认按分支隔离，`main` 与 `claude/upstream-clean`
   互相不共享。
3. 基础镜像用 floating tag（`node:20-alpine` / `node:20-bookworm-slim` /
   `python:3.11-slim`），上游一动就整层缓存失效。
4. **numba/llvmlite 约 150MB 可裁**: `backend/app/backtest/matrix.py` 第 39-51 行
   对 numba 缺失有 `try/except ImportError` 的纯 Python 降级（`njit` no-op + `prange=range`），
   功能不变、只是回测变慢。
5. 依赖安装带容错 fallback（`pnpm install --frozen-lockfile || pnpm install`、
   `uv sync --frozen "$@" || uv sync "$@"`）—— 会**掩盖 lockfile 漂移**并慢速重解析。
6. npm 安装没加 `--no-audit --no-fund`。
7. `.dockerignore` 漏了 `gui-test-screenshots/`、`assets/`、`.claude/`、
   `community-qr-code.jpg`、`操作说明书.md`、`CONTEXT.md`、`CONTRIBUTING.md`。
8. `Dockerfile` 没有 `HEALTHCHECK`（后端有 `/health`，在鉴权白名单里，免认证）。

## 要求

### P0 —— 最高优先

- `docker.yml` 改**矩阵原生构建**: amd64 用 `ubuntu-latest`，arm64 用 `ubuntu-24.04-arm`，
  两架构并行、各推 digest，再合成多架构 manifest。走
  `docker/build-push-action` 的 **push-by-digest + `docker buildx imagetools create`** 官方模式。
  移除不再需要的 `docker/setup-qemu-action`。
- gha 缓存加**固定 scope**（`tickflow-amd64` / `tickflow-arm64`）并加 `ignore-error=true`，
  让跨分支共享缓存。

### P1

- 基础镜像 **pin 到具体 minor**（如 `node:20.19-alpine`、`node:20.19-bookworm-slim`、
  `python:3.11.11-slim`）—— 版本号以**实际 pull 到的**为准，不要凭记忆写。
- 依赖安装改**严格 frozen**（去掉 `|| install` 容错），npm 加 `--no-audit --no-fund`，
  pnpm 锁 9.10.0。
- 新增 **`STRIP_NUMBA` 构建参数（默认 1）**: `uv pip uninstall numba llvmlite || true`。
  需要 numba 加速时传 `--build-arg STRIP_NUMBA=0`。

### P2

- `.dockerignore` 补上第 7 条那批遗漏项。
- 加 `HEALTHCHECK`: 用 python `urllib` 探 `http://127.0.0.1:3018/health`，
  `interval 30s` / `timeout 5s` / `start-period 30s` / `retries 3`。

## 硬约束

- **不改变任何运行时功能。** numba 用构建参数做成可选、默认裁剪。
- **保留 `Dockerfile` 已有的构建参数与国内镜像源逻辑**: `USE_CN_MIRROR`、
  `INCLUDE_STOCKSDK`、`BACKEND_EXTRAS`、`CODEX_CLI_VERSION` 等，一个都不要删。
- **保留 `docker-compose.yml` 的约定**（镜像直拉 + 环境变量内联 + 相对路径挂载 +
  不带反向代理）—— 那个文件本次不动。
- GitHub runner 在海外，CI 里**仍然传 `USE_CN_MIRROR=0`**。
- 登录 GHCR 用 `secrets.GHCR_PAT`（user-scoped 包，`GITHUB_TOKEN` 不够）。

## 交付物

每次按这份约定改完，要给出:

1. 优化后的 `Dockerfile` 全文，**含中文注释说明每处改动**。
2. 优化后的 `.github/workflows/docker.yml` 全文。
3. **不超过 20 行**的改动清单，逐条说明「改了什么 → 为什么 → 预期收益」。
