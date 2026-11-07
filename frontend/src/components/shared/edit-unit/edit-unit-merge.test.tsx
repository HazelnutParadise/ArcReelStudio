import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { LeaveGuardProvider } from "./LeaveGuard";
import { mergeExternalFields, useEditUnit } from "./useEditUnit";

interface Fields {
  image: string;
  video: string;
}

function FieldsEditor({ source, save }: { source: Fields; save: (value: Fields, saved: Fields) => Promise<void> }) {
  const unit = useEditUnit({ source, save, mergeExternalFields: true });
  return (
    <>
      <label>
        画面
        <input value={unit.value.image} onChange={(e) => unit.setValue((v) => ({ ...v, image: e.target.value }))} />
      </label>
      <label>
        运镜
        <input value={unit.value.video} onChange={(e) => unit.setValue((v) => ({ ...v, video: e.target.value }))} />
      </label>
      {unit.externallyUpdated ? <p>内容已被他人更新</p> : null}
      <button type="button" onClick={() => void unit.save()}>
        保存
      </button>
    </>
  );
}

function renderEditor(source: Fields, save = vi.fn(async () => {})) {
  const view = render(
    <LeaveGuardProvider>
      <FieldsEditor source={source} save={save} />
    </LeaveGuardProvider>,
  );
  const rerender = (next: Fields) =>
    view.rerender(
      <LeaveGuardProvider>
        <FieldsEditor source={next} save={save} />
      </LeaveGuardProvider>,
    );
  return { rerender, save };
}

const ORIGINAL: Fields = { image: "原画面", video: "原运镜" };

describe("按字段合并外部更新", () => {
  it("别人改了我没动的字段：直接采用，不标出外部更新，保存时只提交我的字段", async () => {
    const user = userEvent.setup();
    const { rerender, save } = renderEditor(ORIGINAL);

    await user.clear(screen.getByRole("textbox", { name: "画面" }));
    await user.type(screen.getByRole("textbox", { name: "画面" }), "我的画面");
    rerender({ image: "原画面", video: "别人的运镜" });

    expect(screen.getByRole("textbox", { name: "画面" })).toHaveValue("我的画面");
    expect(screen.getByRole("textbox", { name: "运镜" })).toHaveValue("别人的运镜");
    expect(screen.queryByText("内容已被他人更新")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "保存" }));
    expect(save).toHaveBeenCalledWith(
      { image: "我的画面", video: "别人的运镜" },
      { image: "原画面", video: "别人的运镜" },
    );
  });

  it("双方改了同一个字段：保留我的修改并标出外部更新", async () => {
    const user = userEvent.setup();
    const { rerender } = renderEditor(ORIGINAL);

    await user.clear(screen.getByRole("textbox", { name: "画面" }));
    await user.type(screen.getByRole("textbox", { name: "画面" }), "我的画面");
    rerender({ image: "别人的画面", video: "原运镜" });

    expect(screen.getByRole("textbox", { name: "画面" })).toHaveValue("我的画面");
    expect(screen.getByText("内容已被他人更新")).toBeInTheDocument();
  });

  it("冲突标记在之后不相干的更新到来时仍保留", async () => {
    const user = userEvent.setup();
    const { rerender } = renderEditor(ORIGINAL);

    await user.type(screen.getByRole("textbox", { name: "画面" }), "！");
    rerender({ image: "别人的画面", video: "原运镜" });
    rerender({ image: "别人的画面", video: "别人的运镜" });

    expect(screen.getByText("内容已被他人更新")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "运镜" })).toHaveValue("别人的运镜");
  });
});

describe("mergeExternalFields", () => {
  it("双方改成相同的值不算冲突", () => {
    expect(mergeExternalFields({ a: 1 }, { a: 2 }, { a: 2 })).toEqual({ value: { a: 2 }, conflict: false });
  });

  it("新增或移除的字段同样按三方规则处理", () => {
    expect(mergeExternalFields<Record<string, number>>({ a: 1 }, { a: 1, b: 2 }, { c: 3 })).toEqual({
      value: { b: 2, c: 3 },
      conflict: false,
    });
  });

  it("不是对象时整份保留我的修改，两边不同即冲突", () => {
    expect(mergeExternalFields("原", "我的", "别人的")).toEqual({ value: "我的", conflict: true });
  });
});
