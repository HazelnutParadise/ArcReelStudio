import * as Y from "yjs";

/**
 * 编辑单元内容（JSON）与协作文档（Yjs）互转，结构规则与后端 `lib/collab/ydoc_json.py` 一致：
 * 对象 → `Y.Map`，清单 → `Y.Array`，对象上的字符串 → `Y.Text`（多人可同时在同一段文字里打字），
 * 清单里的字符串保持原子值，数字、布尔、null 原样存放。
 *
 * 套用新内容（{@link applyJson}）时只改有差异的部分：文字按公共前后缀算出变动区间，清单按公共前后缀找出
 * 变动段，长度相同的变动段逐项递归。Yjs 的文字位置与 JS 字符串一样按 UTF-16 码元计，无需换算。
 */

export const ROOT = "unit";

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type UnitJson = Record<string, JsonValue>;

export function unitRoot(doc: Y.Doc): Y.Map<unknown> {
  return doc.getMap(ROOT);
}

/** 文档当前内容的 JSON 形态。 */
export function unitJson(doc: Y.Doc): UnitJson {
  return unitRoot(doc).toJSON() as UnitJson;
}

/** 把文档改成 `value`，只改有差异的部分；内容相同时不产生更新。 */
export function applyJson(doc: Y.Doc, value: UnitJson, origin?: unknown): void {
  if (jsonEqual(unitJson(doc), value)) return;
  doc.transact(() => reconcileMap(unitRoot(doc), value), origin);
}

export function jsonEqual(a: unknown, b: unknown): boolean {
  return a === b || JSON.stringify(a) === JSON.stringify(b);
}

function toShared(value: JsonValue, inList: boolean): unknown {
  if (Array.isArray(value)) {
    const array = new Y.Array<unknown>();
    array.insert(
      0,
      value.map((item) => toShared(item, true)),
    );
    return array;
  }
  if (value !== null && typeof value === "object") {
    const map = new Y.Map<unknown>();
    for (const [key, item] of Object.entries(value)) map.set(key, toShared(item, false));
    return map;
  }
  if (typeof value === "string" && !inList) return new Y.Text(value);
  return value;
}

function plain(value: unknown): unknown {
  if (value instanceof Y.Text) return value.toString();
  if (value instanceof Y.Map || value instanceof Y.Array) return value.toJSON();
  return value;
}

function reconcileMap(target: Y.Map<unknown>, value: Record<string, JsonValue>): void {
  for (const key of Array.from(target.keys())) {
    if (!(key in value)) target.delete(key);
  }
  for (const [key, next] of Object.entries(value)) {
    if (!target.has(key)) {
      target.set(key, toShared(next, false));
      continue;
    }
    const current = target.get(key);
    if (!reconcileInPlace(current, next, false) && !jsonEqual(plain(current), next)) {
      target.set(key, toShared(next, false));
    }
  }
}

function reconcileInPlace(current: unknown, next: JsonValue, inList: boolean): boolean {
  if (current instanceof Y.Text && typeof next === "string" && !inList) {
    reconcileText(current, next);
    return true;
  }
  if (current instanceof Y.Map && next !== null && typeof next === "object" && !Array.isArray(next)) {
    reconcileMap(current, next);
    return true;
  }
  if (current instanceof Y.Array && Array.isArray(next)) {
    reconcileArray(current, next);
    return true;
  }
  return false;
}

/** 两段文字的差异区间：`[start, oldEnd)` 换成 `next.slice(start, newEnd)`。 */
export function textSplice(old: string, next: string): { start: number; deleteCount: number; insert: string } {
  let start = 0;
  const limit = Math.min(old.length, next.length);
  while (start < limit && old.charCodeAt(start) === next.charCodeAt(start)) start++;
  // 不在代理对中间切开
  if (start > 0 && isHighSurrogate(old.charCodeAt(start - 1))) start--;
  let oldEnd = old.length;
  let newEnd = next.length;
  while (oldEnd > start && newEnd > start && old.charCodeAt(oldEnd - 1) === next.charCodeAt(newEnd - 1)) {
    oldEnd--;
    newEnd--;
  }
  if (oldEnd < old.length && isLowSurrogate(old.charCodeAt(oldEnd))) {
    oldEnd++;
    newEnd++;
  }
  return { start, deleteCount: oldEnd - start, insert: next.slice(start, newEnd) };
}

function isHighSurrogate(code: number): boolean {
  return code >= 0xd800 && code <= 0xdbff;
}

function isLowSurrogate(code: number): boolean {
  return code >= 0xdc00 && code <= 0xdfff;
}

function reconcileText(text: Y.Text, next: string): void {
  const old = text.toString();
  if (old === next) return;
  const { start, deleteCount, insert } = textSplice(old, next);
  if (deleteCount > 0) text.delete(start, deleteCount);
  if (insert) text.insert(start, insert);
}

function reconcileArray(array: Y.Array<unknown>, next: JsonValue[]): void {
  const old = array.toArray().map(plain);
  if (jsonEqual(old, next)) return;
  let start = 0;
  const limit = Math.min(old.length, next.length);
  while (start < limit && jsonEqual(old[start], next[start])) start++;
  let oldEnd = old.length;
  let newEnd = next.length;
  while (oldEnd > start && newEnd > start && jsonEqual(old[oldEnd - 1], next[newEnd - 1])) {
    oldEnd--;
    newEnd--;
  }
  if (oldEnd - start === newEnd - start) {
    // 等长的变动段逐项递归：改的是某一项的内容（如某句台词），别人在其他项上的修改不受影响
    for (let index = start; index < oldEnd; index++) {
      if (!reconcileInPlace(array.get(index), next[index], true)) {
        array.delete(index, 1);
        array.insert(index, [toShared(next[index], true)]);
      }
    }
    return;
  }
  if (oldEnd > start) array.delete(start, oldEnd - start);
  if (newEnd > start)
    array.insert(
      start,
      next.slice(start, newEnd).map((item) => toShared(item, true)),
    );
}
