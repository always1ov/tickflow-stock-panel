# Fork 改动台账(重建版)

> 本 fork 策略(2026-08-14 重建):基于作者 `upstream/v0.2` 干净代码,**逐个**重加增强功能,
> 每加一个经用户实测验证后再加下一个。数据源铁律:**只用 TickFlow,不引入第三方数据源**。
> 完整历史台账见封存分支 `claude/docker-image-build-trigger-7ryn7i` 的 FORK_NOTES.md(49 条)。

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|------|---------|:---:|---------|
| R1 | **构建/CI 必需项**:GHCR PAT 凭据 + 本分支构建触发;Dockerfile/pyproject README 路径修复(hatchling 构建失败) | `.github/workflows/docker.yml`、`Dockerfile`、`backend/pyproject.toml` | 低 | 不可回退(镜像构建依赖) |
| R2 | **免费多 key 池化(修正版)**:同一 key 字段填多个免费 key(逗号/换行/空格分隔),每 key 各 5 只自选实时额度凑成 5×N,自选超容量时轮转窗口全覆盖。`secrets_store` 加 `get_tickflow_keys()`(`get_tickflow_key` 改为取第一个,单 key 行为不变);`client` 加 `get_realtime_client_pool()`(**仅实时**;付费端点。历史日K的 free-api 路径严禁用池——免费 key 打付费端点会被拒,此为旧版 #47 事故教训);`preferences.get_realtime_watchlist_symbols` 解除 5 只截断;`quote_service._fetch_watchlist_quotes` 池轮询+轮转窗口+按 key 独立限速;Keys 页输入提示。⚠️ 多免费 key 池化可能违反 TickFlow ToS,用户知情自担 | `backend/app/secrets_store.py`、`backend/app/tickflow/client.py`、`backend/app/services/preferences.py`、`backend/app/services/quote_service.py`、`frontend/src/pages/settings/Keys.tsx` | 中(改上游 key/行情层) | `git checkout upstream/v0.2 -- <上述文件>` |
