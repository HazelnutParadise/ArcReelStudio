# ============================================================
# Stage 1: 构建前端
# ============================================================
FROM node:26-slim AS frontend-builder

WORKDIR /build/frontend

# 启用 corepack；pnpm 版本由 frontend/package.json 的 packageManager 字段固定。
# Node 25 起不再内置 corepack，先用 npm 安装固定版本
# 关闭交互式下载确认，否则 docker build 这种非 TTY 环境会卡在
# "Corepack is about to download ..." 直到超时
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN npm install -g corepack@0.36.0 && corepack enable

# 先复制依赖文件，利用缓存（corepack 按 packageManager 字段自动下载对应 pnpm）；
# pnpm-workspace.yaml 存放 overrides 与 catalog，缺了它 --frozen-lockfile 校验不过
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

# 复制前端源码并构建
COPY frontend/ ./
RUN pnpm build

# ============================================================
# Stage 2: 支持 GPU 编码的 ffmpeg
# ============================================================
# 随包 ffmpeg（imageio-ffmpeg）没有编入 NVENC；成片在检测到 NVIDIA GPU 时改用这份
# jellyfin-ffmpeg 静态构建编码，其余媒体处理仍用随包 ffmpeg。版本与校验和随架构固定。
FROM python:3.14-slim AS gpu-ffmpeg

ARG TARGETARCH
ARG JELLYFIN_FFMPEG_VERSION=8.1.3-1
ARG JELLYFIN_FFMPEG_SHA256_AMD64=b86dc023c64a5a9a410e6e3a938a970460214fae78f31c1553c9f88f1c289b6a
ARG JELLYFIN_FFMPEG_SHA256_ARM64=7bc8e8d0986f7f4693f63e9728570f671f07b6e21c05d5465dd7ce461d1631dc

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    case "${TARGETARCH}" in \
    amd64) platform=linux64; sha256="${JELLYFIN_FFMPEG_SHA256_AMD64}" ;; \
    arm64) platform=linuxarm64; sha256="${JELLYFIN_FFMPEG_SHA256_ARM64}" ;; \
    *) echo "不支持的架构：${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/ffmpeg.tar.xz \
    "https://github.com/jellyfin/jellyfin-ffmpeg/releases/download/v${JELLYFIN_FFMPEG_VERSION}/jellyfin-ffmpeg_${JELLYFIN_FFMPEG_VERSION}_portable_${platform}-gpl.tar.xz"; \
    echo "${sha256}  /tmp/ffmpeg.tar.xz" | sha256sum -c -; \
    mkdir -p /out; \
    tar -xJf /tmp/ffmpeg.tar.xz -C /out ffmpeg; \
    rm /tmp/ffmpeg.tar.xz

# ============================================================
# Stage 3: ChatGPT 订阅用的 Codex CLI
# ============================================================
# ChatGPT 订阅经 Codex（app-server）登录与调用。Codex 以 Apache-2.0 发布，用官方的 Linux 静态二进制，版本与校验和
# 随架构固定。Grok CLI 没有允许再分发的许可，不放进镜像：第一次登录 Grok 订阅时由服务按固定版本与校验和下载
# （见 lib/subscriptions/grok_cli.py）。
FROM python:3.14-slim AS subscription-clis

ARG TARGETARCH
ARG CODEX_VERSION=0.166.0
ARG CODEX_SHA256_AMD64=a0bf572d2f93f056c6712a6da348e96078dc84f3885fd7be67807ef389cb3978
ARG CODEX_SHA256_ARM64=94eb707605ec2646b2e05b7edf7c4e7b3ccf02b16237c34ae9beb8cfb7f810a9

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH}" in \
    amd64) codex_arch=x86_64; codex_sha="${CODEX_SHA256_AMD64}" ;; \
    arm64) codex_arch=aarch64; codex_sha="${CODEX_SHA256_ARM64}" ;; \
    *) echo "不支持的架构：${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    mkdir -p /out; \
    curl -fsSL -o /tmp/codex.tar.gz \
    "https://github.com/openai/codex/releases/download/rust-v${CODEX_VERSION}/codex-${codex_arch}-unknown-linux-musl.tar.gz"; \
    echo "${codex_sha}  /tmp/codex.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/codex.tar.gz -C /tmp; \
    install -m 0755 "/tmp/codex-${codex_arch}-unknown-linux-musl" /out/codex; \
    rm -f /tmp/codex.tar.gz "/tmp/codex-${codex_arch}-unknown-linux-musl"

# ============================================================
# Stage 4: 生产镜像
# ============================================================
FROM python:3.14-slim AS production

# 安装系统依赖，并把基础镜像预装的系统包升级到当前仓库版本。
# APT_REFRESH 由 CI 按 ISO 周传入，值变化时本层缓存失效，保证系统包定期刷新
ARG APT_REFRESH=unset
RUN echo "apt refresh: ${APT_REFRESH}" \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl \
    bubblewrap \
    socat \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# 升级基础镜像预装的 pip：依赖全部由 uv 安装、运行时不调用 pip，
# 但 python:3.14-slim 自带的旧 pip 会被镜像扫描器报 CVE，升级以清除这些告警
RUN python -m pip install --no-cache-dir --upgrade pip

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 禁用 Python 输出缓冲，确保日志实时输出到 Docker logs
ENV PYTHONUNBUFFERED=1

# 默认时区，可由 docker-compose / 运行时 -e TZ=... 覆盖
ENV TZ=Asia/Taipei

# 先复制依赖和包元数据文件，利用缓存；workspace 子包作为依赖随这一步安装，源码须先就位
COPY pyproject.toml uv.lock README.md ./
COPY packages/ packages/
RUN uv sync --no-dev --no-install-project

# 复制应用代码
COPY lib/ lib/
COPY server/ server/
COPY alembic/ alembic/
COPY alembic.ini ./
COPY scripts/ scripts/
COPY agent_runtime_profile/ agent_runtime_profile/
COPY public/ public/
# 随包 ffmpeg 的许可证声明（见 NOTICE）随镜像分发
COPY LICENSE NOTICE ./
COPY LICENSES/ LICENSES/

# 复制前端构建产物
COPY --from=frontend-builder /build/frontend/dist/ frontend/dist/

# GPU 编码用的 ffmpeg，路径与 lib/infra/video_encoder.py 的 GPU_FFMPEG_PATH 一致
COPY --from=gpu-ffmpeg /out/ffmpeg /opt/arcreel/ffmpeg-gpu/ffmpeg

# ChatGPT 订阅用的 Codex CLI（PATH 上的 codex）
COPY --from=subscription-clis /out/codex /usr/local/bin/codex

# 构建 commit 由 CI 传入，/health 据此返回运行版本；放在最后，值每次变化也不影响前面的层缓存
ARG BUILD_COMMIT=
ENV ARCREEL_BUILD_COMMIT=${BUILD_COMMIT}

# 暴露端口
EXPOSE 1241

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:1241/health || exit 1

# 启动命令
CMD ["uv", "run", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "1241"]
