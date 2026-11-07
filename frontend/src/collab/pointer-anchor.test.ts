import { afterEach, describe, expect, it } from "vite-plus/test";

import { pointerFromEvent, resolvePointer } from "./pointer-anchor";

function rectOf(element: Element, rect: { left: number; top: number; width: number; height: number }) {
  element.getBoundingClientRect = () => new DOMRect(rect.left, rect.top, rect.width, rect.height);
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("pointer anchors", () => {
  it("anchors to a collaboration field by name and maps back inside the same field", () => {
    document.body.innerHTML = '<main><div data-collab-frame="synopsis"><textarea></textarea></div></main>';
    const frame = document.querySelector("[data-collab-frame]")!;
    rectOf(frame, { left: 100, top: 50, width: 200, height: 100 });

    const pointer = pointerFromEvent({ target: frame.querySelector("textarea"), clientX: 150, clientY: 75 });
    expect(pointer).toEqual({ anchor: "field:synopsis", x: 0.25, y: 0.25 });

    // 对方窗口里同一个字段在别处，按比例落在对应位置
    rectOf(frame, { left: 0, top: 0, width: 400, height: 200 });
    expect(resolvePointer(pointer!)).toEqual({ left: 100, top: 50 });
  });

  it("anchors elsewhere to the element under the pointer by its path from body", () => {
    document.body.innerHTML = "<main><section></section><section><p>text</p></section></main>";
    const paragraph = document.querySelector("section:nth-of-type(2) p")!;
    rectOf(paragraph, { left: 10, top: 10, width: 100, height: 20 });

    const pointer = pointerFromEvent({ target: paragraph, clientX: 60, clientY: 20 });
    expect(pointer).toEqual({ anchor: "element:main:0/section:1/p:0", x: 0.5, y: 0.5 });
    expect(resolvePointer(pointer!)).toEqual({ left: 60, top: 20 });
  });

  it("does not draw a pointer whose anchor is missing or scrolled out of view", () => {
    expect(resolvePointer({ anchor: "field:missing", x: 0.5, y: 0.5 })).toBeNull();

    document.body.innerHTML = "<main><p>far below</p></main>";
    const paragraph = document.querySelector("p")!;
    rectOf(paragraph, { left: 0, top: window.innerHeight + 500, width: 100, height: 20 });
    expect(resolvePointer({ anchor: "element:main:0/p:0", x: 0.5, y: 0.5 })).toBeNull();
  });
});
