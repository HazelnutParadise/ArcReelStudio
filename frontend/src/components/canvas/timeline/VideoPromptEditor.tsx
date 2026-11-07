import { useTranslation } from "react-i18next";
import { CollabField } from "@/collab/CollabField";
import { liveFieldProps } from "@/collab/live-field-props";
import type { LiveEditing } from "@/components/shared/edit-unit/useEditUnit";
import { Textarea } from "@/components/ui/textarea";
import { CAMERA_MOTIONS, CAMERA_MOTION_I18N_KEYS } from "@/types";
import type { VideoPrompt } from "@/types";
import { CompactInput } from "./CompactInput";
import { PromptFieldGrid } from "./PromptFieldGrid";
import { PromptFieldSelect } from "./PromptFieldSelect";

interface VideoPromptEditorProps {
  prompt: VideoPrompt;
  onUpdate: (patch: Partial<VideoPrompt>) => void;
  /** 只读展示（引导演示项目）：字段可读不可改。 */
  readOnly?: boolean;
  /** 所在分镜编辑单元的多人协作绑定：各字段显示其他人的光标。 */
  live?: LiveEditing | null;
}

/** 结构化的视频提示词：动作描述加可折叠的镜头运动与环境音效。台词在分镜详情的台词区单独编辑。 */
export function VideoPromptEditor({ prompt, onUpdate, readOnly, live = null }: VideoPromptEditorProps) {
  const { t } = useTranslation("dashboard");

  return (
    <div className="flex flex-col gap-2">
      <CollabField live={live} path="video_prompt.action">
        <Textarea
          {...liveFieldProps(live, "video_prompt.action")}
          value={prompt.action}
          onChange={(e) => onUpdate({ action: e.target.value })}
          readOnly={readOnly}
          aria-label={t("detail_video_prompt_title")}
          placeholder={t("video_prompt_placeholder")}
          className="max-h-none"
        />
      </CollabField>
      <PromptFieldGrid title={t("camera_motion_section")}>
        <PromptFieldSelect
          label={t("camera_motion_label")}
          value={prompt.camera_motion}
          options={CAMERA_MOTIONS}
          renderOption={(value) => t(CAMERA_MOTION_I18N_KEYS[value])}
          disabled={readOnly}
          onChange={(camera_motion) => onUpdate({ camera_motion })}
        />
        <CompactInput
          label={t("ambiance_audio_label")}
          value={prompt.ambiance_audio}
          onChange={(ambiance_audio) => onUpdate({ ambiance_audio })}
          live={live}
          path="video_prompt.ambiance_audio"
          readOnly={readOnly}
          placeholder={t("ambiance_audio_placeholder")}
        />
      </PromptFieldGrid>
    </div>
  );
}
