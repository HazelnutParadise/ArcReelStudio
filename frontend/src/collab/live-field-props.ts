import type { LiveEditing } from "@/components/shared/edit-unit/useEditUnit";

/** 协作中时绑到输入框上的属性（见 `LiveEditing.fieldProps`）；不在协作中时为空对象。 */
export function liveFieldProps(live: LiveEditing | null, path: string) {
  return live ? live.fieldProps(path) : {};
}
