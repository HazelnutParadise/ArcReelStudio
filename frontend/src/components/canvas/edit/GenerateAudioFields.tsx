import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface GenerateAudioFieldsProps {
  /** 文案前缀的来源：BGM 与音效各有一套 `edit_view_<kind>_generate_*`。 */
  kind: "bgm" | "sfx";
  prompt: string;
  onPromptChange: (value: string) => void;
  promptRows: number;
  seconds: string;
  onSecondsChange: (value: string) => void;
  secondsRange: { min: number; max: number };
  secondsValid: boolean;
  name: string;
  onNameChange: (value: string) => void;
  /** 各自独有的字段，排在共用字段之后（例如音乐的「纯器乐」）。 */
  children?: ReactNode;
}

/** 「生成音乐」与「生成音效」对话框共用的字段：描述、时长、名称。 */
export function GenerateAudioFields({
  kind,
  prompt,
  onPromptChange,
  promptRows,
  seconds,
  onSecondsChange,
  secondsRange,
  secondsValid,
  name,
  onNameChange,
  children,
}: GenerateAudioFieldsProps) {
  const { t } = useTranslation("dashboard");
  const promptId = useId();
  const secondsId = useId();
  const nameId = useId();
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={promptId}>{t(`edit_view_${kind}_generate_prompt`)}</Label>
        <Textarea
          id={promptId}
          value={prompt}
          maxLength={2000}
          rows={promptRows}
          placeholder={t(`edit_view_${kind}_generate_prompt_placeholder`)}
          onChange={(event) => onPromptChange(event.target.value)}
        />
      </div>
      <div className="flex flex-wrap gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={secondsId}>{t(`edit_view_${kind}_generate_seconds`)}</Label>
          <Input
            id={secondsId}
            type="number"
            inputMode="numeric"
            min={secondsRange.min}
            max={secondsRange.max}
            value={seconds}
            aria-invalid={!secondsValid}
            onChange={(event) => onSecondsChange(event.target.value)}
            className="w-28"
          />
        </div>
        <div className="flex min-w-48 flex-1 flex-col gap-1.5">
          <Label htmlFor={nameId}>{t(`edit_view_${kind}_generate_name`)}</Label>
          <Input id={nameId} value={name} maxLength={80} onChange={(event) => onNameChange(event.target.value)} />
        </div>
      </div>
      {children}
    </div>
  );
}
