/**
 * 鼠标指针位置的锚点：「锚点元素 + 在它里面的比例」，两边窗口大小、卷动位置不同也对得上。
 */
import type { PointerPosition } from "./collab-client";

const FIELD_SELECTOR = "[data-collab-field],[data-collab-frame]";

export function pointerFromEvent(event: {
  target: EventTarget | null;
  clientX: number;
  clientY: number;
}): PointerPosition | null {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return null;
  const field = target.closest(FIELD_SELECTOR);
  if (field) {
    const name = field.getAttribute("data-collab-field") ?? field.getAttribute("data-collab-frame") ?? "";
    const rect = field.getBoundingClientRect();
    return {
      anchor: `field:${name}`,
      x: ratio(event.clientX - rect.left, rect.width),
      y: ratio(event.clientY - rect.top, rect.height),
    };
  }
  const rect = target.getBoundingClientRect();
  return {
    anchor: `element:${domPath(target)}`,
    x: ratio(event.clientX - rect.left, rect.width),
    y: ratio(event.clientY - rect.top, rect.height),
  };
}

export function resolvePointer(pointer: PointerPosition): { left: number; top: number } | null {
  const element = anchorElement(pointer.anchor);
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  const left = rect.left + pointer.x * rect.width;
  const top = rect.top + pointer.y * rect.height;
  // 锚点卷到画面外（自己这边看不到那一段）时不画
  if (top < 0 || left < 0 || top > window.innerHeight || left > window.innerWidth) return null;
  return { left, top };
}

function anchorElement(anchor: string): Element | null {
  if (anchor.startsWith("field:")) {
    const name = CSS.escape(anchor.slice("field:".length));
    return document.querySelector(`[data-collab-field="${name}"],[data-collab-frame="${name}"]`);
  }
  if (anchor.startsWith("element:")) return elementAtPath(anchor.slice("element:".length));
  return null;
}

function ratio(offset: number, size: number): number {
  if (size <= 0) return 0;
  return Math.min(1, Math.max(0, offset / size));
}

/** 从 body 往下的元素路径（标签名加同类序号），两边打开同一页面时指向同一个元素。 */
function domPath(element: Element): string {
  const parts: string[] = [];
  let node: Element | null = element;
  while (node && node !== document.body) {
    const parent: Element | null = node.parentElement;
    if (!parent) break;
    const tag = node.tagName;
    const index = Array.from(parent.children)
      .filter((child) => child.tagName === tag)
      .indexOf(node);
    parts.unshift(`${tag.toLowerCase()}:${index}`);
    node = parent;
  }
  return parts.join("/");
}

function elementAtPath(path: string): Element | null {
  if (path === "") return document.body;
  let node: Element | null = document.body;
  for (const part of path.split("/")) {
    const [tag, rawIndex] = part.split(":");
    const index = Number(rawIndex);
    if (!node || !tag || !Number.isInteger(index)) return null;
    const children: Element[] = Array.from(node.children).filter((child) => child.tagName.toLowerCase() === tag);
    node = children[index] ?? null;
  }
  return node;
}
