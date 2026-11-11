import { Library } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { API } from "@/api";
import { StockPickerDialog } from "@/components/stock/StockPickerDialog";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/app-store";
import type { StockItem } from "@/types/stock";

/**
 * BGM 轨与音效轨上的「从素材库挑」：在免版权素材库里找一首音乐或一个音效，存进项目的 BGM 库或音效库（docs/adr/0128）。
 * 按下按钮不触发轨道的跳转。
 */
export function StockAudioButton({ projectName, kind }: { projectName: string; kind: "bgm" | "sfx" }) {
  const { t } = useTranslation("dashboard");
  const [open, setOpen] = useState(false);
  const label = t(`edit_view_${kind}_stock`);

  const importItem = async (item: StockItem) => {
    const result = await API.importStockAudio(projectName, item, kind === "bgm" ? "music" : "sfx");
    const name = (kind === "bgm" ? result.bgm?.name : result.sfx?.name) ?? item.title;
    useAppStore.getState().pushToast(t(`edit_view_${kind}_uploaded`, { name }), "success");
  };

  return (
    <>
      <Button
        variant="ghost"
        size="icon-xs"
        aria-label={label}
        title={label}
        data-testid={`edit-${kind}-stock`}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={() => setOpen(true)}
      >
        <Library aria-hidden />
      </Button>
      {open && (
        <StockPickerDialog kind={kind === "bgm" ? "music" : "sfx"} onPick={importItem} onClose={() => setOpen(false)} />
      )}
    </>
  );
}
