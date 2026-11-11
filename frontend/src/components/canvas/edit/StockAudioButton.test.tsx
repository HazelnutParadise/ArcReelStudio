import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";

import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import type { StockItem, StockSource } from "@/types/stock";

import { StockAudioButton } from "./StockAudioButton";

const RAIN: StockItem = {
  source: "openverse",
  id: "ov-1",
  kind: "sfx",
  title: "Rain on a roof",
  creator: "someone",
  license: "cc0",
  license_url: "https://creativecommons.org/publicdomain/zero/1.0/",
  page_url: "https://example.org/ov-1",
  preview_url: "https://cdn.example.org/ov-1.mp3",
  duration_seconds: 2.4,
  width: null,
  height: null,
};

function source(overrides: Partial<StockSource>): StockSource {
  return {
    id: "openverse",
    display_name: "Openverse",
    kinds: ["music", "sfx", "image"],
    key_scope: "none",
    key_url: null,
    available: true,
    key_masked: null,
    can_set_key: false,
    ...overrides,
  };
}

const FREESOUND = source({
  id: "freesound",
  display_name: "Freesound",
  kinds: ["sfx"],
  key_scope: "member",
  key_url: "https://freesound.org/apiv2/apply",
  available: false,
  can_set_key: true,
});

beforeEach(() => {
  useAppStore.setState({ toast: null });
  vi.spyOn(API, "listStockSources").mockResolvedValue({ sources: [source({}), FREESOUND] });
});

async function openAndSearch(kind: "bgm" | "sfx", buttonName: string) {
  render(<StockAudioButton projectName="demo" kind={kind} />);
  await userEvent.click(screen.getByRole("button", { name: buttonName }));
  await userEvent.type(screen.getByLabelText("搜索词"), "rain");
  await userEvent.click(screen.getByRole("button", { name: "搜索" }));
}

describe("StockAudioButton", () => {
  it("searches the stock library and imports the chosen sound effect into the project", async () => {
    const search = vi.spyOn(API, "searchStock").mockResolvedValue({
      items: [RAIN],
      sources: [
        { source: "openverse", status: "ok" },
        { source: "freesound", status: "key_missing" },
      ],
    });
    const importAudio = vi.spyOn(API, "importStockAudio").mockResolvedValue({
      success: true,
      sfx: {
        id: "sfx-0009",
        name: "Rain on a roof",
        duration: 2.4,
        gain: 1,
        path: "sfx/sfx-0009.mp3",
        url: "/api/v1/files/demo/sfx/sfx-0009.mp3",
        source: "library",
        license: "cc0",
        source_url: "https://example.org/ov-1",
      },
    });
    await openAndSearch("sfx", "从素材库挑音效");

    const results = await screen.findByRole("list", { name: "搜索结果" });
    expect(search).toHaveBeenCalledWith("sfx", "rain");
    const row = within(results).getByRole("listitem");
    expect(within(row).getByText("CC0")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: /Openverse/ })).toHaveAttribute("href", "https://example.org/ov-1");
    expect(within(row).getByLabelText("试听「Rain on a roof」")).toHaveAttribute("src", RAIN.preview_url);

    await userEvent.click(within(row).getByRole("button", { name: "使用" }));

    await waitFor(() => expect(importAudio).toHaveBeenCalledWith("demo", RAIN, "sfx"));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(useAppStore.getState().toast?.text).toContain("Rain on a roof");
  });

  it("imports music into the BGM library", async () => {
    vi.spyOn(API, "searchStock").mockResolvedValue({
      items: [{ ...RAIN, kind: "music" }],
      sources: [{ source: "openverse", status: "ok" }],
    });
    const importAudio = vi.spyOn(API, "importStockAudio").mockResolvedValue({ success: true });
    await openAndSearch("bgm", "从素材库挑音乐");

    await userEvent.click(await screen.findByRole("button", { name: "使用" }));

    await waitFor(() => expect(importAudio).toHaveBeenCalledWith("demo", { ...RAIN, kind: "music" }, "music"));
  });

  it("lets a member add their own key for a source that needs one", async () => {
    const setKey = vi
      .spyOn(API, "setStockSourceKey")
      .mockResolvedValue({ sources: [source({}), { ...FREESOUND, available: true, key_masked: "ab…yz" }] });
    render(<StockAudioButton projectName="demo" kind="sfx" />);
    await userEvent.click(screen.getByRole("button", { name: "从素材库挑音效" }));

    const needsKey = await screen.findByRole("list", { name: "需要密钥的来源" });
    await userEvent.type(within(needsKey).getByLabelText("Freesound 密钥（只给你自己用）"), "my-token");
    await userEvent.click(within(needsKey).getByRole("button", { name: "保存" }));

    await waitFor(() => expect(setKey).toHaveBeenCalledWith("freesound", "my-token"));
    expect(await screen.findByText("Freesound 密钥已设置（ab…yz）")).toBeInTheDocument();
    expect(screen.queryByLabelText("Freesound 密钥（只给你自己用）")).not.toBeInTheDocument();
  });

  it("lets a member remove their key and says so when a source rejects it", async () => {
    vi.spyOn(API, "listStockSources").mockResolvedValue({
      sources: [source({}), { ...FREESOUND, available: true, key_masked: "ab…yz" }],
    });
    vi.spyOn(API, "searchStock").mockResolvedValue({
      items: [],
      sources: [
        { source: "openverse", status: "ok" },
        { source: "freesound", status: "key_rejected" },
      ],
    });
    const removeKey = vi.spyOn(API, "deleteStockSourceKey").mockResolvedValue({ sources: [source({}), FREESOUND] });
    await openAndSearch("sfx", "从素材库挑音效");

    expect(await screen.findByRole("alert")).toHaveTextContent("这些来源拒绝了密钥：Freesound");
    await userEvent.click(screen.getByRole("button", { name: "移除 Freesound 密钥" }));

    await waitFor(() => expect(removeKey).toHaveBeenCalledWith("freesound"));
    expect(await screen.findByLabelText("Freesound 密钥（只给你自己用）")).toBeInTheDocument();
  });

  it("tells a member to ask an admin when the key is shared by the workspace", async () => {
    vi.spyOn(API, "listStockSources").mockResolvedValue({
      sources: [
        source({
          id: "pixabay",
          display_name: "Pixabay",
          kinds: ["sfx"],
          key_scope: "workspace",
          available: false,
          can_set_key: false,
        }),
      ],
    });
    render(<StockAudioButton projectName="demo" kind="sfx" />);
    await userEvent.click(screen.getByRole("button", { name: "从素材库挑音效" }));

    expect(await screen.findByText("Pixabay 还没有设置密钥，请管理员在这里填入后就能使用。")).toBeInTheDocument();
  });

  it("keeps the dialog open and reports why an item could not be used", async () => {
    vi.spyOn(API, "searchStock").mockResolvedValue({ items: [RAIN], sources: [{ source: "openverse", status: "ok" }] });
    vi.spyOn(API, "importStockAudio").mockRejectedValue(new Error("素材档案超过 100 MB"));
    await openAndSearch("sfx", "从素材库挑音效");

    await userEvent.click(await screen.findByRole("button", { name: "使用" }));

    await waitFor(() => expect(useAppStore.getState().toast?.text).toContain("素材档案超过 100 MB"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("says so when nothing is found and names the sources that failed", async () => {
    vi.spyOn(API, "searchStock").mockResolvedValue({ items: [], sources: [{ source: "openverse", status: "failed" }] });
    await openAndSearch("sfx", "从素材库挑音效");

    expect(await screen.findByText(/没有找到素材/)).toBeInTheDocument();
    expect(screen.getByText("这些来源这次没有返回结果：Openverse")).toBeInTheDocument();
  });
});
