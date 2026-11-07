import { useId } from "react";
import { CollabField, liveFieldProps } from "@/collab/CollabField";
import type { LiveEditing } from "@/components/shared/edit-unit/useEditUnit";
import { Input } from "@/components/ui/input";

interface CompactInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** 只读展示：保留可选中的文本，但不接受输入。 */
  readOnly?: boolean;
  /** 所在编辑单元的多人协作绑定与本字段在房间文档里的路径。 */
  live?: LiveEditing | null;
  path?: string;
}

/** 结构化提示词里的单行字段：左侧标签、右侧输入框，放在 `PromptFieldGrid` 的两列里。 */
export function CompactInput({ label, value, onChange, placeholder, readOnly, live = null, path }: CompactInputProps) {
  const id = useId();
  return (
    <>
      <label htmlFor={id} className="text-xs text-muted-foreground">
        {label}
      </label>
      <CollabField live={path ? live : null} path={path ?? ""}>
        <Input
          {...(path ? liveFieldProps(live, path) : {})}
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          readOnly={readOnly}
          placeholder={placeholder}
          className="min-w-0"
        />
      </CollabField>
    </>
  );
}
