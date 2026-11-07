import { describe, expect, it } from "vite-plus/test";

import { withLocalEdits } from "./useLiveEditUnit";

describe("withLocalEdits", () => {
  it("applies only the fields changed locally and keeps everyone else's current content", () => {
    const current = { synopsis: "别人刚改的梗概", genre: "悬疑", theme: "生存" };
    const base = { synopsis: "旧梗概", genre: "科幻", theme: "生存" };
    const mine = { synopsis: "旧梗概", genre: "悬疑科幻", theme: "生存" };

    expect(withLocalEdits(current, base, mine)).toEqual({
      synopsis: "别人刚改的梗概",
      genre: "悬疑科幻",
      theme: "生存",
    });
  });

  it("returns the current content unchanged when nothing was edited locally", () => {
    const current = { synopsis: "现在的内容" };
    expect(withLocalEdits(current, { synopsis: "起点" }, { synopsis: "起点" })).toEqual(current);
  });
});
