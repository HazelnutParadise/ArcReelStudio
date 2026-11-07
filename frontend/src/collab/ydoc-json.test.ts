import { describe, expect, it } from "vite-plus/test";
import * as Y from "yjs";

import { applyJson, textSplice, unitJson, unitRoot } from "./ydoc-json";

function docWith(value: Record<string, unknown>): Y.Doc {
  const doc = new Y.Doc();
  applyJson(doc, value as never);
  return doc;
}

function sync(from: Y.Doc, to: Y.Doc): void {
  Y.applyUpdate(to, Y.encodeStateAsUpdate(from, Y.encodeStateVector(to)));
}

describe("ydoc-json", () => {
  it("stores strings on objects as shared text and list items as plain values", () => {
    const doc = docWith({ synopsis: "雨夜", characters: ["Alice"], prompt: { scene: "街口" }, n: 3 });
    const root = unitRoot(doc);

    expect(root.get("synopsis")).toBeInstanceOf(Y.Text);
    expect((root.get("characters") as Y.Array<unknown>).toArray()).toEqual(["Alice"]);
    expect((root.get("prompt") as Y.Map<unknown>).get("scene")).toBeInstanceOf(Y.Text);
    expect(unitJson(doc)).toEqual({ synopsis: "雨夜", characters: ["Alice"], prompt: { scene: "街口" }, n: 3 });
  });

  it("merges two people typing in the same text", () => {
    const alice = docWith({ synopsis: "雨夜" });
    const bob = new Y.Doc();
    sync(alice, bob);

    applyJson(alice, { synopsis: "深夜，雨夜" });
    applyJson(bob, { synopsis: "雨夜的街口" });
    sync(alice, bob);
    sync(bob, alice);

    expect(unitJson(alice).synopsis).toBe("深夜，雨夜的街口");
    expect(unitJson(bob)).toEqual(unitJson(alice));
  });

  it("edits one list item without touching another person's edit on a different item", () => {
    const alice = docWith({ utterances: [{ text: "早安" }, { text: "晚安" }] });
    const bob = new Y.Doc();
    sync(alice, bob);

    applyJson(alice, { utterances: [{ text: "早安啊" }, { text: "晚安" }] });
    applyJson(bob, { utterances: [{ text: "早安" }, { text: "晚安呀" }] });
    sync(alice, bob);
    sync(bob, alice);

    expect(unitJson(alice).utterances).toEqual([{ text: "早安啊" }, { text: "晚安呀" }]);
  });

  it("produces no update when nothing changed", () => {
    const doc = docWith({ synopsis: "x" });
    const before = Y.encodeStateVector(doc);

    applyJson(doc, { synopsis: "x" });

    expect(Y.encodeStateVector(doc)).toEqual(before);
  });

  it("never splits a surrogate pair when computing the changed span", () => {
    // 「😀」与「😃」的高位代理相同，差异必须从整个字符开始
    expect(textSplice("a😀b", "a😃b")).toEqual({ start: 1, deleteCount: 2, insert: "😃" });
  });
});
