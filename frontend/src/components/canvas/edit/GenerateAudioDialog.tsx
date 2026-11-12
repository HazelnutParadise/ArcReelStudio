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
import { TrackActionButton } from "./TrackActionButton";

type AudioKind = "bgm" | "sfx";

/** 各轨长度的默认值与上下限（秒），与后端生成任务的校验一致。 */
const SECONDS: Record<AudioKind, { initial: number; min: number; max: number }> = {
  bgm: { initial: 60, min: 3, max: 600 },
  sfx: { initial: 3, min: 1, max: 30 },
};

const PROMPT_ROWS: Record<AudioKind, number> = { bgm: 4, sfx: 3 };

/**
 * BGM 轨的「生成音乐」与音效轨的「生成音效」：写下想要的声音与长度，用设定的音乐或音效模型生成，
 * 完成后出现在 BGM 库或音效库（docs/adr/0126、0127）。送出后对话框关闭，生成在任务面板里跑。
 */
export function GenerateAudioButton({ projectName, kind }: { projectName: string; kind: AudioKind }) {
  const { t } = useTranslation("dashboard");
  const [open, setOpen] = useState(false);
  return (
    <>
      <TrackActionButton
        label={t(`edit_view_${kind}_generate`)}
        testId={`edit-${kind}-generate`}
        onClick={() => setOpen(true)}
      >
        <Sparkles aria-hidden />
      </TrackActionButton>
      {open && <GenerateAudioDialog projectName={projectName} kind={kind} onClose={() => setOpen(false)} />}
    </>
  );
}

function GenerateAudioDialog({
  projectName,
  kind,
  onClose,
}: {
  projectName: string;
  kind: AudioKind;
  onClose: () => void;
}) {
  const { t } = useTranslation("dashboard");
  const instrumentalId = useId();
  const range = SECONDS[kind];
  const [prompt, setPrompt] = useState("");
  const [seconds, setSeconds] = useState(String(range.initial));
  const [name, setName] = useState("");
  const [instrumental, setInstrumental] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const parsedSeconds = Number(seconds);
  const secondsValid = Number.isInteger(parsedSeconds) && parsedSeconds >= range.min && parsedSeconds <= range.max;
  const canSubmit = prompt.trim().length > 0 && secondsValid && !submitting;

  const submit = async () => {
    setSubmitting(true);
    const { pushToast } = useAppStore.getState();
    const request = { prompt: prompt.trim(), duration_seconds: parsedSeconds, name: name.trim() || null };
    try {
      const result =
        kind === "bgm"
          ? await API.generateMusic(projectName, { ...request, instrumental })
          : await API.generateSfx(projectName, request);
      pushToast(result.message, "success");
      onClose();
    } catch (cause) {
      pushToast(t(`edit_view_${kind}_generate_failed`, { message: errMsg(cause) }), "error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t(`edit_view_${kind}_generate_title`)}</DialogTitle>
          <DialogDescription>{t(`edit_view_${kind}_generate_desc`)}</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <GenerateAudioFields
            kind={kind}
            prompt={prompt}
            onPromptChange={setPrompt}
            promptRows={PROMPT_ROWS[kind]}
            seconds={seconds}
            onSecondsChange={setSeconds}
            secondsRange={{ min: range.min, max: range.max }}
            secondsValid={secondsValid}
            name={name}
            onNameChange={setName}
          >
            {kind === "bgm" && (
              <div className="flex items-center gap-2">
                <Checkbox
                  id={instrumentalId}
                  checked={instrumental}
                  onCheckedChange={(checked) => setInstrumental(checked === true)}
                />
                <Label htmlFor={instrumentalId}>{t("edit_view_bgm_generate_instrumental")}</Label>
              </div>
            )}
          </GenerateAudioFields>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button disabled={!canSubmit} onClick={() => voidCall(submit())}>
            {submitting && <Loader2 aria-hidden className="animate-spin" />}
            {t(`edit_view_${kind}_generate_submit`)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
