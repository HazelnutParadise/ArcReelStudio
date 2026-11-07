# WebUI Server Package

# 须先于任何 `import httpx` 执行：respx 与仍按 httpx 编写的依赖（方舟 SDK）由此拿到 httpx2 的类，见 docs/agents/dependencies.md。
import httpx2

httpx2.alias_httpx()
