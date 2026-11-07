"""子包测试的进程级设置。"""

# 须先于任何 `import httpx` 执行：respx 按 httpx 编写，由此改为拦截 httpx2 发出的请求，见 docs/agents/dependencies.md。
import httpx2

httpx2.alias_httpx()
