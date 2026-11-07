<h1 align="center">
  <br>
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/logo-animated-light.svg">
    <source media="(prefers-color-scheme: dark)" srcset="frontend/public/logo-animated.svg">
    <img src="docs/assets/logo-animated-light.svg" alt="ArcReel Logo" width="128">
  </picture>
  <br>
  ArcReel
  <br>
</h1>

<p align="center">
  <strong>開源、自架的 AI 影片製作工作台</strong>
  <br>
  把小說、完成的劇本或商品素材，做成角色一致、過程可控、費用可追蹤，而且還能繼續編輯的短影片。
</p>

<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/lang-繁體中文-red?style=flat-square" alt="繁體中文"></a>
  <a href="README.en.md"><img src="https://img.shields.io/badge/lang-English-blue?style=flat-square" alt="English"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL--3.0-2ea44f?style=flat-square" alt="License"></a>
</p>

<p align="center">
  <a href="#快速開始"><strong>快速開始</strong></a>
  ·
  <a href="https://docs.arc-reel.com/guide/getting-started">入門教學</a>
  ·
  <a href="https://docs.arc-reel.com/">完整文件</a>
</p>

<p align="center">
  <img src="docs/assets/screenshots/hero.webp" alt="ArcReel 工作台" width="900">
</p>

> 本專案是 [ArcReel](https://github.com/ArcReel/ArcReel) 的修改版本，由 HazelnutParadise 維護。原始專案的授權與署名規定見下方「授權條款」。

## 介面一覽

<table>
  <tr>
    <td width="50%"><img src="docs/assets/screenshots/video-units.webp" alt="影片單元"></td>
    <td width="50%"><img src="docs/assets/screenshots/props.webp" alt="道具庫"></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/assets/screenshots/scenes.webp" alt="場景庫"></td>
    <td width="50%"><img src="docs/assets/screenshots/ad-mode.webp" alt="廣告／帶貨模式"></td>
  </tr>
</table>

## 作品範例

<div align="center">
  <video src="https://github.com/user-attachments/assets/fcc4ceb2-64dd-44a0-a32c-e0c00b2f9796" width="100%" controls></video>
</div>

> 《入職地府後投訴鬼都是我老客戶》第 1 集

<div align="center">
  <video src="https://github.com/user-attachments/assets/d6bfe589-a5c0-4961-8bfe-b7b59be3bb8a" width="100%" controls></video>
</div>

> 《入職地府後投訴鬼都是我老客戶》第 2 集

<div align="center">
  <video src="https://github.com/user-attachments/assets/1e580769-80f7-4d14-b46d-68569b6e7e4c" width="100%" controls></video>
</div>

> 《入職地府後投訴鬼都是我老客戶》第 3 集

## ArcReel 是什麼

ArcReel 是開源、自架的影片製作工作台，適合做 AI 漫劇與小說改編、旁白解說短影片，以及廣告和帶貨短片。內容分析、素材管理、分鏡、媒體生成、費用追蹤和匯出，都串在同一條產線上，每一步都能審核，中斷後也能接著做。

- **同一條產線**：小說、完成的劇本或商品素材，都能一步步變成角色、場景、道具、分鏡、影片片段和完成的影片。
- **畫面一致，人工把關**：角色、場景等參考圖可以跨分鏡重複使用。關鍵階段可以先確認再往下走，單一素材可以重做，也能退回舊版本。
- **模型與費用集中管理**：文字、圖像、影片和 TTS（文字轉語音）能力在同一處設定，生成前後都能查看預估費用和實際用量。
- **交付後可繼續編輯**：可以直接合成影片，也可以匯出剪映草稿，繼續調整字幕、配音、節奏和轉場。匯出格式以中國大陸版剪映為準，尚未驗證是否相容 CapCut。

## 從素材到完成影片

```mermaid
flowchart LR
    A["小說 / 完成的劇本 / 商品素材"] --> B["內容分析與專案規劃"]
    B --> C["角色 / 場景 / 道具素材"]
    C --> D["分集與結構化劇本"]
    D --> E["分鏡圖 / 多格分鏡"]
    E --> F["影片片段 / 旁白音軌"]
    F --> G["合成完成影片"]
    F --> H["匯出剪映草稿"]
```

每個階段都可以交給 Agent（AI 助理）自動安排，也可以由使用者在工作台裡審核、調整或重新生成。怎麼選模式，請看 [創作流程與模式](https://docs.arc-reel.com/guide/workflows)。

## 快速開始

先安裝 Docker 和 Docker Compose，再執行：

```bash
git clone https://github.com/HazelnutParadise/ArcReelStudio.git
cd ArcReelStudio/deploy

cp .env.example .env
docker compose up -d
```

用瀏覽器開啟 <http://localhost:1241>。預設使用者名稱是 `admin`。`AUTH_PASSWORD` 留空時，第一次啟動會產生一組初始密碼，存在 `deploy/projects/runtime/initial-admin-password`。登入後可以在 **設定 › 帳號與成員** 修改密碼、新增成員。

> 預設的 Compose 設定會把 `1241` 連接埠開放給主機上所有網路介面。請不要把服務直接放到公開網路上。要從遠端連線，請先設定登入驗證，並透過 HTTPS、VPN 或安全通道存取，詳見 [反向代理與 HTTPS](https://docs.arc-reel.com/ops/deployment#reverse-proxy-and-https)。

登入後進入 **設定** 頁面，設定 ArcReel Agent 以及文字、圖像、影片等生成能力，接著建立專案就能開始製作。

第一次使用的完整流程見 [完整入門教學](https://docs.arc-reel.com/guide/getting-started)。正式部署、升級、備份和反向代理見 [部署與維運](https://docs.arc-reel.com/ops/deployment)。

## 文件

以下連結指向原始專案的文件網站，內容為簡體中文。

| 頁面 | 內容 |
|---|---|
| [文件首頁](https://docs.arc-reel.com/) | 依使用者、維運人員和開發者分流的入口 |
| [完整入門教學](https://docs.arc-reel.com/guide/getting-started) | 從第一次部署到生成第一支影片 |
| [創作流程與模式](https://docs.arc-reel.com/guide/workflows) | 小說、劇本與創作構想三種創作類型，以及兩種生成模式 |
| [供應商與模型設定](https://docs.arc-reel.com/guide/providers) | Agent、文字、圖像、影片、TTS 供應商的選擇和設定 |
| [剪映草稿匯出](https://docs.arc-reel.com/guide/jianying-export) | 把 ArcReel 的生成結果交給剪映繼續編輯 |
| [常見問題](https://docs.arc-reel.com/guide/faq) | 部署、費用、模型、資料和授權問題 |
| [部署與維運](https://docs.arc-reel.com/ops/deployment) | SQLite、PostgreSQL、升級、備份和反向代理 |
| [從 SQLite 遷移到 PostgreSQL](https://docs.arc-reel.com/ops/migrate-to-postgres) | 資料遷移、驗證與還原流程 |
| [架構說明](https://docs.arc-reel.com/dev/architecture) | Agent Runtime、任務佇列、供應商抽象層和資料層 |
| [貢獻指南](https://docs.arc-reel.com/dev/contributing) | 本機開發、測試、程式碼規範和 PR 流程 |

## 回報問題與貢獻

遇到可以重現的 Bug，或有明確的功能需求，請到 [GitHub Issues](https://github.com/HazelnutParadise/ArcReelStudio/issues) 提出。

也歡迎貢獻程式碼、文件、測試、供應商串接，或協助重現問題。開始開發前請先閱讀 [CONTRIBUTING.md](CONTRIBUTING.md)。複製專案到本機後，建議馬上安裝專案的 pre-commit hook：

```bash
uv run pre-commit install
```

## 授權條款

ArcReel 採用 [GNU Affero General Public License v3.0](LICENSE) 授權，附加條款見 [NOTICE](NOTICE)。本專案 ArcReelStudio 是 ArcReel 的修改版本，HazelnutParadise 所做的修改同樣採用 AGPLv3 授權，所有修改記錄在本 repo 的提交歷史中。

依照附加條款，修改版本必須保留原作者署名與原始專案連結，並標明所做的修改：

Powered by ArcReel — <https://github.com/ArcReel/ArcReel>

Copyright © 2026 Pollo3470 and ArcReel contributors

ArcReelStudio 修改部分：Copyright © 2026 HazelnutParadise
