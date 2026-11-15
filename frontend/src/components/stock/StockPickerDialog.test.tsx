import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";

import { API } from "@/api";
import type { StockItem, StockSearchResult, StockSource } from "@/types/stock";

import { StockPickerDialog } from "./StockPickerDialog";

function source(overrides: Partial<StockSource>): StockSource {
  return {
    id: "openverse",
    display_name: "Openverse",
    kinds: ["music", "image"],
    key_scope: "none",
    key_url: null,
    available: true,
    key_masked: null,
    can_set_key: false,
    ...overrides,
  };
}

const PIXABAY = source({
  id: "pixabay",
  display_name: "Pixabay",
  kinds: ["image"],
  key_scope: "workspace",
  available: true,
  key_masked: "ab…yz",
});
const PEXELS = source({
  id: "pexels",
  display_name: "Pexels",
  kinds: ["image"],
  key_scope: "workspace",
  available: false,
});

function image(sourceId: string, id: string): StockItem {
  return {
    source: sourceId,
    id,
    kind: "image",
    title: `${sourceId} ${id}`,
    creator: null,
    license: "cc0",
    license_url: "https://creativecommons.org/publicdomain/zero/1.0/",
    page_url: `https://example.org/${id}`,
    preview_url: null,
    duration_seconds: null,
    width: 100,
    height: 100,
  };
}

/** 每个来源一个可以手动放行的请求，以便在等待中检查进度与取消。 */
function deferredSearch() {
  const pending = new Map<string, { resolve: (result: StockSearchResult) => void; signal?: AbortSignal }>();
  const spy = vi.spyOn(API, "searchStock").mockImplementation(
    (_kind, _query, _page, options) =>
      new Promise((resolve) => {
        pending.set(options?.source ?? "", { resolve, signal: options?.signal });
      }),
  );
  const answer = (sourceId: string, items: StockItem[], status: "ok" | "failed" = "ok") =>
    pending.get(sourceId)!.resolve({ items, sources: [{ source: sourceId, status }] });
  return { spy, pending, answer };
}

async function search(text = "key") {
  await userEvent.type(screen.getByLabelText("搜索词"), text);
  await userEvent.click(screen.getByRole("button", { name: "搜索" }));
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(API, "listStockSources").mockResolvedValue({ sources: [source({}), PIXABAY, PEXELS] });
});

describe("StockPickerDialog", () => {
  it("says before searching which sources work without a key and which need one", async () => {
    render(<StockPickerDialog kind="image" onPick={vi.fn()} onClose={vi.fn()} />);

    expect(await screen.findByText("不用密钥就能搜索：Openverse、Pixabay")).toBeInTheDocument();
    expect(screen.getByText("要先设置密钥才会一起搜索：Pexels（设置方式见下方）")).toBeInTheDocument();
    // 不能设置的成员被告知找管理员
    expect(screen.getByText("Pexels 还没有设置密钥，请管理员在这里填入后就能使用。")).toBeInTheDocument();
  });

  it("says so when no source of this kind works without a key", async () => {
    vi.mocked(API.listStockSources).mockResolvedValue({ sources: [PEXELS] });
    const searchSpy = vi.spyOn(API, "searchStock");
    render(<StockPickerDialog kind="image" onPick={vi.fn()} onClose={vi.fn()} />);

    expect(await screen.findByText("这类素材的来源都要先设置密钥，设置好之后才能搜索。")).toBeInTheDocument();
    await search();
    expect(searchSpy).not.toHaveBeenCalled();
  });

  it("asks each usable source on its own and shows progress per source", async () => {
    const { spy, answer } = deferredSearch();
    render(<StockPickerDialog kind="image" onPick={vi.fn()} onClose={vi.fn()} />);
    await screen.findByText(/不用密钥就能搜索/);
    await search();

    expect(spy.mock.calls.map((call) => call[3]?.source)).toEqual(["openverse", "pixabay"]);
    const progress = screen.getByRole("list", { name: "各来源的搜索进度" });
    expect(within(progress).getByText("Openverse：搜索中…")).toBeInTheDocument();
    expect(within(progress).getByText("Pixabay：搜索中…")).toBeInTheDocument();

    answer("pixabay", [image("pixabay", "p1"), image("pixabay", "p2")]);
    expect(await within(progress).findByText("Pixabay：找到 2 条")).toBeInTheDocument();
    expect(within(progress).getByText("Openverse：搜索中…")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "搜索结果" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "取消搜索" })).toBeInTheDocument();

    answer("openverse", []);
    expect(await within(progress).findByText("Openverse：没有找到符合的素材")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "搜索" })).toBeInTheDocument();
    expect(screen.queryByText(/没有找到素材。/)).not.toBeInTheDocument();
  });

  it("lets the user cancel a slow search", async () => {
    const { pending, answer } = deferredSearch();
    render(<StockPickerDialog kind="image" onPick={vi.fn()} onClose={vi.fn()} />);
    await screen.findByText(/不用密钥就能搜索/);
    await search();
    answer("pixabay", [image("pixabay", "p1")]);
    await screen.findByText("Pixabay：找到 1 条");

    await userEvent.click(screen.getByRole("button", { name: "取消搜索" }));

    expect(pending.get("openverse")!.signal?.aborted).toBe(true);
    expect(screen.getByText("Openverse：已取消")).toBeInTheDocument();
    expect(screen.getByText("Pixabay：找到 1 条")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "搜索" })).toBeInTheDocument();
    // 取消之后才到的回应不再改动画面
    answer("openverse", [image("openverse", "late")]);
    await waitFor(() => expect(screen.queryByText("openverse late")).not.toBeInTheDocument());
  });

  it("says plainly when nothing is found anywhere and suggests English keywords", async () => {
    const { answer } = deferredSearch();
    render(<StockPickerDialog kind="image" onPick={vi.fn()} onClose={vi.fn()} />);
    await screen.findByText(/不用密钥就能搜索/);
    await search("钥匙");
    answer("openverse", []);
    answer("pixabay", []);

    expect(await screen.findByText("没有找到素材。换一个搜索词试试，英文的结果通常最多。")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "搜索结果" })).not.toBeInTheDocument();
  });
});
