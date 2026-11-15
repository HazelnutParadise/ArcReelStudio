import { useEffect, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "cn";

import type { RemoteEdit } from "./collab-client";

/** 「某某刚改了这项」显示多久。 */
const RECENT_EDIT_MS = 8000;

/** 字段本身或字段里的某一项（如列表里的一行）最近一次被其他成员修改。 */
function latestEdit(edits: Readonly<Record<string, RemoteEdit>>, path: string): RemoteEdit | null {
  let latest: RemoteEdit | null = null;
  for (const [key, edit] of Object.entries(edits)) {
    if (key !== path && !key.startsWith(`${path}.`)) continue;
    if (!latest || edit.at > latest.at) latest = edit;
  }
  return latest;
}

/**
 * 其他成员刚改了这个字段时，在字段旁标出是谁改的，几秒后消失。
 * 只看本字段：页面上同时改了别的字段不会在这里提示。
 */
export function RecentEditNote({
  edits,
  path,
  className,
}: {
  edits: Readonly<Record<string, RemoteEdit>>;
  path: string;
  className?: string;
}) {
  const { t } = useTranslation("dashboard");
  const edit = latestEdit(edits, path);
  // 挂载之前就已过期的修改（切回这个分页时）不再提示
  const [mountedAt] = useState(() => Date.now());
  const [expired, setExpired] = useState<RemoteEdit | null>(null);
  useEffect(() => {
    if (!edit) return;
    const timer = setTimeout(() => setExpired(edit), Math.max(0, edit.at + RECENT_EDIT_MS - Date.now()));
    return () => clearTimeout(timer);
  }, [edit]);

  if (!edit || expired === edit || edit.at + RECENT_EDIT_MS <= mountedAt) return null;
  return (
    <span
      role="status"
      className={cn("inline-flex items-center gap-1 text-xs text-muted-foreground", className)}
      style={{ "--peer-color": edit.color } as CSSProperties}
    >
      <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-(--peer-color)" />
      {t("collab_recent_edit", { name: edit.name })}
    </span>
  );
}
