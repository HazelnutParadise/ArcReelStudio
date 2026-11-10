import { Loader2, Sparkles } from "lucide-react";
import { useId, useState } from "react";
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
import { useAppStore } from "@/stores/app-store";
import { errMsg, voidCall } from "@/utils/async";

const DEFAULT_SECONDS = 3;
const MIN_SECONDS = 1;
const MAX_SECONDS = 30;

/**
 * 音效轨上的「生成音效」：描述发声物与动作，用设定的音效模型生成一个音效，完成后出现在音效库（docs/adr/0127）。
 * 送出后对话框关闭，生成在任务面板里跑；按下按钮不触发轨道的跳转。
 */
export function GenerateSfxButton({ projectName }: { projectName: string }) {
  const { t } = useTranslation("dashboard");
  const [open, setOpen] = useState(false);
  const label = t("edit_view_sfx_generate");
  return (
    <>
      <Button
        variant="ghost"
        size="icon-xs"
        aria-label={label}
        title={label}
        data-testid="edit-sfx-generate"
        onPointerDown={(event) => event.stopPropagation()}
        onClick={() => setOpen(true)}
      >
        <Sparkles aria-hidden />
      </Button>
      {open && <GenerateSfxDialog projectName={projectName} onClose={() => setOpen(false)} />}
    </>
  );
}

function GenerateSfxDialog({ projectName, onClose }: { projectName: string; onClose: () => void }) {
  const { t } = useTranslation("dashboard");
  const ids = { prompt: useId(), seconds: useId(), name: useId() };
  const [prompt, setPrompt] = useState("");
  const [seconds, setSeconds] = useState(String(DEFAULT_SECONDS));
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const parsedSeconds = Number(seconds);
  const secondsValid = Number.isInteger(parsedSeconds) && parsedSeconds >= MIN_SECONDS && parsedSeconds <= MAX_SECONDS;
  const canSubmit = prompt.trim().length > 0 && secondsValid && !submitting;

  const submit = async () => {
    setSubmitting(true);
    const { pushToast } = useAppStore.getState();
    try {
      const result = await API.generateSfx(projectName, {
        prompt: prompt.trim(),
        duration_seconds: parsedSeconds,
        name: name.trim() || null,
      });
      pushToast(result.message, "success");
      onClose();
    } catch (cause) {
      pushToast(t("edit_view_sfx_generate_failed", { message: errMsg(cause) }), "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("edit_view_sfx_generate_title")}</DialogTitle>
          <DialogDescription>{t("edit_view_sfx_generate_desc")}</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={ids.prompt}>{t("edit_view_sfx_generate_prompt")}</Label>
              <Textarea
                id={ids.prompt}
                value={prompt}
                maxLength={2000}
                rows={3}
                placeholder={t("edit_view_sfx_generate_prompt_placeholder")}
                onChange={(event) => setPrompt(event.target.value)}
              />
            </div>
            <div className="flex flex-wrap gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={ids.seconds}>{t("edit_view_sfx_generate_seconds")}</Label>
                <Input
                  id={ids.seconds}
                  type="number"
                  inputMode="numeric"
                  min={MIN_SECONDS}
                  max={MAX_SECONDS}
                  value={seconds}
                  aria-invalid={!secondsValid}
                  onChange={(event) => setSeconds(event.target.value)}
                  className="w-28"
                />
              </div>
              <div className="flex min-w-48 flex-1 flex-col gap-1.5">
                <Label htmlFor={ids.name}>{t("edit_view_sfx_generate_name")}</Label>
                <Input id={ids.name} value={name} maxLength={80} onChange={(event) => setName(event.target.value)} />
              </div>
            </div>
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button disabled={!canSubmit} onClick={() => voidCall(submit())}>
            {submitting && <Loader2 aria-hidden className="animate-spin" />}
            {t("edit_view_sfx_generate_submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
