import type { ReactNode } from "react";
import { ChevronLeft } from "lucide-react";

import { TruncatedText } from "@/components/shared/TruncatedText";
import { Button } from "@/components/ui/button";

interface PageHeaderProps {
  /** 「返回」按钮；返回到进入页面之前的位置时，用 `useReturnTo` 取得 `onClick`。 */
  back?: { label: string; onClick: () => void };
  title?: string;
  subtitle?: string;
  /** 标题组之后的自定义内容，如项目大厅的品牌与搜索。 */
  children?: ReactNode;
  /** 靠右的页面级动作。 */
  actions?: ReactNode;
}

/**
 * 页面外壳的顶栏，高 56px：「返回 | 标题 | 副标题」成组靠左，返回箭头与侧栏图标在同一条竖线上，
 * 页面级动作靠右。顶栏变窄时「返回」只留箭头、副标题收起，页名始终完整显示。顶栏是名为 `topbar` 的尺寸容器：放进来的品牌、搜索与动作按 `@xl/topbar:` 这类容器查询收放。
 */
export function PageHeader({ back, title, subtitle, children, actions }: PageHeaderProps) {
  return (
    <header className="@container/topbar flex h-14 shrink-0 items-center gap-3 border-b border-border pr-3 pl-3 md:pr-6 xl:pr-8">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        {back && (
          <>
            <Button variant="ghost" onClick={back.onClick}>
              <ChevronLeft aria-hidden data-icon="inline-start" />
              <span className="sr-only @xl/topbar:not-sr-only">{back.label}</span>
            </Button>
            <span aria-hidden className="h-4 w-px shrink-0 bg-border" />
          </>
        )}
        {title && (
          // 页名很短，窄顶栏里优先保住它：不参与收缩，让副标题先收起
          <h1 className="max-w-full min-w-0 shrink-0 text-base font-medium">
            <TruncatedText text={title} />
          </h1>
        )}
        {subtitle && (
          <span className="hidden min-w-0 @3xl/topbar:flex">
            <TruncatedText text={subtitle} className="text-sm text-muted-foreground" />
          </span>
        )}
        {children}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-1 @xl/topbar:gap-2">{actions}</div>}
    </header>
  );
}
