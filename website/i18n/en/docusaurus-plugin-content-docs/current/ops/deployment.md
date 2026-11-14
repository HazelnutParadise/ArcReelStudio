---
id: deployment
title: Deployment and Operations
sidebar_position: 1
update_docs: fact-check
---

# Deployment and Operations {#deployment}

This document covers ArcReel's default deployment, PostgreSQL production deployment, environment variables, data persistence, upgrades, backups, restoration, reverse proxies, and troubleshooting. See the [Security Policy](https://github.com/HazelnutParadise/ArcReelStudio/blob/main/SECURITY.md) for the official support boundaries and the [Security Threat Model](https://github.com/HazelnutParadise/ArcReelStudio/blob/main/docs/security/threat-model.md) for the complete trust boundaries.

## Choosing a Deployment Mode {#choose-deployment-mode}

| Scenario | Recommended Method | Database | Notes |
|---|---|---|---|
| First-time evaluation or light personal use | `deploy/` | SQLite | Minimal configuration and the fastest startup |
| Long-running, concurrent, or production service | `deploy/production/` | PostgreSQL | Better suited to concurrency, backups, and operations, but provides no user isolation |
| An existing PostgreSQL database | `deploy/` with `DATABASE_URL` set | External PostgreSQL | Starts no database container; see [Connect to an Existing PostgreSQL](#external-postgresql) |
| Local development | Run from source | SQLite or PostgreSQL | See the [Contributing Guide](../dev/contributing.md) |

Regardless of the method you choose, project images, videos, and other generated assets must be stored persistently.

An ArcReel instance is one shared workspace: several accounts can sign in, every member sees all projects and shares the provider credentials and settings, and administrators can also manage members. ArcReel has no per-project permissions and does not isolate members' data from each other, so invite only collaborators you trust. A PostgreSQL production deployment does not add tenant isolation either.

## 1. Default Deployment: SQLite {#sqlite-deployment}

### 1.1 Start {#sqlite-start}

```bash
git clone https://github.com/HazelnutParadise/ArcReelStudio.git
cd ArcReelStudio/deploy

cp .env.example .env
```

Edit `.env`:

```dotenv
AUTH_USERNAME=admin
AUTH_PASSWORD=set a strong password
AUTH_TOKEN_SECRET=set a long-lived random secret
# LOG_LEVEL=INFO
```

`AUTH_USERNAME` and `AUTH_PASSWORD` only create the default administrator on first startup, while no account exists yet; changing them later does not affect existing accounts. If `AUTH_PASSWORD` is empty, ArcReel generates an initial password and saves it to `runtime/initial-admin-password` in the data root (`projects/runtime/initial-admin-password` under the host data location for Docker deployments, which is the Compose directory by default; see [Persistent Directories](#sqlite-volumes)). The file is deleted once the default administrator changes the password.

Generate a random secret:

```bash
openssl rand -hex 32
```

Start the service:

```bash
docker compose up -d
```

Verify it:

```bash
docker compose ps
docker compose logs --tail=100 arcreel
curl http://localhost:1241/health
```

### 1.2 Persistent Directories {#sqlite-volumes}

The default Compose configuration mounts:

| Host Path | Container Path | Contents |
|---|---|---|
| `deploy/projects/` | `/app/projects` | Data root: projects, generated assets, the default SQLite database, logs, Vertex AI credentials, and all other runtime data |
| `deploy/claude_data/` | `/root/.claude` | Agent runtime data |

The table shows the default locations. After you set `ARCREEL_HOST_DATA_DIR` in `deploy/.env`, `projects/` and `claude_data/` are placed under that directory instead. For example, `ARCREEL_HOST_DATA_DIR=/srv/arcreel` maps to `/srv/arcreel/projects/` and `/srv/arcreel/claude_data/`. A relative path is resolved against `deploy/` and must start with `./` or `../`, for example `./data`. A bare `data` is read by Compose as a named volume, and the container does not start. The paths inside the container stay the same, so you do not need to change the in-container data root `ARCREEL_DATA_DIR`.

To move an existing deployment to a new location:

1. Run `docker compose down` in `deploy/`;
2. Move `projects/` and `claude_data/` to the new directory as a whole, preserving file ownership and permissions (for example with `mv` or `rsync -a`);
3. Set `ARCREEL_HOST_DATA_DIR` in `deploy/.env`, then run `docker compose up -d`.

`deploy/.env` only supplies Compose interpolation values and is not mounted into the container. The container receives exactly the environment variables listed under `environment` in `docker-compose.yml`.

`deploy/projects/` is ArcReel's data root (`ARCREEL_DATA_DIR`, `/app/projects` inside the container). Projects live in its `projects/` subdirectory, and all other runtime data sits alongside it:

```text
deploy/projects/               data root
├── projects/<project-name>/   projects and generated assets
├── deleted_projects/          deleted projects, kept for 30 days
├── global_assets/             global asset library
├── users/<user_id>/memory/    Agent user memory
├── arcreel.db                 default SQLite database (with -wal / -shm)
├── logs/                      application logs
├── vertex_keys/               Vertex AI credential files
├── trial_runs/                output of endpoint "Test connection" runs
└── runtime/                   migration markers, generation admission locks, image thumbnail cache, and other runtime state
```

Only directories under `projects/` whose names contain letters, digits, or hyphens and that contain a `project.json` file count as projects. No other entry in the data root appears in the project list. The diagnostic logs downloaded from Settings → About list the actual locations of the data root and each kind of data above.

> Back up the entire data root, not just the database. The database stores tasks, configuration, and index information, while the project directories store source media and generated files. They must remain consistent.

The project trash is stored in `projects/<project-name>/.arcreel/trash/`. A full data-root backup keeps its deletion records; a project ZIP export does not include it. Deletion records are kept for 30 days from deletion and are cleared at application startup and periodically while it runs. Restoring a backup does not reset a record's retention period.

A deleted project moves as a whole, together with its project trash, to `deleted_projects/<project-name>#deleted-<deletion-time>/`. It is also kept for 30 days and cleared the same way. You can restore or permanently delete it from Deleted projects on the project list page. If the original name is already taken, the project is restored under a new name with a suffix.

## 2. Production Deployment: PostgreSQL {#postgresql-deployment}

### 2.1 Start {#postgresql-start}

```bash
cd "$(git rev-parse --show-toplevel)/deploy/production"
cp .env.example .env
```

Edit `.env`:

```dotenv
AUTH_USERNAME=admin
AUTH_PASSWORD=set a strong password
AUTH_TOKEN_SECRET=set a long-lived random secret
POSTGRES_PASSWORD=set a database password
# LOG_LEVEL=INFO
```

Generate a password containing only hexadecimal characters where possible:

```bash
openssl rand -hex 16
```

The default Compose configuration passes the raw `POSTGRES_PASSWORD` to PostgreSQL and also interpolates it into the password segment of `DATABASE_URL`. If the password contains URL-reserved characters such as `@`, `:`, `/`, `?`, `#`, or `%`, the password in the connection URI must be percent-encoded. Do not put the encoded value directly in `POSTGRES_PASSWORD`: PostgreSQL needs the raw password, while only the URI needs the encoded form.

When special characters are required, keep the raw and encoded values separate in `.env`:

```dotenv
POSTGRES_PASSWORD='p@ss/word'
POSTGRES_PASSWORD_URLENCODED=p%40ss%2Fword
```

Then change only the password segment of `DATABASE_URL` in `deploy/production/docker-compose.yml` to `${POSTGRES_PASSWORD_URLENCODED}`; leave the PostgreSQL container's `POSTGRES_PASSWORD` unchanged. You can generate the encoded value with `urllib.parse.quote(raw_password, safe="")`. If you do not want to maintain this Compose customization, use the hexadecimal password described above.

Start the service:

```bash
docker compose up -d
```

Verify it:

```bash
docker compose ps
docker compose logs --tail=100 postgres
docker compose logs --tail=100 arcreel
curl http://localhost:1241/health
```

### 2.2 PostgreSQL Persistent Directories {#postgresql-volumes}

| Host Path | Contents |
|---|---|
| `deploy/production/pgdata/` | PostgreSQL data directory |
| `deploy/production/projects/` | Data root: projects, media assets, logs, Vertex AI credentials, and so on; same layout as the [default deployment](#sqlite-volumes), without the database |
| `deploy/production/claude_data/` | Agent runtime data |
| `deploy/production/.env` | Authentication and database configuration; only supplies Compose interpolation values and is not mounted into the container |

The locations of `pgdata/`, `projects/`, and `claude_data/` are likewise set by `ARCREEL_HOST_DATA_DIR` in `deploy/production/.env`; when it is not set, they are under `deploy/production/`. Move them with the same steps as the [default deployment](#sqlite-volumes), and move all three directories. `pgdata/` is owned by the user inside the PostgreSQL container, so preserve its ownership and permissions when moving it; otherwise PostgreSQL cannot start.

`pgdata/` stores only the PostgreSQL cluster, while `projects/` is the data root and stores project metadata, media assets, and the remaining runtime data. Both directories must be persisted and backed up together. The production deployment uses PostgreSQL through `DATABASE_URL` and does not use `deploy/production/projects/arcreel.db`. Do not copy SQLite files into `pgdata/`, and do not treat these two directories as interchangeable database backups.

### 2.3 Database Migrations {#database-migrations}

ArcReel runs Alembic migrations at application startup to upgrade the database schema to the current version.

The schema is built from a single baseline migration. A database created by upstream ArcReel or by an early development build of this project has no matching starting point; startup stops with `Can't locate revision identified by '…'`, so start with a new database instead.

You must still create a backup before upgrading. Automatic migration handles schema upgrades; it does not replace a rollback-capable data backup.

### 2.4 Connect to an Existing PostgreSQL {#external-postgresql}

If you already run a PostgreSQL server, you do not need the database container that ships with Compose. Which Compose file you use decides whether a database container starts: `deploy/` starts none, and `deploy/production/` always starts one. `DATABASE_URL` only decides which database ArcReel connects to.

1. Create a dedicated database and account for ArcReel in PostgreSQL. The account needs permission to create tables. Do not share the database with other services.
2. Set `DATABASE_URL` in `deploy/.env`:

   ```dotenv
   DATABASE_URL=postgresql+asyncpg://arcreel:password@db.example.com:5432/arcreel
   ```

3. Start it from `deploy/`:

   ```bash
   docker compose up -d
   ```

4. Check the startup log to confirm that migrations finished without connection errors:

   ```bash
   docker compose logs --tail=100 arcreel
   ```

Notes:

- Use `deploy/`, not `deploy/production/`. Production Compose fixes `DATABASE_URL` under `environment`, which overrides the value in `.env`, and it still starts its own PostgreSQL container.
- Only PostgreSQL is supported, and the URL must start with `postgresql+asyncpg://`.
- ArcReel runs database migrations automatically at startup, so an empty database is enough.
- When the database runs on the same host, do not use `localhost` as the host name, because `localhost` inside the container points to the container itself. With Docker Desktop on macOS and Windows, use `host.docker.internal`. On Linux, use the host's LAN IP, or add `extra_hosts: ["host.docker.internal:host-gateway"]` to the `arcreel` service in `docker-compose.yml`.
- If the password contains URL-reserved characters, percent-encode it in the URL as described in the [production deployment start section](#postgresql-start).
- The database administrator is responsible for database backups. The `projects/` data root must still be persisted as in the [default deployment](#sqlite-volumes) and backed up together with the database.
- If you already have data in SQLite, migrate it first by following [Migrate from SQLite to PostgreSQL](./migrate-to-postgres.md), then switch `DATABASE_URL`.

## 3. Environment Variables {#environment-variables}

The default deployment examples currently include these core variables:

| Variable | Default | Recommendation |
|---|---|---|
| `ARCREEL_IMAGE_TAG` | `main` for the default deployment, `latest` for the production deployment | Image tag, read only by Compose; pin a version in production, see [Pin a Version](#pin-version) |
| `ARCREEL_HOST_DATA_DIR` | The Compose directory | Data location on the host, read only by Compose; see [Persistent Directories](#sqlite-volumes) |
| `AUTH_USERNAME` | `admin` | Username of the default administrator, used only on first startup while no account exists |
| `AUTH_PASSWORD` | Empty | Password of the default administrator, used only on first startup; when empty an initial password is generated, see [Accounts and Members](#accounts) |
| `AUTH_TOKEN_SECRET` | Empty | Set a fixed, long-lived random value; if left empty, ArcReel generates one, saves it to `runtime/auth-token-secret` under the data root, and reuses it after restarts |
| `AUTH_ENABLED` | `true` | Never disable for remote deployments; `false` leaves every management endpoint unauthenticated |
| `LOG_LEVEL` | `INFO` | Temporarily change to `DEBUG` while troubleshooting, then restore it |
| `POSTGRES_PASSWORD` | None | Required and must be set only for production deployments |
| `TZ` | `Asia/Taipei` | Can be overridden in the Compose environment |
| `DATABASE_URL` | Default SQLite path | Production Compose sets the PostgreSQL URL automatically; to use an external database, set it in the default deployment's `.env` (see [Connect to an Existing PostgreSQL](#external-postgresql)) |
| `ARCREEL_DATA_DIR` | `projects` | Data root; projects, the default SQLite database, logs, and Vertex credentials all live under it. Docker deployments fix it to `/app/projects` inside the container; use `ARCREEL_HOST_DATA_DIR` to change the location on the host |
| `CORS_ORIGINS` | Wildcard | When narrowed to an allowlist, browser MCP client origins must be listed too |
| `ARCREEL_OFFICIAL_SERVICE_URL` | Built-in official service address | The official service behind market install counts, ratings, and submissions; set it to empty to turn it off entirely, leaving the market to read market sources only |

Notes:

- Changing `AUTH_TOKEN_SECRET` invalidates existing login tokens. A value you set takes precedence, and the secret file generated under the data root is no longer used. When no value is explicitly set, deleting the secret file and restarting generates a new secret and invalidates existing logins.
- After editing `.env`, run `docker compose up -d` in the Compose directory to recreate the container. `docker compose restart` and automatic container restarts keep the environment variables captured when the container was created and do not reload `.env`.
- Compose passes only the variables listed under `environment` in `docker-compose.yml` into the container. To pass a variable not listed in the table, add a line `NAME: ${NAME}` under `environment` and set its value in `.env`. Earlier Compose files passed the whole `.env` into the container through `env_file`; after the upgrade, variables not listed in the table (for example `HTTPS_PROXY`) are no longer passed in, so add back the ones you need this way.
- `AUTH_ENABLED=false` is only for a local machine protected by its own network boundary. Compose publishes port `1241` on all host interfaces by default, so never disable authentication for remote deployments. While authentication is off, startup logs a WARNING.
- `.env` may contain secrets. Do not commit it to version control.
- Vertex credential files should be readable only by the user who runs ArcReel.
- File logs are always written to `logs/` under the data root. Set `ARCREEL_LOG_FILE_DISABLED=true` if you only want logs on stdout.
- Third-party model API keys are normally managed on the ArcReel Settings page. Do not include them in public documentation.

The remote MCP endpoint is `/mcp` and always requires an API Key with an `arc-` prefix; it never permits anonymous access, even when `AUTH_ENABLED=false`. Remote access needs no extra `MCP_*` configuration: paste the endpoint URL shown under "External agent access" in Settings, together with an API Key created under "Access tokens", into your client, and connect through an HTTPS reverse proxy, VPN, or secure tunnel that preserves long-lived SSE connections.

### 3.1 Accounts and Members {#accounts}

On first startup, ArcReel creates the default administrator from `AUTH_USERNAME` / `AUTH_PASSWORD`. After that, manage accounts under Settings › Accounts & members:

- Every member can change their own password or sign out there. Changing the password signs out the member's other devices.
- Administrators can add members, make a member an administrator, disable accounts, or reset a member's password. Disabling, changing the role, and resetting the password all end that member's existing sessions.
- At least one active administrator must remain; administrators cannot disable themselves or remove their own administrator role.

Usernames may contain only lowercase letters, digits, and `.` `_` `@` `-`, and sign-in is case-insensitive. `embedded-agent` is reserved for the embedded Agent and cannot be used as a username. Passwords must be at least 8 characters.

If you forget the password, run this in the Compose directory:

```bash
docker compose exec arcreel uv run python -m scripts.manage_users reset-password admin
```

The command asks you to enter the new password twice and does not show what you type; when you cannot answer prompts, add `--password <new password>` instead. The `list` subcommand lists all accounts. For source deployments, run `uv run python -m scripts.manage_users ...` from the repository root.

When you upgrade from an earlier version that had only one `.env` account, the first startup turns the current `AUTH_USERNAME` / `AUTH_PASSWORD` into the default administrator, so the existing password keeps working. Sessions issued before the upgrade all end, and everyone needs to sign in again once. If the old `AUTH_USERNAME` does not meet the username rules above (for example, it contains spaces or Chinese characters), the default administrator is renamed to `admin` and the startup log records the change; sign in as `admin` from then on.

Several members can open the same project at the same time and edit it together, as in a shared document:

- The right side of the top bar shows the other members in the project; open it to see which episode each of them is viewing. You also see the other members' mouse pointers and names on the page.
- In the project overview, the creative brief, characters / scenes / props / products, character derivatives, an episode's own source text, the shot details, reference video units, project settings, global asset library entries and Agent memory files, each person's changes appear for the others right away. A member editing the same field shows up as a colored cursor with their name in that field.
- These editors have no Save button: the server merges everyone's input and writes it to the project files shortly after typing stops. When two people type in the same text at once, both keep their words; Ctrl / ⌘ + Z undoes only your own changes.
- When the Agent or a background task changes what you are editing, the change merges into the editor without overwriting what you are still typing.
- You can keep editing while disconnected; changes stay on your device and sync automatically once you reconnect, and the editor shows "Offline" in the meantime. If the collaboration service can't be reached (for example, the reverse proxy doesn't forward WebSockets), the editors fall back to editing and then saving.
- When a project settings change isn't valid yet (for example, switching to TTS narration before choosing a voice model), the reason shows below the editor and the change stays until it's complete.
- Providers and credentials, custom endpoints and the remaining global settings are still edited and then saved; the later save wins when two members save at the same time.

The list of online members and the content being edited together live only in the service process's memory, so run a single service process. The service writes any unsaved content before it shuts down, and pages reconnect automatically after a restart.

### 3.2 GPU Encoding {#gpu-encoding}

The image ships an ffmpeg build with NVIDIA NVENC support. When the container can use an NVIDIA GPU, final cuts encode their video on the GPU; without a GPU they fall back to CPU encoding automatically, with no extra configuration.

To enable it on an NVIDIA GPU host:

1. Install the NVIDIA driver and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) on the host.
2. Add the following to `.env` in the Compose directory:

   ```dotenv
   COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml
   ```

   On Windows hosts Compose separates files with a semicolon, so write `COMPOSE_FILE=docker-compose.yml;docker-compose.gpu.yml` instead.

3. Run `docker compose up -d` to recreate the container.

GPU encoding is active once the startup log reports that it is available. You can turn it off under Settings › General; final cuts then always encode on the CPU.

Do not load `docker-compose.gpu.yml` on hosts without an NVIDIA GPU: Docker refuses to start the container when it cannot provide a GPU.

The GPU only encodes final-cut video; mixing, muxing, and other media processing still run on the CPU. If GPU encoding fails midway, that final cut is re-rendered on the CPU automatically. Only NVIDIA GPUs are supported.

The server does not validate the request `Host` header; the endpoint boundary rests on the API Key enforced on every request. Host ownership belongs to the deployment: restrict `server_name` (Nginx) or the equivalent rule on your reverse proxy so only requests for the expected domain reach ArcReel.

Browser MCP clients need no configuration either while `CORS_ORIGINS` stays at its permissive default; once you narrow it to an allowlist, add the client Origin to it as well. That single allowlist governs both the application API and the MCP endpoint; there is no second MCP-specific list.

Remote MCP offers no OAuth authorization and publishes no OAuth protected-resource metadata (RFC 9728). Clients that only support OAuth discovery and cannot be given a Bearer credential cannot connect.

ArcReel's sandbox requires provider secrets to be absent from the parent process environment. If any of the following credential environment variables has a non-empty value, the service refuses to start and prompts you to move the credential to the Web UI Settings page:

- `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN`
- `ARK_API_KEY` / `XAI_API_KEY` / `GEMINI_API_KEY` / `VIDU_API_KEY`
- `DASHSCOPE_API_KEY` / `MINIMAX_API_KEY` / `AGNES_API_KEY` / `OPENAI_API_KEY`
- `GOOGLE_APPLICATION_CREDENTIALS` (upload Vertex credentials on the Settings page; they are stored in `vertex_keys/` under the data root)

Non-secret configuration such as `ANTHROPIC_BASE_URL` and model names does not independently cause startup to be rejected, but it is still best managed in the Web UI together with the corresponding credentials.

## 4. Health Checks and Logs {#health-and-logs}

### 4.1 Health Check {#health-check}

Compose uses:

```text
GET /health
```

To check manually:

```bash
curl -f http://localhost:1241/health
```

This endpoint requires no authentication. In official images, the response includes a `commit` field holding the commit sha the image was built from, which tells you which version the instance is running; when run directly from source, it is `null`.

### 4.2 View Logs {#view-logs}

```bash
# Last 200 lines
docker compose logs --tail=200 arcreel

# Follow continuously
docker compose logs -f arcreel

# Production database logs
docker compose logs -f postgres
```

File logs are stored in `logs/` under the data root, which is `deploy/projects/logs/` in the default deployment.

Do not paste complete logs directly into a public issue. Remove the following before submitting them:

- API keys;
- Tokens;
- Credentials embedded in Base URLs;
- User input;
- Private information in local file paths.

## 5. Upgrades {#upgrade}

### 5.1 Before Upgrading {#before-upgrade}

1. Read the [CHANGELOG](https://github.com/HazelnutParadise/ArcReelStudio/blob/main/CHANGELOG.md) and the target release notes;
2. Check for breaking changes;
3. Back up the data root and the database; see [Backup and Restore](#backup-and-restore);
4. Record the current image version;
5. Perform the upgrade during an acceptable maintenance window.

> ArcReel does not support downgrades. An upgrade may rewrite the database schema and project structures, and older versions cannot read the upgraded data. To go back to an older version, stop the service and restore the backup taken before the upgrade.

### 5.2 Upgrade the Default Deployment {#upgrade-sqlite-deployment}

From `deploy/`:

```bash
# Back up first; see below
docker compose pull
docker compose up -d

docker compose ps
docker compose logs --tail=100 arcreel
curl -f http://localhost:1241/health
```

### 5.3 Upgrade the Production Deployment {#upgrade-postgresql-deployment}

From `deploy/production/`:

```bash
# Back up the database and the data root projects/ first
docker compose pull
docker compose up -d

docker compose ps
docker compose logs --tail=100 postgres
docker compose logs --tail=200 arcreel
curl -f http://localhost:1241/health
```

The application runs database migrations when it starts. Do not skip multiple versions and upgrade directly without a backup.

### 5.4 Moving In from Upstream ArcReel {#from-upstream-arcreel}

This version does not take over an upstream ArcReel installation. The data root is read and written only in the layout shown in [Persistent Directories](#sqlite-volumes); the old flat layout, the old default database file name `.arcreel.db`, the `logs/` directory under the code directory, and the old system configuration file are neither moved nor imported. The database can only be created from an empty database; an upstream database cannot be attached.

To bring projects over from upstream, first open them in upstream ArcReel so they are upgraded to schema 19 or later, export them as archives, and import those archives into this version; see [Project Schema Migrations](#project-schema-migrations). Enter provider settings and credentials again on the Settings page.

### 5.5 Project Schema Migrations {#project-schema-migrations}

In addition to database migrations, application startup upgrades each project in the `projects/` directory under the data root. Only directories whose names contain letters, digits, or hyphens and that contain a `project.json` file count as projects for migration and stale backup cleanup.

This version can only upgrade projects at schema 19 or later. A project whose `project.json` records an earlier schema version, or no schema version at all, is not migrated, and migration does not rewrite its files (source encoding conversion included): at startup ArcReel only writes a migration failure record, `.migration_failure.json`, into the project directory, the project page header shows "Project version too old", generation is turned off, and the other projects upgrade as usual. Restoring such a project from "Deleted projects" behaves the same way. It cannot be repaired or retried in this version. Importing such an archive is refused outright and leaves no data behind. To keep using such a project, open it in upstream ArcReel first, let it upgrade to schema 19 or later, export an archive, and import that archive into this version.

Before committing a migration, ArcReel creates adjacent backups with a `.bak.v<source-version>-<timestamp>` suffix for:

- `project.json`;
- Formal script files registered in `project.json`, and the script plan drafts of the same episodes;
- An existing `.arcreel_artifacts.json`;
- `versions/versions.json`, for migrations that rewrite version records.

Project migration is safe to retry. If a previous startup was interrupted while creating backups or committing changes, the next startup validates the project again and ensures that at least one backup exactly matches the pre-migration content before continuing. Identical backups are kept only once, so repeated failures do not pile up copies. These automatically generated project-level backups exist only for migration recovery; they do not replace deployment-level backups of the database and the entire data root.

After a migration completes, ArcReel writes `.migration_report.json` to the project directory. It holds two groups: "Changed" lists what the migration changed (choices made while normalizing legacy shapes, placeholder definitions added, structure repaired), and "Not carried over" lists files that were left in place but not registered (unreadable files, and legacy narration audio with no recorded synthesis settings). Generation gaps, units that need replanning, and artifacts left unregistered because their basis cannot be computed (for example a script plan whose source text is not UTF-8) are not in the report. The report is informational only and never blocks any operation. When it is not empty, the project page header shows a one-time notice, "This upgrade changed N items", that opens the read-only report; once dismissed it does not come back. The production status API returns the `migration_report` field only while the report is non-empty and not yet dismissed.

Archive import runs the same migration chain, and whatever version exported the archive, files the import could not read are added to the same report. When the report is not empty, a "Confirm before importing" dialog shows that report before the project appears in the project list. "Cancel" leaves no project data behind; "Confirm import" completes the import, and the project page does not show the same report again. When the report is empty, the import goes through directly; re-importing a healthy project exported by the current version leaves the report empty. If the migration chain fails during import, the import fails with the specific reason and no data from the archive is kept.

Exporting a project archive only reads the project and never changes it. When the state of an artifact cannot be confirmed, the export does not fail. It carries what is there and the export diagnostics list, item by item, what you will see after import:

- A version file is missing or damaged, but the formal file matches the version record's content fingerprint: the archive puts the version file back from the formal file, listed under "Auto-fixed". After import the state is the same as now, and restoring that version and rendering work as usual. The version file in the source project stays as it is.
- A video or narration file is still there but can no longer be confirmed as the selected version (the version file is missing and does not match the record, the version record is gone, the file was replaced, or it was already stale after the previous import): it is included and shows as stale after import, still usable, and stays stale through further exports and imports. Videos and narration that are stale now do not become up to date through an export; regenerating them or switching versions in the version history brings back the normal judgement.
- An artifact file is no longer in the project, or is a symbolic link or inside a symbolically linked folder: its artifact record is left out, the references in scripts or `project.json` that import requires and that point to it are cleared in the archive, and after import it shows as missing.
- Parts of the version history that import refuses (malformed entries, or version records pointing outside the version history folder): the archive leaves those parts out and includes the other versions.
- Subtitles and narration presentations that no longer match the video or narration version they were built from, or that were built from an older version a "current version only" archive does not include: their records are left out. They are built locally at no cost, and after import they are rebuilt from the selected media the next time you preview, edit or export a Jianying draft.
- The artifact manifest cannot be read: the archive rebuilds the artifact records from the project files and version records. Videos and narration are judged against the generation basis in their version records; those that are stale now, or cannot be confirmed as the selected version, show as stale after import; other artifacts show as up to date after import and their existing stale marks are not kept.

The export stops, with the reason and the location of the problem, only when the project keeps changing during the export (try again later), when project files, scripts, version records or grid records cannot be read (including files and folders without read permission) or are damaged, when remote materials cannot be retrieved, or when the disk is full (free up space and try again).

On import, videos and narration whose version file is missing from the archive or does not match its record are imported as stale and listed in the import result; when the formal file matches the version record, the import puts the version file back, and switching back to that version in the version history makes it up to date again. Archives without artifact records (for example packed by hand) register the files again; the import puts version files back first, so such videos and narration show as up to date. When a formal file in the archive does not match the content fingerprint recorded at export, the import is refused as before.

Migration rejects a whole project only for these problems: the project's schema version is earlier than 19; `project.json` or a script cannot be read (it is not valid JSON, or it lacks content that determines its shape, such as the content type); the version records `versions/versions.json` or the artifact manifest `.arcreel_artifacts.json` cannot be read; the item structure of a script is broken (for example, an item list contains an entry that is not an object); or the archive itself is unsafe. A migration that cannot finish (out of disk space, a write failure) still blocks; the project stays in its pre-upgrade state, and you can retry after fixing the cause. All other data problems are handled item by item, and existing content is not discarded:

- Legacy shapes written by the normal workflow of earlier versions are normalized automatically: when a script does not record its episode, or records one that differs from its binding, the episode list wins; within one asset type, entries whose names match after trimming surrounding whitespace and Unicode normalization, ignoring case, are reduced to the first one: derivatives of a removed entry move to the kept one (a derivative whose name differs from an existing one only in case merges into it), and references in scripts and script plans that use the removed name's casing are rewritten to the kept name, and the removed entry's asset sheet registration is dropped (if the kept entry had no registration of its own, its sheet shows as needing generation); script items with a missing or duplicate ID get a new ID (duplicates from the second one on), and media files under the original ID stay with the item that keeps it; when two episodes have an item with the same ID, the media stays with the episode the ID prefix names (or, if it names neither, the one listed first), and the item in the other episode gets a new ID; that episode's registrations under the original ID are dropped so they no longer hold the other episode's media file; in that episode, a grid image whose members include the original ID and the storyboards cut from it need regenerating, and the matching clips in edit timelines show as deleted units.
- When an asset sheet, reference image, reference audio, or merchandise photo points to a file under another existing asset (including derivative images), the migration copies it under this asset and rewrites the reference, leaving the original file with the original asset. Copying uses extra disk space; if the destination under this asset already holds different content, the existing file is first moved to a kept copy. Copying does not change an asset sheet's production status: one that was up to date before the rewrite stays up to date, and one that was already outdated still needs regenerating. The copy destination, the reference, and the asset sheet registration are committed in one transaction and restored if it fails. A source path that contains a symbolic link is not copied; if the destination directory is a symbolic link, the migration fails, and you need to restore it to a real directory inside the project before retrying; if the destination file is a symbolic link, only the link itself is replaced and the file it points to is left unchanged. The locations of copies and kept copies are listed under "Changed".
- When normalization has to choose, the other copy is kept next to the original file with a `.kept.v<from-version>-<timestamp>` suffix. Kept copies are never cleaned up automatically, and the "Changed" entry in the report shows where each one is.
- When a single grid record, script plan draft, or media file cannot be read, the file stays where it is, is not registered, and is listed under "Not carried over"; the rest of the project migrates normally. A video or narration audio file whose selected version snapshot is missing cannot be confirmed as the selected version, so it is likewise kept in place and listed under "Not carried over". When a script in an imported archive references an undefined character, scene, or prop, the import adds an empty definition for it and lists it under "Changed".

For drama projects whose `project.json` has no aspect ratio field, storyboard freshness is judged against the drama default ratio of 16:9, matching what generation actually uses. Storyboards in such projects that were previously recorded against 9:16 show as out of date; regenerate them as needed.

For uploaded storyboards and videos, the import adds or rewrites artifact records using the uploaded bytes when the selected version is still a manual upload and the file exactly matches its upload snapshot. They show as current even with an empty prompt or missing referenced asset sheets. Later prompt, asset, or style edits do not make them stale, and missing-only batches preserve them. Artifacts whose selected version is generated or whose file differs from the upload snapshot are not backfilled as uploads.

For generated storyboards, if a referenced asset was deleted or renamed, or a referenced character, scene, or prop has no registrable sheet (it was never generated, its file is missing, or its description is empty), the storyboard is still registered and shows as current; the missing reference is recorded in its artifact record. Regenerating that storyboard is refused until the gap is filled. Product sheets are optional: a product with no declared sheet can use only its originals, or text alone if no originals are declared either. An unavailable declared product sheet or an unreadable declared product original is handled the same way. Once you restore the asset registration or sheet, re-upload missing originals, or clear their invalid fields, the storyboard shows as stale; regenerate it as needed.

Asset sheets and derivative sheets follow the same rule: if a character or product declares an original image that cannot be read, or the asset description is empty, the sheet is still registered and shows as current; a derivative whose base sheet has such a gap is registered as well. Regenerating is refused until you re-upload the original or clear the invalid original field and fill in the description; after that, the sheet shows as stale. A character or product whose original image is lost cannot generate an asset sheet either, and is handled the same way.

If a project migration fails, preserve the files and inspect the startup logs. Do not manually change the schema version or delete backup files or kept copies. Repair the damaged project files or permissions, then restart the service.

### 5.6 Pin a Version {#pin-version}

The image tag used by Compose is set by `ARCREEL_IMAGE_TAG` in `.env`:

| Tag | Content | Published |
|---|---|---|
| `main` | Latest build of the main branch; default for the default deployment | After every merge into main |
| `X.Y.Z`, `X.Y`, `latest` | Releases; `latest` is the default for the production deployment and points to the latest stable release | After a `vX.Y.Z` release |

A pre-release (such as `vX.Y.Z-rc.1`) only publishes its own version tag and does not update `latest`. Until the first release has been published, `latest` does not exist; set `ARCREEL_IMAGE_TAG=main` for the production deployment until then.

For production, pin a specific release:

```bash
# deploy/production/.env
ARCREEL_IMAGE_TAG=X.Y.Z
```

Run `docker compose up -d` after setting it. Changing this value explicitly when upgrading reduces the risk of unintentionally pulling a new version.

## 6. Backup and Restore {#backup-and-restore}

After the whole site is moved to a different absolute path, the application relocates the storage of existing Agent sessions to match the current project directories at startup, so conversations can continue with their context. Sessions of deleted projects follow the new name the project is restored under. With `ARCREEL_SDK_SESSION_STORE=off`, sessions are stored only in the SDK's local directory, so keep that directory when migrating (`claude_data/` for Docker, or `CLAUDE_CONFIG_DIR` or the default `~/.claude` for native deployments). When the same session has records in several source locations, or the destination already has a record, they are not merged automatically; a failed move logs a warning, and the service still starts.

After object storage is enabled under **Save new images to**, the content of remote images lives only in your TOS bucket; backups of the data root and the database contain only their records and a local cache that can be cleaned up. When restoring a backup, the connection must still point to the original bucket, and the objects in the bucket must be kept as well. ArcReel deletes image objects that are no longer used, so objects of projects or versions deleted after the backup may already be gone from the bucket, and those images cannot be read after restoring an older backup. If you need to restore to an earlier point in time, back up the objects under `arcreel-materials/` while writes are stopped (or enable versioning on the bucket), and put them back into the original bucket under the same keys when restoring; see [Save New Images to Object Storage](../guide/providers.md#remote-image-storage).

### 6.1 Back Up a SQLite Deployment {#backup-sqlite}

The data root already contains projects, the default SQLite database, logs, and Vertex credentials, so a file-system backup only needs to archive the data root plus `.env` and `claude_data/`.

First identify the data location on the host, then stop writes. It is `deploy/` by default; if you set `ARCREEL_HOST_DATA_DIR` in `.env`, set `host_dir` to that value:

```bash
cd deploy

host_dir="."
# Set to ARCREEL_HOST_DATA_DIR if you set it, for example: host_dir="/srv/arcreel"
data_dir="$(cd "${host_dir}/projects" && pwd)"

docker compose stop arcreel
```

Create the backup:

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

Archiving the entire `data_dir` after the service has stopped keeps `arcreel.db` and project assets at the same point in time. The configuration and data archives must use the same timestamp and be stored together. `umask 077` and backup directory mode `0700` restrict access to the credentials and project assets they contain. Do not copy only `arcreel.db` while ArcReel is writing to it. In WAL mode, committed transactions may still reside in `arcreel.db-wal`; losing or mismatching the WAL can cause data loss or corruption. If downtime is not possible, use the SQLite Online Backup API, such as the `sqlite3` `.backup` command, or `VACUUM INTO` to create a consistent snapshot instead of copying the main database file directly with `cp`.

Restart the service:

```bash
docker compose start arcreel
```

To restore:

1. Stop ArcReel;
2. Back up the current directory so you can roll back if files are overwritten;
3. Restore `.env` from the configuration archive to `deploy/` and `claude_data/` to `host_dir`, then extract the paired data archive completely into an empty `data_dir`;
4. Start the service and check `/health`;
5. Open several projects and verify their images, videos, and version history.

### 6.2 Back Up a PostgreSQL Deployment {#backup-postgresql}

Stop the ArcReel application first, but leave PostgreSQL running, so no new writes occur while you back up the database and project files. `host_dir` is the data location on the host; if you set `ARCREEL_HOST_DATA_DIR` in `.env`, set it to that value:

```bash
cd "$(git rev-parse --show-toplevel)/deploy/production"
host_dir="."
# Set to ARCREEL_HOST_DATA_DIR if you set it, for example: host_dir="/srv/arcreel"
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

The database and file backups use the same timestamp and must be stored and restored together. The `projects/` directory in the file backup is the data root and already includes logs and Vertex credentials. The file backup includes the active `docker-compose.yml`, so any `DATABASE_URL` customization required by a special-character password is restored together with `.env`. `umask 077` and backup directory mode `0700` ensure that the host-created SQL file and file archive are readable and writable only by the current user.

`pg_dump` reads `PGPASSWORD` through libpq. The command above sets it only for that `pg_dump` process inside the PostgreSQL container, allowing `docker compose exec -T` to run non-interactively without expanding the password into the host command line. For long-running host-side backup automation, use a PostgreSQL password file with `0600` permissions instead. Never put the password in a script or backup filename.

If `tar` reports `Permission denied`, the mounted directory contains files created by the container's root user that the current host user cannot read. Rerun the corresponding `tar` command with `sudo`, then restrict read access to the backup file when finished.

### 6.3 Restore PostgreSQL {#restore-postgresql}

Before restoring, stop ArcReel but leave PostgreSQL running:

```bash
cd "$(git rev-parse --show-toplevel)/deploy/production"
host_dir="."
# Set to ARCREEL_HOST_DATA_DIR if you set it, for example: host_dir="/srv/arcreel"
docker compose stop arcreel

backup_stamp=YYYYMMDD-HHMMSS
tar -xzf "backups/arcreel-files-${backup_stamp}.tar.gz" .env docker-compose.yml
tar -xzf "backups/arcreel-files-${backup_stamp}.tar.gz" -C "${host_dir}" projects claude_data
```

The file archive restores `.env` and `docker-compose.yml` to `deploy/production/`, and the data root `projects/` and `claude_data/` to `host_dir`. The following procedure also deletes the existing data in the target `arcreel` database. First verify that the database and file backups with the same `backup_stamp` are complete, and rehearse the restoration procedure in an isolated environment.

Recreate an empty database before importing to avoid conflicts with existing schemas or data:

```bash
docker compose exec -T postgres \
  dropdb -U arcreel --maintenance-db=postgres --if-exists --force arcreel

docker compose exec -T postgres \
  createdb -U arcreel --maintenance-db=postgres -O arcreel arcreel

cat "backups/arcreel-db-${backup_stamp}.sql" | \
  docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U arcreel -d arcreel
```

After the database import succeeds, restart the application:

```bash
docker compose start arcreel
curl -f http://localhost:1241/health
```

> The restoration strategy depends on whether you are overwriting an existing database, restoring across versions, and whether the service was still accepting writes when the backup was created. Production environments should regularly perform real restoration drills, not merely verify that backup files exist.

## 7. Reverse Proxy and HTTPS {#reverse-proxy-and-https}

ArcReel does not currently support direct exposure to the public Internet. Private remote deployments must enable authentication and protect traffic with TLS, a VPN, or a secure tunnel. Do not publish port `1241` directly to an untrusted network. Recommended practices:

- Use Nginx, Caddy, Traefik, or a cloud load balancer;
- Configure HTTPS;
- Allow only the proxy server to access the ArcReel container port;
- Preserve long-lived SSE connections;
- Set sufficiently large upload limits and read timeouts.

The official Compose files use `1241:1241` by default, which publishes the backend port on every host network interface. Adding a reverse proxy alone does not close this direct access path. When the reverse proxy runs on the same host, change the `arcreel` service's port mapping before startup so it listens only on loopback:

```yaml
ports:
  - "127.0.0.1:1241:1241"
```

If the reverse proxy runs on a container network or another host, remove any unnecessary host port publishing and use the container network, host firewall, or an equivalent network policy to ensure only the proxy can access the ArcReel backend.

ArcReel handles cache headers and compression itself, so the reverse proxy needs no extra configuration for them:

- Media URLs with a version key (`?v=`, `?fp=`) or pointing to a `versions/` snapshot, and the content-hashed frontend build output under `/assets/`, return `Cache-Control: public, max-age=31536000, immutable`, so browsers reuse their local copy directly;
- Media URLs without a version key return `Cache-Control: no-cache`, so browsers revalidate with the server before each use and receive `304` when the file has not changed;
- The page entry HTML returns `no-store`, so browsers load the new frontend after an upgrade;
- Text responses such as JSON, JS, CSS, and HTML are gzip-compressed; SSE event streams, images, audio, and video are not compressed.

The reverse proxy should pass these response headers through unchanged. Do not override them with `expires`, `add_header Cache-Control`, or `proxy_hide_header`.

Nginx example. The example splits out the media file paths: SSE and regular API traffic run with proxy buffering off so events reach the browser in real time, while `/api/v1/files/` and `/api/v1/global-assets/` run with proxy buffering on so Nginx receives images and videos first and releases the backend connection early.

```nginx
server {
    listen 443 ssl http2;
    server_name arcreel.example.com;

    ssl_certificate /etc/letsencrypt/live/arcreel.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/arcreel.example.com/privkey.pem;

    client_max_body_size 2g;

    # Compress text types only. Nginx does not recompress responses ArcReel has already compressed.
    # Do not add text/event-stream: compression buffering delays SSE events. Images, audio, and video are already compressed; do not add them either
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/markdown application/json application/javascript image/svg+xml;

    # Project media and global assets: read-only GET, buffering on
    location ~ ^/api/v1/(files|global-assets)/ {
        proxy_pass http://127.0.0.1:1241;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering on;
    }

    # WebSocket for live collaboration: forward the upgrade, or editors fall back to edit-then-save
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

        # ArcReel uses SSE to push Agent replies and project events
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

Certificate configuration depends on your infrastructure. You can use ACME/Let's Encrypt or certificates managed by your cloud platform.

## 8. Container Permissions and the Agent Sandbox {#container-permissions-and-sandbox}

ArcReel strictly checks the Agent sandbox at startup on Linux and macOS and refuses to start if the required tools are missing or unavailable. Native Windows does not provide `bwrap`, so ArcReel automatically falls back to a restricted Bash command allowlist. This mode supports only project creation and basic workflows; use WSL2 or Docker Desktop for production deployments.

| Environment | Tool | Installation |
|---|---|---|
| macOS | `sandbox-exec` | Included with the operating system; no additional installation required |
| Local development on Linux | `bwrap` + `socat` | Ubuntu/Debian: `sudo apt install bubblewrap socat`; Fedora: `sudo dnf install bubblewrap socat`; Arch: `sudo pacman -S bubblewrap socat` |
| Docker | `bwrap` + `socat` | Included in the official image |
| Native Windows | No `bwrap` sandbox | Automatically falls back to a Bash command allowlist; WSL2 / Docker Desktop recommended |

The official Compose configuration gives the Agent Bash sandbox:

- `seccomp:unconfined`
- `apparmor:unconfined`
- `NET_ADMIN`

These settings support `bwrap` isolation and nested network namespaces inside the container, but also give the container more privileges than a typical web application.

Production recommendations:

- Use a dedicated host or, at minimum, a well-isolated runtime environment;
- Do not mount the Docker socket into the container;
- Do not mount any additional, unnecessary host directories;
- Restrict access to administrative pages;
- Keep ArcReel and the base image up to date;
- Give the Agent only the network and file access it needs;
- Treat project input from unknown sources with caution.

Although the Docker image includes `bwrap` and `socat`, user namespace or AppArmor policies on the host may still prevent the sandbox from starting. If startup fails, resolve the `SANDBOX_*` diagnostics shown in the service output. Do not bypass the checks by switching to privileged mode, and do not remove the official Compose sandbox configuration without understanding the consequences.

## 9. Monitoring Recommendations {#monitoring}

At minimum, monitor:

- Whether `/health` is available;
- Whether containers restart frequently;
- Available disk space;
- The growth rate of `projects/`;
- The size of the PostgreSQL data directory;
- Task failure rates;
- Provider rate limits and insufficient quotas;
- The most recent successful backup time.

Media assets usually grow faster than the database. Prioritize capacity alerts for the project directory.

## 10. Common Problems {#troubleshooting}

### Service Fails to Start {#service-wont-start}

```bash
docker compose ps
docker compose logs --tail=300 arcreel
```

Check:

- Whether the production `.env` sets `POSTGRES_PASSWORD`; when it is empty, Compose reports `必須設定 POSTGRES_PASSWORD` and refuses to start;
- Whether port `1241` is already in use;
- Whether the image was pulled successfully;
- Whether the mounted directories are writable;
- Whether `POSTGRES_PASSWORD` is set for production deployments.

### Health Check Fails {#health-check-fails}

```bash
curl -v http://localhost:1241/health
docker compose logs --tail=300 arcreel
```

If the container has just started, check whether database migrations are still running.

### Cannot Log In {#cannot-log-in}

- Usernames are case-insensitive; confirm that an administrator has not disabled the account;
- Changing `AUTH_PASSWORD` in `.env` does not affect existing accounts; if you forgot the password, reset it as described in [Accounts and Members](#accounts);
- If `AUTH_PASSWORD` was empty on first startup, the initial password is in `projects/runtime/initial-admin-password` under the host data location;
- Log in again after changing `AUTH_TOKEN_SECRET`.

### Agent Requests Fail {#agent-request-fails}

- Verify the Agent credentials;
- Check the Base URL and model name;
- Check the network and proxy;
- Check whether the provider is rate-limiting requests;
- Use a small amount of content for verification. Do not run a complete novel through the whole pipeline on the first attempt.

### Tasks Remain Queued {#tasks-stuck-in-queue}

- Review the image, video, and audio concurrency settings;
- Check for abnormal tasks that have remained running for an extended period;
- Check the provider's RPM quota;
- Check whether a preceding task is still incomplete.

### Rapid Disk Growth {#disk-growth}

From the Compose directory, check how much space each part of the data root uses:

```bash
du -sh projects/*
find projects/projects -type f -size +500M
```

Do not directly delete files referenced by current projects. Prefer archiving projects, removing unused projects, and retaining only the necessary space for version history.

## 11. Go-Live Checklist {#go-live-checklist}

- [ ] Use PostgreSQL;
- [ ] Pin the release image version;
- [ ] Set a strong `AUTH_PASSWORD` before the first startup, or change the initial password right after signing in;
- [ ] Set a fixed `AUTH_TOKEN_SECRET`;
- [ ] Configure HTTPS;
- [ ] Do not expose `1241` directly;
- [ ] Verify that SSE works correctly;
- [ ] Back up the database and the data root;
- [ ] Complete a restoration drill;
- [ ] Configure disk space and health-check alerts;
- [ ] Confirm that model API keys do not appear in logs or the repository;
- [ ] Read the license and `NOTICE`.
