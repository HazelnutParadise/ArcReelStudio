/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseSync } from "oxc-parser";
import { describe, expect, it } from "vitest";
import { ENQUEUE_METHODS } from "../lint/arcreel-plugin";

type AstNode = { type: string; start: number; method?: boolean; key?: { type: string; name?: string; start: number; end: number } };

function walk(value: unknown, visit: (node: AstNode) => void): void {
  if (Array.isArray(value)) {
    for (const item of value) walk(item, visit);
    return;
  }
  if (value === null || typeof value !== "object") return;
  if (typeof (value as { type?: unknown }).type === "string") visit(value as AstNode);
  for (const child of Object.values(value)) walk(child, visit);
}

// 入队类方法以 api.ts 上的 JSDoc `@enqueue` 标记识别（返回类型不统一，无法按类型推断）。
// 该集合必须与 lint/arcreel-plugin.ts 的 ENQUEUE_METHODS 完全相同，否则漏登记的方法可被组件直调。
function taggedEnqueueMethods(source: string): string[] {
  const { program, comments, errors } = parseSync("api.ts", source);
  if (errors.length > 0) throw new Error(`api.ts 解析失败：${errors.map((e) => e.message).join("；")}`);
  // 与 TypeScript 的 JSDoc 归属一致：成员前方连续的空白与注释里，最后一段 /** */ 是它的 JSDoc，
  // 其中前面是空白的 @enqueue 都算标记。
  const commentByEnd = new Map(comments.map((c) => [c.end, c]));
  const jsdocOf = (start: number) => {
    let end = start;
    for (;;) {
      while (end > 0 && /\s/.test(source[end - 1])) end -= 1;
      const comment = commentByEnd.get(end);
      if (!comment) return undefined;
      if (comment.type === "Block" && comment.value.startsWith("*")) return comment.value;
      end = comment.start;
    }
  };
  const names: string[] = [];
  walk(program, (node) => {
    // 箭头函数属性（`static foo = async () => …`）也算方法定义，否则改写形态后会被静默漏掉
    const isMethod =
      node.type === "MethodDefinition" ||
      node.type === "PropertyDefinition" ||
      (node.type === "Property" && node.method === true);
    const doc = isMethod ? jsdocOf(node.start) : undefined;
    if (node.key && doc !== undefined && /(^|[\s*])@enqueue(?![\w-])/.test(doc)) {
      names.push(node.key.type === "Identifier" && node.key.name ? node.key.name : source.slice(node.key.start, node.key.end));
    }
  });
  return names.sort();
}

describe("入队类 API 方法标记", () => {
  it("带 @enqueue 标记的方法与 ENQUEUE_METHODS 完全一致", () => {
    const tagged = taggedEnqueueMethods(readFileSync(resolve(process.cwd(), "src/api.ts"), "utf8"));
    expect(tagged.length).toBeGreaterThan(0);
    expect(tagged).toEqual([...ENQUEUE_METHODS].sort());
  });

  // 期望值取自 TypeScript 6 的 ts.getJSDocTags 在同一份源码上的结果。
  it("JSDoc 标记的归属与 TypeScript 一致", () => {
    const source = [
      "class API {",
      "  /**",
      "   * 多行说明",
      "   * @enqueue",
      "   */",
      "  static async method() {}",
      "  /** @enqueue */",
      "  static arrow = async () => 1;",
      "  /** 写在行中的 @enqueue 同样是标记 */",
      "  static inline() {}",
      "  /** @enqueue */",
      "  // 中间隔着普通注释，JSDoc 仍归后面的成员",
      "  static separated() {}",
      "  /* @enqueue */",
      "  static plainBlock() {}",
      "  /** @enqueue */",
      "  /** 只有最后一段 JSDoc 算数 */",
      "  static twoDocs() {}",
      "  /** 其他 */ /** @enqueue */ static sameLine() {}",
      "  /** @enqueueLater */",
      "  static otherTag() {}",
      "}",
      "",
    ].join("\n");
    expect(taggedEnqueueMethods(source)).toEqual(["arrow", "inline", "method", "sameLine", "separated"]);
  });
});
