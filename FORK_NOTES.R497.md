# R497 — 维表还没刷新过时查名字不再抛错

| # | 改动 | 涉及文件 | 冲突风险 | 单独回退 |
|---|---|---|---|---|
| R497 | 给转折页取数时撞见: KlineRepository 的 _name_map_cache 只在三张维表刷新成功(try 块里)或 clear_cache 时才被赋值, __init__ 里没有。新装还没同步维表、或维表刷新抛错时, 第一次 get_name_map 就 AttributeError, 今日总览(转折页顶部那份)整页 500。在 __init__ 里补一行初始化为 None, 行为与刷新过但为空一致(返回空映射)。新增 test_name_map_init.py 1 条, 在原代码上红、修后绿; 全量验证通过 | backend/app/tickflow/repository.py; backend/tests/test_name_map_init.py | 低(作者 repository.py 的 __init__ 加一行) | 可以: git revert 本提交 |
