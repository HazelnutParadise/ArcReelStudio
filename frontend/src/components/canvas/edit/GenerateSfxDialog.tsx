import { Loader2, Sparkles } from "lucide-react";
import { useState } from "react";
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
import { useAppStore } from "@/stores/app-store";
import { errMsg, voidCall } from "@/utils/async";

import { GenerateAudioFields } from "./GenerateAudioFields";

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
          <GenerateAudioFields
            kind="sfx"
            prompt={prompt}
            onPromptChange={setPrompt}
            promptRows={3}
            seconds={seconds}
            onSecondsChange={setSeconds}
            secondsRange={{ min: MIN_SECONDS, max: MAX_SECONDS }}
            secondsValid={secondsValid}
            name={name}
            onNameChange={setName}
          />
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
