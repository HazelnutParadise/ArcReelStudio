/**
 * 输入框里第 `index` 个字符前的光标位置（相对输入框左上角，已扣掉卷动）。
 *
 * 做法：建一个与输入框排版一致的镜像 div，把光标前的文字放进去，量末尾标记的位置。与 textarea-caret-position
 * 的做法相同，适用于 textarea 与单行 input。
 */
const MIRRORED_PROPERTIES = [
  "direction",
  "boxSizing",
  "width",
  "height",
  "overflowX",
  "overflowY",
  "borderTopWidth",
  "borderRightWidth",
  "borderBottomWidth",
  "borderLeftWidth",
  "borderStyle",
  "paddingTop",
  "paddingRight",
  "paddingBottom",
  "paddingLeft",
  "fontStyle",
  "fontVariant",
  "fontWeight",
  "fontStretch",
  "fontSize",
  "fontSizeAdjust",
  "lineHeight",
  "fontFamily",
  "textAlign",
  "textTransform",
  "textIndent",
  "textDecoration",
  "letterSpacing",
  "wordSpacing",
  "tabSize",
] as const;

export interface CaretPoint {
  top: number;
  left: number;
  height: number;
}

export function caretCoordinates(el: HTMLInputElement | HTMLTextAreaElement, index: number): CaretPoint {
  const isInput = el instanceof HTMLInputElement;
  const style = getComputedStyle(el);
  const mirror = document.createElement("div");
  const mirrorStyle = mirror.style;
  mirrorStyle.position = "absolute";
  mirrorStyle.visibility = "hidden";
  mirrorStyle.top = "0";
  mirrorStyle.left = "-9999px";
  mirrorStyle.whiteSpace = isInput ? "pre" : "pre-wrap";
  mirrorStyle.overflowWrap = isInput ? "normal" : "break-word";
  for (const prop of MIRRORED_PROPERTIES) {
    mirrorStyle[prop] = style[prop];
  }
  mirrorStyle.overflow = "hidden";
  const clamped = Math.max(0, Math.min(index, el.value.length));
  mirror.textContent = el.value.slice(0, clamped);
  const marker = document.createElement("span");
  // 空标记量不到高度：放入光标后的文字（至少一个字符）
  marker.textContent = el.value.slice(clamped) || ".";
  mirror.appendChild(marker);
  document.body.appendChild(mirror);
  const lineHeight = Number.parseFloat(style.lineHeight) || Number.parseFloat(style.fontSize) * 1.4;
  const point = {
    top: marker.offsetTop + Number.parseFloat(style.borderTopWidth) - el.scrollTop,
    left: marker.offsetLeft + Number.parseFloat(style.borderLeftWidth) - el.scrollLeft,
    height: lineHeight,
  };
  mirror.remove();
  return point;
}
