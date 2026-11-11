import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { API } from "@/api";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogBody,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useAppStore } from "@/stores/app-store";
import { errMsg } from "@/utils/async";
import type { Series } from "@/types/series";

interface DeleteSeriesDialogProps {
  series: Series;
  open: boolean;
  onClose: () => void;
  onDeleted: (series: Series) => void;
}

/** 删除系列先确认。只删系列本身：项目与资产库资产都保留。 */
export function DeleteSeriesDialog({ series, open, onClose, onDeleted }: DeleteSeriesDialogProps) {
  const { t } = useTranslation(["dashboard", "common"]);
  const [submitting, setSubmitting] = useState(false);

  const handleDelete = async () => {
    setSubmitting(true);
    try {
      await API.deleteSeries(series.id);
      useAppStore.getState().pushToast(t("dashboard:series_deleted", { name: series.name }), "success");
      onDeleted(series);
      onClose();
    } catch (err) {
      useAppStore.getState().pushToast(t("dashboard:series_delete_failed", { message: errMsg(err) }), "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        // 提交中不响应 Esc，避免请求还在途时对话框先消失
        if (!next && !submitting) onClose();
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("dashboard:series_delete_title", { name: series.name })}</AlertDialogTitle>
        </AlertDialogHeader>
        <AlertDialogBody>
          <AlertDialogDescription>{t("dashboard:series_delete_desc")}</AlertDialogDescription>
        </AlertDialogBody>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={submitting}>{t("common:cancel")}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" disabled={submitting} onClick={() => void handleDelete()}>
            {submitting && <Loader2 aria-hidden data-icon="inline-start" className="animate-spin" />}
            {t("dashboard:series_delete")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
