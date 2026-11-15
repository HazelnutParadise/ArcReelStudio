import { Link } from "wouter";
import { useTranslation } from "react-i18next";
import { ROUTE_APP_PROJECTS } from "@/app-routes";
import { buttonVariants } from "@/components/ui/button";

/**
 * 404 页。缺省是「地址不存在」；项目地址里的项目不存在时，传入专属的标题、说明与返回文字，
 * 返回目标都是项目列表。
 */
export function NotFoundPage({
  title,
  description,
  backLabel,
}: {
  title?: string;
  description?: string;
  backLabel?: string;
} = {}) {
  const { t } = useTranslation("common");

  return (
    <main className="relative flex h-dvh overflow-y-auto bg-background p-4 text-foreground">
      <div className="m-auto flex flex-col items-center gap-3 text-center">
        <p aria-hidden className="font-editorial text-9xl leading-none tracking-tighter text-muted-foreground">
          404
        </p>
        <h1 className="text-lg font-medium">{title ?? t("not_found_title")}</h1>
        <p className="text-sm text-muted-foreground">{description ?? t("not_found_description")}</p>
        <Link
          href={`~${ROUTE_APP_PROJECTS}`}
          replace
          className={buttonVariants({ variant: "outline", className: "mt-5" })}
        >
          {backLabel ?? t("not_found_back")}
        </Link>
      </div>
    </main>
  );
}
