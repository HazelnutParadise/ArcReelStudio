import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import type { RemoteEdit } from "@/collab/collab-client";
import { useAppStore } from "@/stores/app-store";

/**
 * 影响已有产出的设置被其他成员改了：不论停在哪个分页都推一条提示，说明是谁改的、本机已同步。
 * 进入页面时已有的修改记录不提示。
 */
export function useImpactfulSettingNotice(edits: Readonly<Record<string, RemoteEdit>> | null, isAd: boolean): void {
  const { t } = useTranslation("dashboard");
  const seen = useRef<WeakSet<RemoteEdit> | null>(null);
  useEffect(() => {
    if (!edits) return;
    const fields: Array<[string, string]> = [
      ["aspect_ratio", t("aspect_ratio")],
      isAd
        ? ["target_duration", t("target_duration_label")]
        : ["episode_target_duration", t("episode_target_duration_label")],
    ];
    const first = seen.current === null;
    const known = (seen.current ??= new WeakSet());
    for (const [path, setting] of fields) {
      const edit = edits[path];
      if (!edit || known.has(edit)) continue;
      known.add(edit);
      if (!first)
        useAppStore.getState().pushToast(t("collab_setting_changed_notice", { name: edit.name, setting }), "info");
    }
  }, [edits, isAd, t]);
}
