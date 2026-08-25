<!-- SILVER_SHOWRUNNER_READ_MODE: MODULAR_ONLY -->
<!-- RUNTIME_ROUTE_REGISTRY: schemas/runtime_route_registry.json -->

# Silver-Showrunner-alpha.7-Master v1.1.3

> 不只会生成画面：我们让 AI 先学会当总导演。

唯一阅读入口：`SKILL.md`。本地工具只执行 `运行银幕总控.cmd`，不直接调用 Python，也不读取 helper 源码。

- 模块模式：读 `SKILL.md`，按路由只加载当前模块；不得同时读取 ONEFILE。
- ONEFILE 模式：只读发布包外的一个剖面；不得同时读取模块文件。
- 默认 `MANGA_CORE`；纯文字 Pilot 用 `TEXT_ONLY_ECO`，其余按需选择。
- `.skill / ZIP` 为运行包：含正式运行文件，不含测试、构建工具、版本史或 ONEFILE。

用户界面名称为“Silver-Showrunner-alpha.7-Master v1.1.3”；内部版本 `1.1.3`。
