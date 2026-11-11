import { useTranslation } from "react-i18next";
import { cn } from "cn";
import type { Series } from "@/types/series";

interface SeriesListProps {
  series: Series[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

/** 系列列表：名称、简介与项目、资产数量。当前选中的一项用 `aria-current` 标出。 */
export function SeriesList({ series, selectedId, onSelect }: SeriesListProps) {
  const { t } = useTranslation("dashboard");
  return (
    <ul aria-label={t("series_list_label")} className="flex flex-col gap-2">
      {series.map((item) => (
        <li key={item.id} className="flex min-w-0">
          <button
            type="button"
            aria-current={item.id === selectedId ? "true" : undefined}
            onClick={() => onSelect(item.id)}
            className={cn(
              "flex min-w-0 flex-1 flex-col gap-1 rounded-lg border bg-card px-3 py-2.5 text-left outline-none transition-colors duration-fast focus-visible:ring-3 focus-visible:ring-ring/50",
              item.id === selectedId ? "border-primary bg-primary/10" : "border-border hover:border-input",
            )}
          >
            <span className="truncate text-sm font-medium">{item.name}</span>
            {item.description && <span className="line-clamp-2 text-xs text-muted-foreground">{item.description}</span>}
            <span className="text-xs text-muted-foreground tabular-nums">
              {t("series_list_counts", { projects: item.project_names.length, assets: item.asset_ids.length })}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
