import { useId, useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { API } from "@/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { errMsg } from "@/utils/async";
import type { Series } from "@/types/series";

interface CreateSeriesDialogProps {
  onClose: () => void;
  onCreated: (series: Series) => void;
}

/** 新建系列：只问名称与简介。名称冲突等服务端拒绝的原因原文显示在表单里，对话框保持打开。 */
export function CreateSeriesDialog({ onClose, onCreated }: CreateSeriesDialogProps) {
  const { t } = useTranslation(["dashboard", "common"]);
  const formId = useId();
  const nameId = useId();
  const descriptionId = useId();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const trimmed = name.trim();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      onCreated(await API.createSeries(trimmed, description.trim()));
      onClose();
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        // 提交中不响应 Esc，避免请求还在途时对话框先消失
        if (!open && !submitting) onClose();
      }}
    >
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>{t("dashboard:series_create_title")}</DialogTitle>
          <DialogDescription>{t("dashboard:series_create_desc")}</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <form id={formId} className="flex flex-col gap-4" onSubmit={(event) => void submit(event)}>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={nameId}>{t("dashboard:series_name_label")}</Label>
              <Input id={nameId} value={name} maxLength={100} onChange={(event) => setName(event.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={descriptionId}>{t("dashboard:series_description_label")}</Label>
              <Textarea
                id={descriptionId}
                rows={3}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </form>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" disabled={submitting} onClick={onClose}>
            {t("common:cancel")}
          </Button>
          <Button type="submit" form={formId} disabled={!trimmed || submitting}>
            {submitting && <Loader2 aria-hidden data-icon="inline-start" className="animate-spin" />}
            {t("dashboard:series_create_submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
