import { Loader2, Sparkles } from "lucide-react";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { API } from "@/api";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { useAppStore } from "@/stores/app-store";
import { errMsg, voidCall } from "@/utils/async";

import { GenerateAudioFields } from "./GenerateAudioFields";

const DEFAULT_SECONDS = 60;
const MIN_SECONDS = 3;
const MAX_SECONDS = 600;

/**
 * BGM 轨上的「生成音乐」：写下想要的风格与长度，用设定的音乐模型生成一首，完成后出现在 BGM 库（docs/adr/0126）。
 * 送出后对话框关闭，生成在任务面板里跑；按下按钮不触发轨道的跳转。
 */
export function GenerateMusicButton({ projectName }: { projectName: string }) {
  const { t } = useTranslation("dashboard");
  const [open, setOpen] = useState(false);
  const label = t("edit_view_bgm_generate");
  return (
    <>
      <Button
        variant="ghost"
        size="icon-xs"
        aria-label={label}
        title={label}
        data-testid="edit-bgm-generate"
        onPointerDown={(event) => event.stopPropagation()}
        onClick={() => setOpen(true)}
      >
        <Sparkles aria-hidden />
      </Button>
      {open && <GenerateMusicDialog projectName={projectName} onClose={() => setOpen(false)} />}
    </>
  );
}

function GenerateMusicDialog({ projectName, onClose }: { projectName: string; onClose: () => void }) {
  const { t } = useTranslation("dashboard");
  const instrumentalId = useId();
  const [prompt, setPrompt] = useState("");
  const [seconds, setSeconds] = useState(String(DEFAULT_SECONDS));
  const [name, setName] = useState("");
  const [instrumental, setInstrumental] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const parsedSeconds = Number(seconds);
  const secondsValid = Number.isInteger(parsedSeconds) && parsedSeconds >= MIN_SECONDS && parsedSeconds <= MAX_SECONDS;
  const canSubmit = prompt.trim().length > 0 && secondsValid && !submitting;

  const submit = async () => {
    setSubmitting(true);
    const { pushToast } = useAppStore.getState();
    try {
      const result = await API.generateMusic(projectName, {
        prompt: prompt.trim(),
        duration_seconds: parsedSeconds,
        instrumental,
        name: name.trim() || null,
      });
      pushToast(result.message, "success");
      onClose();
    } catch (cause) {
      pushToast(t("edit_view_bgm_generate_failed", { message: errMsg(cause) }), "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("edit_view_bgm_generate_title")}</DialogTitle>
          <DialogDescription>{t("edit_view_bgm_generate_desc")}</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <GenerateAudioFields
            kind="bgm"
            prompt={prompt}
            onPromptChange={setPrompt}
            promptRows={4}
            seconds={seconds}
            onSecondsChange={setSeconds}
            secondsRange={{ min: MIN_SECONDS, max: MAX_SECONDS }}
            secondsValid={secondsValid}
            name={name}
            onNameChange={setName}
          >
            <div className="flex items-center gap-2">
              <Checkbox
                id={instrumentalId}
                checked={instrumental}
                onCheckedChange={(checked) => setInstrumental(checked === true)}
              />
              <Label htmlFor={instrumentalId}>{t("edit_view_bgm_generate_instrumental")}</Label>
            </div>
          </GenerateAudioFields>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button disabled={!canSubmit} onClick={() => voidCall(submit())}>
            {submitting && <Loader2 aria-hidden className="animate-spin" />}
            {t("edit_view_bgm_generate_submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
