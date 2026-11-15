import { Link } from "wouter";
import { FileQuestion } from "lucide-react";
import { useTranslation } from "react-i18next";
import { buttonVariants } from "@/components/ui/button";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";

/**
 * 项目工作区里找不到的地址：画布内显示空状态，外壳保留。缺省是没有路由承接的子路径，回到项目概览；
 * 地址里的集不存在等情形传入专属的标题、说明与返回目标。
 */
export function WorkspaceNotFound({
  title,
  description,
  backHref = "/",
  backLabel,
}: {
  title?: string;
  description?: string;
  backHref?: string;
  backLabel?: string;
} = {}) {
  const { t } = useTranslation(["dashboard", "common"]);
  return (
    <div className="relative flex min-h-0 flex-1 overflow-y-auto">
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <FileQuestion aria-hidden />
          </EmptyMedia>
          <EmptyTitle role="heading" aria-level={1}>
            {title ?? t("dashboard:workspace_not_found_title")}
          </EmptyTitle>
          <EmptyDescription>{description ?? t("common:not_found_description")}</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Link href={backHref} replace className={buttonVariants({ variant: "outline" })}>
            {backLabel ?? t("dashboard:workspace_not_found_back")}
          </Link>
        </EmptyContent>
      </Empty>
    </div>
  );
}
