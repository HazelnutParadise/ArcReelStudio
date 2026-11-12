import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";

interface TrackActionButtonProps {
  label: string;
  testId: string;
  disabled?: boolean;
  onClick: () => void;
  /** 按钮里的图标。 */
  children: ReactNode;
}

/** 轨道名旁的小图标按钮。按下时不把指针事件传给轨道，免得触发轨道的跳转。 */
export function TrackActionButton({ label, testId, disabled, onClick, children }: TrackActionButtonProps) {
  return (
    <Button
      variant="ghost"
      size="icon-xs"
      aria-label={label}
      title={label}
      disabled={disabled}
      data-testid={testId}
      onPointerDown={(event) => event.stopPropagation()}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}
