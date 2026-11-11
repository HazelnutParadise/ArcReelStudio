# ArcReelStudio

> 中文说明见 [GitHub 仓库](https://github.com/HazelnutParadise/ArcReelStudio)。ArcReelStudio 是 [ArcReel](https://github.com/ArcReel/ArcReel) 的修改版本。

An open-source, self-hosted AI video production workspace. Turn novels, finished screenplays, or product assets into character-consistent, controllable, cost-trackable short videos that remain editable.

- **Source**: https://github.com/HazelnutParadise/ArcReelStudio
- **Documentation**: https://github.com/HazelnutParadise/ArcReelStudio/blob/main/website/i18n/en/docusaurus-plugin-content-docs/current/index.mdx
- **Based on**: [ArcReel](https://github.com/ArcReel/ArcReel)
- **License**: AGPL-3.0

## Supported tags

| Tag | Meaning |
|---|---|
| `latest` | The most recent stable release |
| `X.Y.Z` | An exact release |
| `X.Y` | The latest patch of that minor line |
| `X` | The latest release of that major line |

Images are published for `linux/amd64` and `linux/arm64`, with SBOM and provenance attestations attached.

## Quick start

Compose is the supported way to run ArcReel — the application needs a database, a data volume, and specific kernel capabilities for its sandbox:

```bash
git clone https://github.com/HazelnutParadise/ArcReelStudio.git
cd ArcReelStudio/deploy

cp .env.example .env
docker compose up -d
```

Open <http://localhost:1241>. The default username is `admin`. If `AUTH_PASSWORD` is empty, ArcReel generates an initial password on first startup and saves it to `deploy/projects/runtime/initial-admin-password`. After signing in, change the password and add members under Settings › Accounts & members.

> Default Compose publishes port `1241` on all host interfaces. Do not expose ArcReel directly to the public Internet; before enabling remote access, configure authentication and use HTTPS, a VPN, or a secure tunnel.

For the complete first-run walkthrough see [Getting Started](https://github.com/HazelnutParadise/ArcReelStudio/blob/main/website/i18n/en/docusaurus-plugin-content-docs/current/guide/getting-started.md); for production deployment, upgrades, backups, and reverse proxies see [Deployment and Operations](https://github.com/HazelnutParadise/ArcReelStudio/blob/main/website/i18n/en/docusaurus-plugin-content-docs/current/ops/deployment.md).

## What you get

- **One production workflow**: turn novels, finished screenplays, or product assets into characters, scenes, props, storyboards, video clips, and final videos step by step.
- **Visual continuity with human control**: reuse reference assets across shots, review key stages, regenerate individual assets, and roll back to earlier versions.
- **Manageable models and costs**: configure text, image, video, and TTS capabilities in one place, then review estimated costs and actual usage.
- **Editable delivery**: render final videos directly or export Jianying drafts to refine subtitles, voice-over, pacing, and transitions.

## Support

Reproducible bugs and focused feature requests are welcome in [GitHub Issues](https://github.com/HazelnutParadise/ArcReelStudio/issues).
