---
id: deployment
title: 部署与运维
sidebar_position: 1
update_docs: fact-check
---

# 部署与运维 {#deployment}

本文档说明 ArcReel 的默认部署、PostgreSQL 生产部署、环境变量、数据持久化、升级、备份、恢复、反向代理和故障排查。正式支持边界见 [安全政策](https://github.com/HazelnutParadise/ArcReelStudio/blob/main/SECURITY.md)，完整信任边界见 [安全威胁模型](https://github.com/HazelnutParadise/ArcReelStudio/blob/main/docs/security/threat-model.md)。

## 部署方式选择 {#choose-deployment-mode}

| 场景 | 推荐方式 | 数据库 | 说明 |
|---|---|---|---|
| 首次体验、个人轻量使用 | `deploy/` | SQLite | 配置最少，启动最快 |
| 长期运行、并发访问、正式服务 | `deploy/production/` | PostgreSQL | 更适合并发、备份和运维，但不提供用户隔离 |
| 已有 PostgreSQL 数据库 | `deploy/` 并设置 `DATABASE_URL` | 外部 PostgreSQL | 不另外启动数据库容器，见[连接已有的 PostgreSQL](#external-postgresql) |
| 本地开发 | 源码启动 | SQLite 或 PostgreSQL | 见[贡献指南](../dev/contributing.md) |

无论选择哪种方式，项目图片、视频和其他生成资产都需要持久化保存。

一个 ArcReel 实例是一个共用工作区：可以有多个账号登录，所有成员都能看到全部项目，共用供应商凭据和设置；管理员另外可以管理成员。ArcReel 不按项目划分权限，也不隔离成员之间的数据，只应邀请可以信任的协作者。PostgreSQL 生产部署同样不提供租户隔离。

## 1. 默认部署：SQLite {#sqlite-deployment}

### 1.1 启动 {#sqlite-start}

```bash
git clone https://github.com/HazelnutParadise/ArcReelStudio.git
cd ArcReelStudio/deploy

cp .env.example .env
```

编辑 `.env`：

```dotenv
AUTH_USERNAME=admin
AUTH_PASSWORD=请设置强密码
AUTH_TOKEN_SECRET=请设置长期固定的随机密钥
# LOG_LEVEL=INFO
```

`AUTH_USERNAME` 与 `AUTH_PASSWORD` 只在第一次启动、还没有任何账号时用来建立默认管理员，之后修改它们不会改动已有账号。`AUTH_PASSWORD` 留空时会生成初始密码，保存在数据根的 `runtime/initial-admin-password`（Docker 部署为宿主机数据存放位置下的 `projects/runtime/initial-admin-password`，默认即 Compose 目录，见[持久化目录](#sqlite-volumes)）；默认管理员修改密码后，这个文件会被删除。

生成随机密钥：

```bash
openssl rand -hex 32
```

启动：

```bash
docker compose up -d
```

验证：

```bash
docker compose ps
docker compose logs --tail=100 arcreel
curl http://localhost:1241/health
```

### 1.2 持久化目录 {#sqlite-volumes}

默认 Compose 会挂载：

| 宿主机路径 | 容器路径 | 内容 |
|---|---|---|
| `deploy/projects/` | `/app/projects` | 数据根：项目、生成资产、默认 SQLite 数据库、日志、Vertex AI 凭据等全部运行数据 |
| `deploy/claude_data/` | `/root/.claude` | Agent 运行时相关数据 |

表中是默认位置。在 `deploy/.env` 中设置 `ARCREEL_HOST_DATA_DIR` 后，`projects/` 与 `claude_data/` 改放在该目录下，例如 `ARCREEL_HOST_DATA_DIR=/srv/arcreel` 对应 `/srv/arcreel/projects/` 与 `/srv/arcreel/claude_data/`；相对路径以 `deploy/` 为基准，并且要以 `./` 或 `../` 开头，例如 `./data`。只写 `data` 时，Compose 会把它当成命名卷，容器无法启动。容器内的路径不变，不需要修改容器内数据根的 `ARCREEL_DATA_DIR`。

已有部署更换存放位置时，按以下顺序操作：

1. 在 `deploy/` 执行 `docker compose down`；
2. 把 `projects/` 与 `claude_data/` 整个移到新目录，保留文件属主与权限（例如使用 `mv` 或 `rsync -a`）；
3. 在 `deploy/.env` 中设置 `ARCREEL_HOST_DATA_DIR`，执行 `docker compose up -d`。

`deploy/.env` 只作为 Compose 的插值来源，不挂进容器。容器收到哪些环境变量，以 `docker-compose.yml` 中 `environment` 列出的为准。

`deploy/projects/` 是 ArcReel 的数据根（`ARCREEL_DATA_DIR`，容器内为 `/app/projects`）。项目收在其中的 `projects/` 子目录里，其余运行数据与之并列：

```text
deploy/projects/               数据根
├── projects/<项目名>/         项目与生成资产
├── deleted_projects/          已删除项目，保留 30 天
├── global_assets/             全局资产库
├── users/<user_id>/memory/    Agent 用户记忆
├── arcreel.db                 默认 SQLite 数据库（连同 -wal / -shm）
├── logs/                      应用日志
├── vertex_keys/               Vertex AI 凭据文件
├── trial_runs/                端点「测试连接」的产物
└── runtime/                   迁移完成标记、生成准入锁、图片缩略图缓存等运行时状态
```

只有 `projects/` 下名字由英文字母、数字或中划线组成、并且包含 `project.json` 的目录才算项目，数据根里的其它条目不会出现在项目列表中。设置页「关于」中下载的诊断日志会列出数据根及上述各类数据的实际位置。

> 备份时归档整个数据根，不要只备份数据库而忽略项目文件。数据库保存任务、配置和索引信息，项目目录保存原始素材和生成文件，两者需要保持一致。

项目回收站存放在 `projects/<项目名>/.arcreel/trash/`，完整数据根备份会保留其中的删除记录，项目 ZIP 导出不包含它。删除记录按删除时间保留 30 天，应用启动时和运行期间定期清理；恢复备份不会重置记录的保留期。

删除的项目整体移到 `deleted_projects/<项目名>#deleted-<删除时间>/`，连同它的项目回收站，同样保留 30 天、按同样的方式清理。在项目列表页的「已删除项目」中可以恢复或彻底删除；恢复时原名已被占用，项目会以加后缀的新名字恢复。

## 2. 生产部署：PostgreSQL {#postgresql-deployment}

### 2.1 启动 {#postgresql-start}

```bash
cd "$(git rev-parse --show-toplevel)/deploy/production"
cp .env.example .env
```

编辑 `.env`：

```dotenv
AUTH_USERNAME=admin
AUTH_PASSWORD=请设置强密码
AUTH_TOKEN_SECRET=请设置长期固定的随机密钥
POSTGRES_PASSWORD=请设置数据库密码
# LOG_LEVEL=INFO
```

推荐生成只含十六进制字符的密码：

```bash
openssl rand -hex 16
```

默认 Compose 会把 `POSTGRES_PASSWORD` 的原始值交给 PostgreSQL，同时把它拼入 `DATABASE_URL` 的密码段。如果密码含有 `@`、`:`、`/`、`?`、`#`、`%` 等 URL 保留字符，连接 URI 中的密码必须做百分号编码。不要把编码后的值直接填入 `POSTGRES_PASSWORD`：PostgreSQL 需要原始密码，只有 URI 需要编码。

当必须使用特殊字符时，在 `.env` 中分开保存原始值与编码值：

```dotenv
POSTGRES_PASSWORD='p@ss/word'
POSTGRES_PASSWORD_URLENCODED=p%40ss%2Fword
```

然后把 `deploy/production/docker-compose.yml` 中 `DATABASE_URL` 的密码部分改为 `${POSTGRES_PASSWORD_URLENCODED}`；PostgreSQL 容器的 `POSTGRES_PASSWORD` 仍保持不变。可用 `urllib.parse.quote(raw_password, safe="")` 生成编码值。如果不想维护这项 Compose 改动，就使用上述十六进制密码。

启动：

```bash
docker compose up -d
```

验证：

```bash
docker compose ps
docker compose logs --tail=100 postgres
docker compose logs --tail=100 arcreel
curl http://localhost:1241/health
```

### 2.2 PostgreSQL 持久化目录 {#postgresql-volumes}

| 宿主机路径 | 内容 |
|---|---|
| `deploy/production/pgdata/` | PostgreSQL 数据目录 |
| `deploy/production/projects/` | 数据根：项目、媒体资产、日志、Vertex AI 凭据等，布局与[默认部署](#sqlite-volumes)相同，不含数据库 |
| `deploy/production/claude_data/` | Agent 运行时数据 |
| `deploy/production/.env` | 认证和数据库配置；只作为 Compose 的插值来源，不挂进容器 |

`pgdata/`、`projects/` 与 `claude_data/` 的位置同样由 `deploy/production/.env` 中的 `ARCREEL_HOST_DATA_DIR` 决定，未设置时在 `deploy/production/` 下；更换位置的步骤与[默认部署](#sqlite-volumes)相同，三个目录都要移动。`pgdata/` 由 PostgreSQL 容器内的用户持有，移动时必须保留属主与权限，否则 PostgreSQL 无法启动。

`pgdata/` 只保存 PostgreSQL 集群数据，`projects/` 是数据根，保存项目元数据、媒体资产和其余运行数据，两者都必须持久化且配套备份。生产部署通过 `DATABASE_URL` 使用 PostgreSQL，不会使用 `deploy/production/projects/arcreel.db`；不要把 SQLite 文件复制进 `pgdata/`，也不要把两个目录当成可相互替代的数据库备份。

### 2.3 数据库迁移 {#database-migrations}

ArcReel 在应用启动时运行 Alembic 迁移，将数据库结构升级到当前版本。

数据库结构从同一个起点迁移脚本建起。上游 ArcReel 或本项目早期开发版建出的数据库没有对应的迁移起点，启动时会报 `Can't locate revision identified by '…'`，不能直接沿用，请用新的数据库。

升级前仍然必须备份。自动迁移解决的是结构升级，不代替可回滚的数据备份。

### 2.4 连接已有的 PostgreSQL {#external-postgresql}

已有 PostgreSQL 服务器时，可以不启动 Compose 自带的数据库容器。是否启动数据库容器由所用的 Compose 文件决定：`deploy/` 不启动，`deploy/production/` 一定启动。`DATABASE_URL` 只决定 ArcReel 连接哪个数据库。

1. 在 PostgreSQL 中为 ArcReel 建立专用数据库和账号，账号需要建表权限。不要与其他服务共用同一个数据库。
2. 在 `deploy/.env` 中设置 `DATABASE_URL`：

   ```dotenv
   DATABASE_URL=postgresql+asyncpg://arcreel:密码@db.example.com:5432/arcreel
   ```

3. 在 `deploy/` 中启动：

   ```bash
   docker compose up -d
   ```

4. 查看启动日志，确认迁移完成且没有连接错误：

   ```bash
   docker compose logs --tail=100 arcreel
   ```

注意：

- 使用 `deploy/`，不要使用 `deploy/production/`。生产 Compose 在 `environment` 中固定了 `DATABASE_URL`，会覆盖 `.env` 中的设置，并且仍会启动自带的 PostgreSQL 容器。
- 只支持 PostgreSQL，URL 必须以 `postgresql+asyncpg://` 开头。
- 应用启动时自动运行数据库迁移，空数据库即可。
- 数据库运行在同一台主机上时，主机名不能写 `localhost`，因为容器内的 `localhost` 指向容器本身。macOS 和 Windows 的 Docker Desktop 使用 `host.docker.internal`；Linux 填写主机的局域网 IP，或在 `docker-compose.yml` 的 `arcreel` 服务中加入 `extra_hosts: ["host.docker.internal:host-gateway"]`。
- 密码含有 URL 保留字符时，URL 中的密码必须做百分号编码，规则见[生产部署的启动说明](#postgresql-start)。
- 数据库备份由数据库管理员负责，`projects/` 数据根仍需按[默认部署](#sqlite-volumes)持久化，并与数据库配套备份。
- 已在 SQLite 中有数据时，先按 [从 SQLite 迁移到 PostgreSQL](./migrate-to-postgres.md) 迁移数据，再切换 `DATABASE_URL`。

## 3. 环境变量 {#environment-variables}

默认部署示例当前包含以下核心变量：

| 变量 | 默认值 | 建议 |
|---|---|---|
| `ARCREEL_IMAGE_TAG` | 默认部署 `main`，生产部署 `latest` | 镜像标签，只由 Compose 读取；生产环境建议固定版本，见[固定版本](#pin-version) |
| `ARCREEL_HOST_DATA_DIR` | Compose 目录 | 宿主机上的数据存放位置，只由 Compose 读取，见[持久化目录](#sqlite-volumes) |
| `AUTH_USERNAME` | `admin` | 默认管理员的用户名，只在第一次启动、还没有任何账号时使用 |
| `AUTH_PASSWORD` | 空 | 默认管理员的密码，只在第一次启动时使用；留空则生成初始密码，见[账号与成员](#accounts) |
| `AUTH_TOKEN_SECRET` | 空 | 建议设置长期固定随机值；留空时自动生成并保存到数据根下的 `runtime/auth-token-secret`，重启后沿用 |
| `AUTH_ENABLED` | `true` | 远程部署不得关闭；设为 `false` 时全部管理接口无需认证 |
| `LOG_LEVEL` | `INFO` | 排障时临时改为 `DEBUG`，完成后恢复 |
| `POSTGRES_PASSWORD` | 无 | 仅生产部署需要，必须设置 |
| `TZ` | `Asia/Taipei` | 可在 Compose 环境中覆盖 |
| `DATABASE_URL` | SQLite 默认路径 | 生产 Compose 自动设置 PostgreSQL URL；连接外部数据库时在默认部署的 `.env` 中设置，见[连接已有的 PostgreSQL](#external-postgresql) |
| `ARCREEL_DATA_DIR` | `projects` | 数据根；项目、默认 SQLite 数据库、日志和 Vertex 凭据都在其下。Docker 部署的容器内固定为 `/app/projects`，要改宿主机位置请用 `ARCREEL_HOST_DATA_DIR` |
| `CORS_ORIGINS` | 通配 | 设为白名单时，浏览器型 MCP 客户端的 Origin 也须列入 |
| `ARCREEL_OFFICIAL_SERVICE_URL` | 内置官方服务地址 | 市场安装量、评分与分享提交所用的官方服务；设为空即整体关闭，市场回到只读取市场源的形态 |

注意：

- `AUTH_TOKEN_SECRET` 变化后，现有登录 Token 会失效。显式设置时以设置值为准，数据根下自动生成的密钥文件不再使用。未显式设置时，删除密钥文件并重启会生成新密钥，使现有登录失效。
- 修改 `.env` 后，在 Compose 目录执行 `docker compose up -d` 重建容器。`docker compose restart` 与容器自动拉起沿用创建容器时的环境变量，不会重新载入 `.env`。
- Compose 只把 `docker-compose.yml` 中 `environment` 列出的变量传进容器。要传入表中未列出的变量，在 `environment` 中加一行 `变量名: ${变量名}`，再在 `.env` 中设置取值。旧版 Compose 用 `env_file` 把整份 `.env` 传进容器，升级后表中未列出的变量（例如 `HTTPS_PROXY`）不会再传入，需要的话按这个方法加回去。
- `AUTH_ENABLED=false` 仅适用于受独立网络边界保护的本机环境。Compose 默认把 `1241` 端口发布到宿主机所有网卡，远程部署不得关闭认证。认证关闭时，启动日志会输出 WARNING。
- `.env` 中可能包含密钥，不要提交到版本库。
- Vertex 凭据文件应只授予运行 ArcReel 的用户读取权限。
- 文件日志固定写入数据根下的 `logs/`；只需要 stdout 日志时设置 `ARCREEL_LOG_FILE_DISABLED=true`。
- 第三方模型 API Key 通常在 ArcReel 设置页中管理，不要写入公开文档。

远程 MCP 端点为 `/mcp`，始终要求 `arc-` 前缀 API Key；即使 `AUTH_ENABLED=false` 也不会匿名放行。外部接入不需要额外的 `MCP_*` 配置：把设置页「外部 Agent 接入」给出的端点地址，与在「访问令牌」创建的 API Key 填进客户端即可，通过保留 SSE 长连接的 HTTPS 反向代理、VPN 或安全隧道访问。

### 3.1 账号与成员 {#accounts}

第一次启动时，ArcReel 按 `AUTH_USERNAME` / `AUTH_PASSWORD` 建立默认管理员。之后的账号都在「设置 › 账号与成员」中管理：

- 每个成员都可以在这里修改自己的密码或登出。修改密码后，其他设备上的登录会失效。
- 管理员可以新增成员、把成员设为管理员、停用账号或替成员重设密码。停用、改角色和重设密码都会让该成员现有的登录失效。
- 至少要保留一位启用中的管理员；管理员不能停用自己，也不能取消自己的管理员身份。

用户名只能使用小写英文字母、数字和 `.` `_` `@` `-`，登录时不区分大小写。`embedded-agent` 保留给内嵌 Agent，不能用作用户名。密码至少 8 个字符。

忘记密码时，在 Compose 目录执行：

```bash
docker compose exec arcreel uv run python -m scripts.manage_users reset-password admin
```

命令会请你输入两次新密码，输入时不会显示；不方便交互时可以加上 `--password <新密码>`。`list` 子命令列出所有账号。源码部署在仓库根目录执行 `uv run python -m scripts.manage_users ...`。

从只有一组 `.env` 账号的旧版本升级时，第一次启动会把当时的 `AUTH_USERNAME` / `AUTH_PASSWORD` 写成默认管理员，原来的密码照常可用；升级前签发的登录全部失效，需要重新登录一次。旧的 `AUTH_USERNAME` 不符合上面的用户名规则时（例如含有空格或中文），默认管理员会改名为 `admin`，启动日志会记录这次改名，之后请用 `admin` 登录。

多位成员可以同时打开同一个项目，像共同编辑文档一样一起改：

- 顶栏右侧显示也在这个项目里的其他成员，点开可以看到各自正在看哪一集；页面上会看到其他成员的鼠标指针和名字。
- 项目概述、创作灵感、角色 / 场景 / 道具 / 商品、角色衍生形象、自带原文的集原文、分镜详情、参考视频单元、项目设置、全局资产库条目与 Agent 记忆文件，每个人的修改会即时出现在其他人那里。正在编辑同一个字段的成员显示为该字段上带名字的彩色光标。
- 这些编辑区没有「保存」按钮：服务端合并所有人的输入，停止输入片刻后写回项目文件。两个人在同一段文字里同时打字，双方的字都会保留；Ctrl / ⌘ + Z 只撤销自己的修改。
- Agent 或后台任务改了你正在编辑的内容时，改动直接并进编辑区，不会覆盖你还在打的字。
- 断线时可以继续编辑，修改留在本机，重新连上后自动同步；断线期间编辑区下方提示「已离线」。连不上协作服务时（例如反向代理没有转发 WebSocket），编辑区退回「改完再保存」的方式。
- 项目设置里的改动不合规时（例如配音模型还没选就切到 TTS 配音），编辑区下方显示原因，修改保留到补齐为止。
- 供应商与凭证、自定义端点和其余全局设置仍是改完再保存，同时保存时以后保存的一方为准。

在线名单与协作中的编辑内容都只保存在服务进程的内存里，所以只能运行一个服务进程。服务关闭前会把还没写回的内容写回；重启后各页面自动重新连线。

### 3.2 GPU 编码 {#gpu-encoding}

镜像内置支持 NVIDIA NVENC 的 ffmpeg。容器能使用 NVIDIA GPU 时，渲染成片改用 GPU 编码画面；拿不到 GPU 时自动使用 CPU 编码，不需要额外配置。

在 NVIDIA GPU 主机上启用：

1. 在宿主机安装 NVIDIA 驱动与 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)。
2. 在 Compose 目录的 `.env` 中加入：

   ```dotenv
   COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml
   ```

   Windows 主机上 Compose 用分号分隔多个文件，改写成 `COMPOSE_FILE=docker-compose.yml;docker-compose.gpu.yml`。

3. 执行 `docker compose up -d` 重建容器。

启动日志出现「GPU 编码可用」即已生效。在「设置 › 通用」中可以关闭 GPU 编码，关闭后成片始终使用 CPU 编码。

没有 NVIDIA GPU 的主机不要加载 `docker-compose.gpu.yml`：Docker 拿不到 GPU 时会拒绝启动容器。

GPU 只负责成片的画面编码，混音、封装和其他媒体处理仍使用 CPU。GPU 编码中途失败时，该成片自动改用 CPU 重新渲染。目前只支持 NVIDIA GPU。

服务端不校验请求的 `Host` 头，端点边界由每请求强制的 API Key 承担；域名归属交给部署形态，请在反向代理上限定 `server_name`（Nginx）或等价规则，只把预期域名的请求转发给 ArcReel。

`CORS_ORIGINS` 保持默认通配时，浏览器型 MCP 客户端同样无需配置；一旦收紧为白名单，就要把该客户端的 Origin 也列进去——这一个白名单同时约束应用 API 与 MCP 端点，不存在第二份 MCP 专用清单。

远程 MCP 不提供 OAuth 授权，也不发布 OAuth 受保护资源元数据（RFC 9728）；只支持 OAuth 自动发现、无法自行填写 Bearer 凭证的客户端无法接入。

ArcReel 的沙箱要求父进程环境中不保留供应商密钥。以下凭据环境变量存在非空值时，服务会拒绝启动并提示迁移到 WebUI 设置页：

- `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN`
- `ARK_API_KEY` / `XAI_API_KEY` / `GEMINI_API_KEY` / `VIDU_API_KEY`
- `DASHSCOPE_API_KEY` / `MINIMAX_API_KEY` / `AGNES_API_KEY` / `OPENAI_API_KEY`
- `GOOGLE_APPLICATION_CREDENTIALS`（Vertex 凭据在设置页上传，保存在数据根下的 `vertex_keys/`）

`ANTHROPIC_BASE_URL`、模型名等非密钥配置不会单独触发启动拒绝，但仍建议与对应凭据一起在 WebUI 中管理。

## 4. 健康检查和日志 {#health-and-logs}

### 4.1 健康检查 {#health-check}

Compose 使用：

```text
GET /health
```

手动检查：

```bash
curl -f http://localhost:1241/health
```

该端点无需认证。官方镜像的响应带 `commit` 字段，值是构建镜像的 commit sha，可用来确认实例运行的版本；从源码直接运行时为 `null`。

### 4.2 查看日志 {#view-logs}

```bash
# 最近 200 行
docker compose logs --tail=200 arcreel

# 持续跟踪
docker compose logs -f arcreel

# 生产数据库日志
docker compose logs -f postgres
```

文件日志位于数据根下的 `logs/`，默认部署为 `deploy/projects/logs/`。

不要在公开 Issue 中直接粘贴完整日志。提交前先清理：

- API Key；
- Token；
- Base URL 中的凭据；
- 用户输入内容；
- 本地文件路径中的隐私信息。

## 5. 升级 {#upgrade}

### 5.1 升级前 {#before-upgrade}

1. 阅读 [CHANGELOG](https://github.com/HazelnutParadise/ArcReelStudio/blob/main/CHANGELOG.md) 和目标 Release 说明；
2. 确认是否存在破坏性变更；
3. 备份数据根和数据库，见[备份与恢复](#backup-and-restore)；
4. 记录当前镜像版本；
5. 在可接受的维护窗口执行升级。

> ArcReel 不支持降级。升级可能改写数据库结构和项目结构，旧版本无法读取升级后的数据；要回到旧版本，需要停止服务并恢复升级前的备份。

### 5.2 默认部署升级 {#upgrade-sqlite-deployment}

在 `deploy/` 中：

```bash
# 先备份，见后文
docker compose pull
docker compose up -d

docker compose ps
docker compose logs --tail=100 arcreel
curl -f http://localhost:1241/health
```

### 5.3 生产部署升级 {#upgrade-postgresql-deployment}

在 `deploy/production/` 中：

```bash
# 先备份数据库和数据根 projects/
docker compose pull
docker compose up -d

docker compose ps
docker compose logs --tail=100 postgres
docker compose logs --tail=200 arcreel
curl -f http://localhost:1241/health
```

应用启动时会执行数据库迁移。不要在没有备份的情况下跳过多个版本直接升级。

### 5.4 从上游 ArcReel 迁入 {#from-upstream-arcreel}

本版本不接管上游 ArcReel 的安装：数据根只按[持久化目录](#sqlite-volumes)一节所示的布局读写，旧的平铺布局、旧的默认数据库文件名 `.arcreel.db`、代码目录下的 `logs/` 和旧系统配置文件都不会被搬动或导入；数据库也只能从空库建出，不能接上上游的数据库。

要带走上游的项目，先在上游 ArcReel 中把项目升级到 schema 19 或更高版本并导出归档，再在本版本中导入，见[项目结构迁移](#project-schema-migrations)。供应商配置与凭据在设置页重新填写。

### 5.5 项目结构迁移 {#project-schema-migrations}

应用启动时除数据库迁移外，也会逐个升级数据根 `projects/` 目录下的项目结构。只有名字由英文字母、数字或中划线组成，且包含 `project.json` 的目录会被视为项目并参与迁移及过期备份回收。

本版本只能升级 schema 19 及以上的项目。`project.json` 里 schema 版本更早或没有 schema 版本的项目不会被迁移，迁移也不改写它的文件（包括源文件编码转换）：启动时只在项目目录里写一份迁移失败记录 `.migration_failure.json`，项目大厅的卡片标出「版本过旧」，项目页顶栏显示「项目版本过旧」，生成功能关闭，其他项目照常升级；从「已删除项目」恢复这样的项目也一样。这类项目在本版本里无法修复或重试。导入这样的归档会直接被拒绝，不留下任何数据。要继续使用这类项目，先在上游 ArcReel 中打开它，让它升级到 schema 19 或更高版本，再导出归档，导入到本版本。

迁移提交前会在各文件旁创建带 `.bak.v<起点版本>-<时间戳>` 后缀的备份，覆盖：

- `project.json`；
- `project.json` 登记的正式剧本文件与同一集的脚本规划草稿；
- 已存在的 `.arcreel_artifacts.json`；
- 改写版本记录的迁移另备份 `versions/versions.json`。

迁移可安全重试：如果上次启动在备份或提交中断，下一次启动会重新校验，并确保至少有一份与迁移前内容完全一致的备份后再继续；内容相同的备份只保留一份，反复失败不会堆出多份。自动生成的这些项目级备份只用于迁移恢复，不能代替数据库与整个数据根的部署级备份。

迁移完成后会在项目目录写入 `.migration_report.json`，只记两组内容：「已调整」列出迁移改了什么（旧形态规整时的取舍、补上的占位定义、修复的结构），「未能带入」列出原地保留、但没有登记的文件（读不出的文件、没有合成设置记录的旧版旁白音频）。生成缺口、需要重新规划的单位，以及依据算不出而没有登记的产物（例如源文不是 UTF-8 时的脚本规划）不进报告。报告只作说明，不阻断任何操作。报告非空时，项目页顶栏会出现一次「本次升级调整了 N 项内容」的提示，点开是只读报告；关闭后不再出现。制作状态接口的 `migration_report` 字段只在报告非空、尚未关闭时给出。

归档导入同样走这条迁移链，并且不论导入包是哪个版本导出的，导入时读不出的文件也写进这份报告。报告非空时，项目出现在项目列表之前会弹出「导入前请确认」，内容就是这份报告；选「取消」不留下任何项目数据，选「确认导入」才完成导入，项目页不再重复提示同一份报告。报告为空时直接导入；当前版本导出的正常项目再导入，报告就是空的。导入时迁移链出错，导入会带着具体原因失败，导入包里的数据不会留下。

导出项目归档只读取项目、不改动它。某件产物的状态无法确认时，导出不会失败，而是照实带上，并在导出诊断里逐条说明导入后会看到什么：

- 版本文件不见了或已损坏，但正式文件与版本记录的内容指纹一致：归档里按正式文件补回版本文件，列在「已自动修复」。导入后状态与现在一致，恢复该版本与出片照常可用。源项目里这份版本文件仍是原样。
- 视频或配音的文件还在，但无法确认它仍是所选版本（版本文件不见了且对不上记录、版本记录缺失、文件被替换，或上次导入时就是已过期）：照常带上，导入后显示为已过期，仍可查看和使用，再导出导入也一样。现在已过期的视频与配音，导出后不会变成最新；重新生成或在版本历史里切换版本后恢复正常判定。
- 产物文件已不在项目里，或是符号链接、位于符号链接目录下：不带它的产物记录，剧本或 `project.json` 里导入校验要求在场、却指向它的引用在归档里清空，导入后显示为缺失。引用的是隐藏文件时同样清空，因为归档不带隐藏文件。被清空的引用若是某件产物的生成依据（例如视频的尾帧），这件产物导入后显示为已过期，不会因为引用被清掉而变成最新。
- 版本历史里导入会拒收的部分（结构损坏，或版本记录指向版本历史目录之外）：归档去掉这几项，其余版本照常带上。
- 字幕与旁白呈现对不上所依据的视频或配音版本，或依据的旧版本不在「仅当前版本」的归档里：不带它们的记录。它们在本地生成、不产生费用，导入后预览、剪辑或导出剪映草稿时会按当时选中的媒体重新生成。
- 产物清单读不出：归档按项目文件与版本记录重新整理产物记录。视频与配音照版本记录里的生成依据判定，已过期的、无法确认是所选版本的，导入后都显示为已过期；其他产物导入后显示为最新，原来的已过期标记不会保留。

只有这些情况会让导出停下并说明原因：项目在导出过程中一直有改动（稍后重试）；项目文件、剧本、版本记录或宫格记录读不出（包括没有读取权限的文件与目录）、结构损坏，原因里会写明出问题的位置，版本文件的位置上是目录也算在内；远端素材取不回；磁盘空间不足或超出磁盘配额（清出空间后重试）。

导入时，包里缺少版本文件或版本文件与记录不符的视频与配音以已过期导入，导入结果会逐条列出；包里缺少版本文件、正式文件又与版本记录一致时，导入会补回版本文件，之后在版本历史里切回该版本即可恢复为最新。包里带着的版本文件与版本记录不符，或位置上是目录时，原样保留，导入结果会提示这个版本无法切回。几条版本记录共用同一个版本文件时，导出与导入都不改它。包里有重名的条目时拒绝导入。没有产物记录的归档（手工打包等）按文件重新登记，导入会先补回版本文件，这类视频与配音照常显示为最新。包里的正式文件与导出时记下的内容指纹不符时，导入照旧拒绝。

迁移只因以下问题拒绝整个项目：项目的 schema 版本早于 19；`project.json` 或剧本读不出（不是合法 JSON，或缺了创作类型这类决定其形态的内容）；版本记录 `versions/versions.json` 或产物清单 `.arcreel_artifacts.json` 读不出；剧本里的条目结构损坏（例如条目列表里有不是对象的条目）；导入包本身不安全。迁移本身没能做完（磁盘空间不足、写入失败）照旧阻断，项目保持升级前的状态，排除故障后重试即可。其余数据问题按条目处理，原有内容不会丢弃：

- 过去正常流程写出的旧形态由迁移自动规整：剧本没有记录所属的集、或记录的集与绑定不符时，以集列表为准写回；同一类资产里名字去掉首尾空白、统一 Unicode 形式后相同（不区分大小写）的只留第一条，去掉的那条名下的衍生并到保留的那条名下（与已有衍生只差大小写时并入已有的那个），剧本与脚本规划里写成只差大小写那个名字的引用改为保留的名字，去掉的那条的资产图登记一并撤掉（保留的那条若原本没有自己的登记，会显示为需要生成）；剧本里缺 ID 或 ID 重复的条目补上新 ID，重复的从第二条起换号，原 ID 的媒体文件留给保留原 ID 的那一条；两集里有同 ID 的条目时，媒体留给 ID 前缀所指的那一集（对不上时留给集列表里靠前的那一集），另一集的条目换新 ID，该集原 ID 的产物登记一并撤掉，不占住另一集的媒体文件；该集里成员包含原 ID 的宫格图及它切出的分镜图需要重新生成，剪辑时间线里对应的片段显示为单元已删除。
- 资产图、参考图、参考音频或商品原图指向其他现存资产名下的文件（含衍生图）时，迁移会复制一份到本资产名下并改写引用，原文件留给原资产。复制会增加磁盘占用；本资产名下的落点已有不同内容时，原有文件先移为保留副本。资产图的制作状态不因复制改变：改写前是最新的仍是最新，改写前已失效的仍需重新生成。复制落点、引用与资产图登记在同一事务内提交，失败时恢复原状。源路径含符号链接时不复制；目标目录是符号链接时，迁移会失败，需先还原为项目内的实际目录再重试；目标文件是符号链接时，只替换链接本身，不改动链接指向的文件。复制与保留副本的位置列入「已调整」。
- 规整需要取舍时，另一份留作保留副本，文件名带 `.kept.v<起点版本>-<时间戳>` 后缀，放在原文件旁。保留副本不会被自动清理，报告的「已调整」里写明它的位置。
- 单个宫格记录、单份脚本规划草稿或单个媒体文件读不出时，文件原样留在原处、不登记，列入「未能带入」，其余内容照常迁移。视频或配音文件还在、但所选版本的快照文件不在时，无法确认它就是所选版本，同样原样保留、列入「未能带入」。归档里的剧本引用了未定义的角色、场景或道具时，导入会补一条空白定义并列入「已调整」。

`project.json` 里没有画面比例字段的剧情演绎项目，分镜图按剧情模式的缺省比例 16:9 判断是否最新，与实际生成时一致。这类项目此前按 9:16 登记的分镜图会显示为已过期；按需重新生成即可。

用户上传的分镜图与视频，当前选中的版本仍为手动上传、且文件与上传快照字节一致时，导入会按上传字节补登或改写产物记录，显示为最新；提示词为空或引用资产缺图也不影响登记。之后改提示词、资产或画风不会让它们过期，批量补缺会保留它们。已改选生成版本或文件与上传快照不一致的产物不按上传口径补登。

生成的分镜图里引用的资产如果已删除或改名，或者引用的角色、场景、道具没有可登记的资产图（从未生成、文件丢失，或描述为空），这张分镜图照常登记、显示为最新，缺的引用记在它的产物记录里；但重新生成该分镜图会被拒绝，直到补齐。商品资产图是可选的：未声明资产图时，可只用原图；也未声明原图时，可只用文字。已声明的商品资产图不可用，或已声明的商品原图读不到，处理方式相同。补齐资产登记或资产图、重新上传缺失原图或清掉失效的原图字段后，这张分镜图显示为已过期，按需重新生成即可。

资产图与衍生资产图也按同一口径登记：角色或商品声明了原图但原图读不到，或资产描述为空，资产图照常登记、显示为最新；衍生的本体资产图有缺口时，衍生资产图同样照常登记。重新生成会被拒绝，直到重新上传原图或清掉失效的原图字段、补上描述；补齐后这张资产图显示为已过期。原图丢失的角色与商品同样不能生成资产图，处理方式相同。

如果某个项目迁移失败，先保留现场并查看启动日志，不要手工修改 schema 版本、删除备份文件或保留副本。修复损坏的项目文件或权限后再重启服务。

### 5.6 固定版本 {#pin-version}

Compose 使用的镜像标签由 `.env` 中的 `ARCREEL_IMAGE_TAG` 决定：

| 标签 | 内容 | 发布时机 |
|---|---|---|
| `main` | main 分支的最新构建，默认部署的默认值 | 每次合入 main 后 |
| `X.Y.Z`、`X.Y`、`latest` | 正式版本；`latest` 是生产部署的默认值，指向最新稳定版本 | 发布 `vX.Y.Z` 版本后 |

预发布版本（如 `vX.Y.Z-rc.1`）只发布同名版本标签，不更新 `latest`。还没有发布过正式版本时，`latest` 不存在，生产部署先设置 `ARCREEL_IMAGE_TAG=main`。

生产环境建议固定到某个正式版本：

```bash
# deploy/production/.env
ARCREEL_IMAGE_TAG=X.Y.Z
```

设置后执行 `docker compose up -d`。升级时修改这个值，可以降低无意中拉取新版本的风险。

## 6. 备份与恢复 {#backup-and-restore}

迁移整个站点到不同的绝对路径后，应用启动时会按当前项目目录调整已有 Agent 会话的存储位置，保留续聊上下文；已删除项目的会话也会随其恢复到的新名称调整。使用 `ARCREEL_SDK_SESSION_STORE=off` 时，会话仅保存在 SDK 本地目录，迁移时须一并保留该目录（Docker 为 `claude_data/`，原生部署为 `CLAUDE_CONFIG_DIR` 或默认的 `~/.claude`）。同一会话在多个来源位置都有记录，或目标位置已有记录时，不会自动合并；移动失败会记录告警，服务仍会启动。

在「新增图片保存位置」中启用对象存储后，远端图片的内容只保存在你的 TOS 存储桶里，数据根与数据库备份只含它们的记录与可清理的本地缓存。恢复备份时连接须仍指向原来的桶，桶里的对象需要一并保留。ArcReel 会删除不再使用的图片对象，备份之后删除的项目或版本，其对象可能已从桶里删除，恢复较早的备份后这些图片无法读取；需要恢复到较早时间点时，请在停止写入期间一并备份桶里 `arcreel-materials/` 下的对象（或为桶开启版本控制），恢复时放回原来的桶与对象键，见[新增图片保存到对象存储](../guide/providers.md#remote-image-storage)。

### 6.1 SQLite 部署备份 {#backup-sqlite}

数据根已经包含项目、默认 SQLite 数据库、日志和 Vertex 凭据，文件系统备份只需归档数据根，外加 `.env` 与 `claude_data/`。

先确认宿主机上的数据存放位置，再停止写入。默认在 `deploy/` 下；在 `.env` 中设置了 `ARCREEL_HOST_DATA_DIR` 时，把 `host_dir` 改为该值：

```bash
cd deploy

host_dir="."
# 设置了 ARCREEL_HOST_DATA_DIR 时改为该值，例如：host_dir="/srv/arcreel"
data_dir="$(cd "${host_dir}/projects" && pwd)"

docker compose stop arcreel
```

备份：

```bash
backup_stamp="$(date +%Y%m%d-%H%M%S)"
umask 077
mkdir -p backups
chmod 700 backups

tar -czf "backups/arcreel-config-${backup_stamp}.tar.gz" \
  .env -C "${host_dir}" claude_data

tar -czf "backups/arcreel-projects-${backup_stamp}.tar.gz" \
  -C "${data_dir}" .
```

服务停止后再归档整个 `data_dir`，可以让 `arcreel.db` 与项目资产保持在同一时点。配置归档与数据归档必须使用相同时间标签并配套保存；`umask 077` 与备份目录模式 `0700` 会限制其中凭据和项目资产的读取权限。不要在 ArcReel 写入时只复制 `arcreel.db`：WAL 模式下，已提交交易可能仍在 `arcreel.db-wal` 中，丢失或错配 WAL 文件会造成数据丢失甚至损坏。如果无法停服，应使用 SQLite Online Backup API（例如 `sqlite3` 的 `.backup`）或 `VACUUM INTO` 生成一致快照，而不是直接 `cp` 主数据库文件。

恢复服务：

```bash
docker compose start arcreel
```

恢复时：

1. 停止 ArcReel；
2. 备份当前目录，避免覆盖后无法回退；
3. 将配置归档中的 `.env` 恢复到 `deploy/`，`claude_data/` 恢复到 `host_dir`，并将配套数据归档完整解压到空的 `data_dir`；
4. 启动并检查 `/health`；
5. 打开几个项目验证图片、视频和版本历史。

### 6.2 PostgreSQL 部署备份 {#backup-postgresql}

先停止 ArcReel 应用，保留 PostgreSQL 运行，避免备份数据库和项目文件期间继续产生写入。`host_dir` 是宿主机上的数据存放位置，在 `.env` 中设置了 `ARCREEL_HOST_DATA_DIR` 时改为该值：

```bash
cd "$(git rev-parse --show-toplevel)/deploy/production"
host_dir="."
# 设置了 ARCREEL_HOST_DATA_DIR 时改为该值，例如：host_dir="/srv/arcreel"
umask 077
mkdir -p backups
chmod 700 backups
docker compose stop arcreel

backup_stamp="$(date +%Y%m%d-%H%M%S)"

docker compose exec -T postgres sh -c \
  'PGPASSWORD="$POSTGRES_PASSWORD" exec pg_dump -h 127.0.0.1 -U arcreel -d arcreel' \
  > "backups/arcreel-db-${backup_stamp}.sql"

tar -czf "backups/arcreel-files-${backup_stamp}.tar.gz" \
  .env docker-compose.yml -C "${host_dir}" projects claude_data

docker compose start arcreel
```

数据库备份和文件备份使用同一时间标签，必须配套保存和恢复。文件备份中的 `projects/` 是数据根，已包含日志与 Vertex 凭据。文件备份包含当前 `docker-compose.yml`，因此特殊字符密码所需的 `DATABASE_URL` 定制也会随 `.env` 一起恢复。`umask 077` 与备份目录模式 `0700` 会让宿主机重定向生成的 SQL 文件和文件归档仅对当前用户可读写。

`pg_dump` 会使用 libpq 的 `PGPASSWORD`。上述命令只在 PostgreSQL 容器内的该次 `pg_dump` 进程中设置它，因此 `docker compose exec -T` 可以非交互执行，也不会把密码展开到宿主机命令行。长期的宿主机备份自动化应改用权限为 `0600` 的 PostgreSQL password file，不要把密码写进脚本或备份文件名。

如果 `tar` 报 `Permission denied`，说明挂载目录中存在由容器内 root 用户创建、宿主机当前用户不可读的文件。可用 `sudo` 重新执行对应的 `tar` 命令，并在完成后限制备份文件的读取权限。

### 6.3 PostgreSQL 恢复 {#restore-postgresql}

恢复前停止 ArcReel，保留 PostgreSQL：

```bash
cd "$(git rev-parse --show-toplevel)/deploy/production"
host_dir="."
# 设置了 ARCREEL_HOST_DATA_DIR 时改为该值，例如：host_dir="/srv/arcreel"
docker compose stop arcreel

backup_stamp=YYYYMMDD-HHMMSS
tar -xzf "backups/arcreel-files-${backup_stamp}.tar.gz" .env docker-compose.yml
tar -xzf "backups/arcreel-files-${backup_stamp}.tar.gz" -C "${host_dir}" projects claude_data
```

文件归档会把 `.env`、`docker-compose.yml` 恢复到 `deploy/production/`，把数据根 `projects/` 和 `claude_data/` 恢复到 `host_dir`。以下流程还会删除目标 `arcreel` 数据库中的现有数据；先确认同一 `backup_stamp` 的数据库与文件备份完整，并在隔离环境演练恢复流程。

重建空数据库后再导入，避免与已有表结构或数据冲突：

```bash
docker compose exec -T postgres \
  dropdb -U arcreel --maintenance-db=postgres --if-exists --force arcreel

docker compose exec -T postgres \
  createdb -U arcreel --maintenance-db=postgres -O arcreel arcreel

cat "backups/arcreel-db-${backup_stamp}.sql" | \
  docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U arcreel -d arcreel
```

数据库导入成功后，重新启动：

```bash
docker compose start arcreel
curl -f http://localhost:1241/health
```

> 恢复策略取决于是否覆盖现有数据库、是否跨版本以及备份时服务是否仍有写入。生产环境应定期做真实恢复演练，而不只是确认备份文件存在。

## 7. 反向代理与 HTTPS {#reverse-proxy-and-https}

ArcReel 当前不支持直接暴露到公网。私有远程部署必须启用认证，并通过 TLS、VPN 或安全隧道保护传输。不要把 `1241` 端口直接发布到不受信任的网络。建议：

- 使用 Nginx、Caddy、Traefik 或云负载均衡器；
- 配置 HTTPS；
- 只允许代理服务器访问 ArcReel 容器端口；
- 保留 SSE 长连接；
- 设置足够的上传大小和读取超时。

官方 Compose 文件默认使用 `1241:1241`，会把后端端口发布到宿主机的所有网络接口；仅添加反向代理不会关闭这条直连路径。反向代理运行在同一宿主机时，启动前将 `arcreel` 服务的端口映射改为仅监听 loopback：

```yaml
ports:
  - "127.0.0.1:1241:1241"
```

如果反向代理运行在容器网络或其他主机上，应取消不必要的宿主机端口发布，并通过容器网络、主机防火墙或等效网络策略保证只有代理能够访问 ArcReel 后端。

ArcReel 自身已经处理缓存头和压缩，反向代理不需要另行配置：

- 带版本键（`?v=`、`?fp=`）或指向 `versions/` 版本快照的媒体地址，以及前端 `/assets/` 下带内容哈希的构建产物，返回 `Cache-Control: public, max-age=31536000, immutable`，浏览器直接复用本地缓存；
- 不带版本键的媒体地址返回 `Cache-Control: no-cache`，浏览器每次使用前向服务端再验证，文件未变化时返回 `304`；
- 页面入口 HTML 返回 `no-store`，升级后浏览器会加载新版前端；
- JSON、JS、CSS、HTML 等文本响应使用 gzip 压缩，SSE 事件流和图片、音视频不压缩。

反向代理应原样透传这些响应头，不要用 `expires`、`add_header Cache-Control` 或 `proxy_hide_header` 覆盖。

Nginx 示例。示例把媒体文件路径单独拆出：SSE 与普通 API 关闭代理缓冲，事件实时到达浏览器；`/api/v1/files/` 与 `/api/v1/global-assets/` 开启代理缓冲，图片和视频由 Nginx 先行接收，后端连接尽早释放。

```nginx
server {
    listen 443 ssl http2;
    server_name arcreel.example.com;

    ssl_certificate /etc/letsencrypt/live/arcreel.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/arcreel.example.com/privkey.pem;

    client_max_body_size 2g;

    # 只压缩文本类型。ArcReel 已压缩的响应 Nginx 不会重复压缩；
    # 不要加入 text/event-stream，压缩缓冲会延迟 SSE 事件；图片和音视频本身已压缩，也不要加入
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/markdown application/json application/javascript image/svg+xml;

    # 项目媒体与全局资产：只读 GET，开启缓冲
    location ~ ^/api/v1/(files|global-assets)/ {
        proxy_pass http://127.0.0.1:1241;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering on;
    }

    # 多人即时协作的 WebSocket：必须转发升级请求，否则编辑区退回「改完再保存」
    location = /api/v1/collab {
        proxy_pass http://127.0.0.1:1241;
        proxy_http_version 1.1;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location / {
        proxy_pass http://127.0.0.1:1241;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # ArcReel 使用 SSE 推送 Agent 回复和项目事件
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

证书配置取决于你的基础设施，可以使用 ACME/Let's Encrypt 或云平台托管证书。

## 8. 容器权限与 Agent 沙箱 {#container-permissions-and-sandbox}

ArcReel 在 Linux 和 macOS 启动时会严格检查 Agent 沙箱，所需工具缺失或不可用时会拒绝启动。Windows 原生环境没有 `bwrap`，会自动降级为受限的 Bash 命令白名单；该模式只保证项目创建与基础流程，生产部署建议使用 WSL2 或 Docker Desktop。

| 环境 | 工具 | 安装 |
|---|---|---|
| macOS | `sandbox-exec` | 系统自带，无需额外安装 |
| Linux 本地开发 | `bwrap` + `socat` | Ubuntu/Debian：`sudo apt install bubblewrap socat`；Fedora：`sudo dnf install bubblewrap socat`；Arch：`sudo pacman -S bubblewrap socat` |
| Docker | `bwrap` + `socat` | 官方镜像已包含 |
| Windows 原生 | 无 `bwrap` 沙箱 | 自动降级为 Bash 命令白名单；推荐 WSL2 / Docker Desktop |

官方 Compose 为 Agent Bash 沙箱配置了：

- `seccomp:unconfined`
- `apparmor:unconfined`
- `NET_ADMIN`

这些设置用于支持容器中的 `bwrap` 隔离和嵌套网络命名空间，但也意味着容器获得了比普通 Web 应用更高的权限。

生产部署建议：

- 使用专用主机或至少使用隔离良好的运行环境；
- 不把 Docker Socket 挂载到容器；
- 不额外挂载不必要的宿主机目录；
- 限制管理页面访问范围；
- 及时更新 ArcReel 和基础镜像；
- 只为 Agent 配置必要的网络和文件访问权限；
- 对未知来源的项目输入保持谨慎。

Docker 镜像虽然已包含 `bwrap` 和 `socat`，宿主机的 user namespace 或 AppArmor 策略仍可能阻止沙箱启动。启动失败时应根据服务输出的 `SANDBOX_*` 诊断修复，不要改成特权模式绕过检查，也不要在不了解影响的情况下删除官方 Compose 的沙箱配置。

## 9. 监控建议 {#monitoring}

最低限度应监控：

- `/health` 是否可用；
- 容器是否频繁重启；
- 磁盘剩余空间；
- `projects/` 增长速度；
- PostgreSQL 数据目录大小；
- 任务失败率；
- 供应商限流和额度不足；
- 备份最近成功时间。

媒体资产增长通常快于数据库，应优先为项目目录设置容量告警。

## 10. 常见故障 {#troubleshooting}

### 服务无法启动 {#service-wont-start}

```bash
docker compose ps
docker compose logs --tail=300 arcreel
```

检查：

- 生产部署的 `.env` 中是否设置了 `POSTGRES_PASSWORD`；留空时 Compose 报 `必須設定 POSTGRES_PASSWORD` 并拒绝启动；
- 端口 `1241` 是否被占用；
- 镜像是否成功拉取；
- 挂载目录是否可写；
- 生产部署是否设置 `POSTGRES_PASSWORD`。

### 健康检查失败 {#health-check-fails}

```bash
curl -v http://localhost:1241/health
docker compose logs --tail=300 arcreel
```

如果容器刚启动，先确认是否仍在执行数据库迁移。

### 无法登录 {#cannot-log-in}

- 用户名不区分大小写，确认账号没有被管理员停用；
- 修改 `.env` 中的 `AUTH_PASSWORD` 不会改动已有账号；忘记密码时按[账号与成员](#accounts)重设；
- 首次启动没有设置 `AUTH_PASSWORD` 时，初始密码在宿主机数据存放位置下的 `projects/runtime/initial-admin-password`；
- 修改 `AUTH_TOKEN_SECRET` 后需要重新登录。

### Agent 请求失败 {#agent-request-fails}

- 验证 Agent 凭据；
- 检查 Base URL 和模型名称；
- 检查网络和代理；
- 查看供应商是否限流；
- 使用少量内容验证，不要一上来就用完整小说跑通全流程。

### 任务一直排队 {#tasks-stuck-in-queue}

- 查看图像、视频和音频并发设置；
- 检查是否有长时间停留在运行中的异常任务；
- 查看供应商 RPM 配额；
- 检查前序任务是否尚未完成。

### 磁盘快速增长 {#disk-growth}

在 Compose 目录中重点检查数据根各部分的占用：

```bash
du -sh projects/*
find projects/projects -type f -size +500M
```

不要直接删除当前项目引用的文件。优先通过项目归档、清理无用项目和保留必要版本控制空间。

## 11. 上线检查清单 {#go-live-checklist}

- [ ] 使用 PostgreSQL；
- [ ] 固定 Release 镜像版本；
- [ ] 首次启动前设置强 `AUTH_PASSWORD`，或登录后立即修改初始密码；
- [ ] 设置固定 `AUTH_TOKEN_SECRET`；
- [ ] 配置 HTTPS；
- [ ] 不直接暴露 `1241`；
- [ ] 验证 SSE 可正常工作；
- [ ] 备份数据库和数据根；
- [ ] 完成一次恢复演练；
- [ ] 配置磁盘和健康检查告警；
- [ ] 确认模型 API Key 不出现在日志和仓库；
- [ ] 阅读许可证和 `NOTICE`。
