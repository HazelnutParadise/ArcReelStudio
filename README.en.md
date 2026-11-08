<h1 align="center">
  <br>
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/logo-animated-light.svg">
    <source media="(prefers-color-scheme: dark)" srcset="frontend/public/logo-animated.svg">
    <img src="docs/assets/logo-animated-light.svg" alt="ArcReel Logo" width="128">
  </picture>
  <br>
  ArcReelStudio
  <br>
</h1>

<p align="center">
  <strong>An open-source, self-hosted AI video production workspace</strong>
  <br>
  Turn novels, finished screenplays, or product assets into character-consistent, controllable, cost-trackable short videos that remain editable.
</p>

<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/lang-繁體中文-red?style=flat-square" alt="繁體中文"></a>
  <a href="README.en.md"><img src="https://img.shields.io/badge/lang-English-blue?style=flat-square" alt="English"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-2ea44f?style=flat-square" alt="License"></a>
</p>

<p align="center">
  <a href="#quick-start"><strong>Quick Start</strong></a>
  ·
  <a href="https://docs.arc-reel.com/en/guide/getting-started">Getting Started</a>
  ·
  <a href="https://docs.arc-reel.com/en/">Documentation</a>
</p>

<p align="center">
  <img src="docs/assets/screenshots/hero.webp" alt="ArcReelStudio Workspace" width="900">
</p>

> ArcReelStudio is a modified version of [ArcReel](https://github.com/ArcReel/ArcReel), maintained by HazelnutParadise. See "Differences from the original ArcReel" below for what changed, and "License" for the original project's license and attribution terms.

## Screenshots

<table>
  <tr>
    <td width="50%"><img src="docs/assets/screenshots/video-units.webp" alt="Video units"></td>
    <td width="50%"><img src="docs/assets/screenshots/props.webp" alt="Props library"></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/assets/screenshots/scenes.webp" alt="Scenes library"></td>
    <td width="50%"><img src="docs/assets/screenshots/ad-mode.webp" alt="Ad / product mode"></td>
  </tr>
</table>

## Showcase

<div align="center">
  <video src="https://github.com/user-attachments/assets/fcc4ceb2-64dd-44a0-a32c-e0c00b2f9796" width="100%" controls></video>
</div>

> 《入職地府後投訴鬼都是我老客戶》Episode 1

<div align="center">
  <video src="https://github.com/user-attachments/assets/d6bfe589-a5c0-4961-8bfe-b7b59be3bb8a" width="100%" controls></video>
</div>

> 《入職地府後投訴鬼都是我老客戶》Episode 2

<div align="center">
  <video src="https://github.com/user-attachments/assets/1e580769-80f7-4d14-b46d-68569b6e7e4c" width="100%" controls></video>
</div>

> 《入職地府後投訴鬼都是我老客戶》Episode 3

## What ArcReelStudio is

ArcReelStudio is an open-source, self-hosted workspace for AI drama and novel adaptation, narrated short videos, ads, and product shorts. It organizes content analysis, asset management, storyboards, media generation, cost tracking, and export into an inspectable and resumable production pipeline.

- **One production workflow**: turn novels, finished screenplays, or product assets into characters, scenes, props, storyboards, video clips, and final videos step by step.
- **Visual continuity with human control**: reuse reference assets across shots, review key stages, regenerate individual assets, and roll back to earlier versions.
- **Manageable models and costs**: configure text, image, video, and TTS capabilities in one place, then review estimated costs and actual usage.
- **Editable delivery**: render final videos directly or export Jianying drafts to refine subtitles, voice-over, pacing, and transitions. Exports target the mainland-China edition of Jianying; CapCut compatibility has not been verified.

## Differences from the original ArcReel

ArcReelStudio keeps the original production workflow. The main differences are multi-user collaboration, how accounts and subscriptions connect, and the deployment defaults.

| Area | Original ArcReel | ArcReelStudio |
|---|---|---|
| Accounts | A single sign-in account, credentials in `.env` | Accounts live in the database with admin and member roles. Admins can add or disable members, change roles, and reset passwords |
| Collaboration | One editor at a time; saving can overwrite someone else's changes | Several people type at once, like a shared document, with visible cursors and online members. Edits by the Agent or background tasks to the same unit are merged automatically |
| API keys | Each provider uses its default key | New **Settings › Connections** page. Store several connections per provider and pick one for each model setting |
| Subscriptions | The Agent can use a Claude subscription | Sign in to Claude, ChatGPT, and Grok subscriptions in the browser, several accounts each. Text and image generation can also run on subscription quota |
| Agent engine | Claude | Claude or OpenAI Codex. Codex runs on a ChatGPT subscription or an OpenAI API key |
| UI languages | Simplified Chinese, English, and others | Adds Traditional Chinese |
| Video encoding | CPU encoding | Final cuts can be encoded with NVENC on NVIDIA GPUs |
| Deployment defaults | Image `arcreel/arcreel`, timezone `Asia/Shanghai` | Image `ghcr.io/hazelnutparadise/arcreelstudio:main`, timezone `Asia/Taipei`, and documented setup for an existing PostgreSQL |

The Codex engine does not yet support rewriting from an earlier message, the Agent asking the user questions, the read-only review sub-agent, or automatic switching between subscription and API key. Every change and its date is recorded in this repository's commit history.

## From source to final video

```mermaid
flowchart LR
    A["Novel / Screenplay / Product Assets"] --> B["Content Analysis & Project Planning"]
    B --> C["Character / Scene / Prop Assets"]
    C --> D["Episode Plan & Structured Script"]
    D --> E["Storyboard Image / Grid Storyboard"]
    E --> F["Video Clips / Voice-over Tracks"]
    F --> G["Final Composition"]
    F --> H["Jianying Draft Export"]
```

Every stage can be orchestrated by the Agent, or reviewed, adjusted, and regenerated by the user in the workspace. See [Workflows and Modes](https://docs.arc-reel.com/en/guide/workflows) for guidance on choosing a mode.

## Quick Start

Install Docker and Docker Compose, then run:

```bash
git clone https://github.com/HazelnutParadise/ArcReelStudio.git
cd ArcReelStudio/deploy

cp .env.example .env
docker compose up -d
```

Open <http://localhost:1241>. The default username is `admin`. If `AUTH_PASSWORD` is empty, ArcReelStudio generates an initial password on first startup and saves it to `deploy/projects/runtime/initial-admin-password`. After signing in, change the password and add members under Settings › Accounts & members.

> Default Compose publishes port `1241` on all host interfaces. Do not expose ArcReelStudio directly to the public Internet; before enabling remote access, configure authentication and use HTTPS, a VPN, or a secure tunnel. See [Reverse Proxy and HTTPS](https://docs.arc-reel.com/en/ops/deployment#reverse-proxy-and-https).

After signing in, open **Settings**, configure the Agent and the text, image, video, and other generation capabilities, then create a project.

For the complete first-run workflow, see [Getting Started](https://docs.arc-reel.com/en/guide/getting-started). For production deployment, upgrades, backups, and reverse proxies, see [Deployment and Operations](https://docs.arc-reel.com/en/ops/deployment).

## Documentation

The links below point to the original project's documentation site, which does not cover the ArcReelStudio features listed above.

| Page | Purpose |
|---|---|
| [Documentation Home](https://docs.arc-reel.com/en/) | Entry points for users, operators, and developers |
| [Getting Started](https://docs.arc-reel.com/en/guide/getting-started) | From first deployment to the first generated video |
| [Workflows and Modes](https://docs.arc-reel.com/en/guide/workflows) | Novels, scripts, and creative ideas; three creation types and two generation modes |
| [Provider Configuration](https://docs.arc-reel.com/en/guide/providers) | Selection and configuration of Agent, text, image, video, and TTS providers |
| [Jianying Draft Export](https://docs.arc-reel.com/en/guide/jianying-export) | Continue editing generated output in Jianying |
| [FAQ](https://docs.arc-reel.com/en/guide/faq) | Deployment, cost, model, data, and licensing questions |
| [Deployment and Operations](https://docs.arc-reel.com/en/ops/deployment) | SQLite, PostgreSQL, upgrades, backups, and reverse proxies |
| [Migrate from SQLite to PostgreSQL](https://docs.arc-reel.com/en/ops/migrate-to-postgres) | Data migration, verification, and rollback |
| [Architecture](https://docs.arc-reel.com/en/dev/architecture) | Agent Runtime, task queue, provider abstraction, and data layer |
| [Contributing](https://docs.arc-reel.com/en/dev/contributing) | Local development, tests, conventions, and pull requests |

## Issues and contributing

Reproducible bugs and focused feature requests are welcome in [GitHub Issues](https://github.com/HazelnutParadise/ArcReelStudio/issues).

Contributions to code, documentation, tests, provider adapters, and reproducible bug reports are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before starting. After cloning the repository, install the pre-commit hooks:

```bash
uv run pre-commit install
```

## License

The original ArcReel is licensed under the [GNU Affero General Public License v3.0](LICENSE). Additional terms are available in [NOTICE](NOTICE). ArcReelStudio is a modified version of ArcReel. The modifications made by HazelnutParadise are also licensed under AGPLv3, and every change is recorded in this repository's commit history.

Under those terms, modified versions must preserve the original author attribution and a link to the original project, and must mark their changes:

Powered by ArcReel — <https://github.com/ArcReel/ArcReel>

Copyright © 2026 Pollo3470 and ArcReel contributors

ArcReelStudio modifications: Copyright © 2026 HazelnutParadise
