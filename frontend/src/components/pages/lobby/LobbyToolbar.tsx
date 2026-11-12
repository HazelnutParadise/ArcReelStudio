import { useTranslation } from "react-i18next";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Series } from "@/types/series";
import { LOBBY_FILTERS, SERIES_FILTER_ALL, SERIES_FILTER_NONE, type LobbyFilter } from "./lobby-projects";

interface LobbyToolbarProps {
  filter: LobbyFilter;
  onFilterChange: (filter: LobbyFilter) => void;
  counts: Record<LobbyFilter, number>;
  /** 系列筛选；没有系列（或系列加载失败）时不传，工具栏不显示这一项。 */
  seriesFilter?: {
    series: Series[];
    value: string;
    onChange: (value: string) => void;
  };
}

/**
 * 吸顶在外壳主体顶端的工具栏：左边是带计数的筛选，右边说明排序方式。排序固定按最近活动，不提供切换。
 * 底色不透明，滚过的卡片不会透出来。
 */
export function LobbyToolbar({ filter, onFilterChange, counts, seriesFilter }: LobbyToolbarProps) {
  const { t } = useTranslation("dashboard");
  return (
    <div className="sticky top-0 z-sticky flex items-center gap-3 border-b border-border bg-background py-2">
      <ToggleGroup
        aria-label={t("lobby_filter_label")}
        size="sm"
        value={[filter]}
        onValueChange={(next: string[]) => {
          // 再次点击当前筛选不会取消选中。
          const picked = next.find((value): value is LobbyFilter =>
            (LOBBY_FILTERS as readonly string[]).includes(value),
          );
          if (picked) onFilterChange(picked);
        }}
      >
        {LOBBY_FILTERS.map((key) => (
          <ToggleGroupItem key={key} value={key}>
            {t(`lobby_filter_${key}`)}
            <span className="text-muted-foreground tabular-nums">{counts[key]}</span>
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      {seriesFilter && <SeriesFilterSelect {...seriesFilter} />}
      <span className="ml-auto shrink-0 text-xs text-muted-foreground">{t("lobby_sort_recent")}</span>
    </div>
  );
}

function SeriesFilterSelect({ series, value, onChange }: NonNullable<LobbyToolbarProps["seriesFilter"]>) {
  const { t } = useTranslation("dashboard");
  const items = [
    { value: SERIES_FILTER_ALL, label: t("lobby_series_all") },
    ...series.map((item) => ({ value: String(item.id), label: item.name })),
    { value: SERIES_FILTER_NONE, label: t("lobby_series_none") },
  ];
  return (
    <Select items={items} value={value} onValueChange={(next: string | null) => onChange(next ?? SERIES_FILTER_ALL)}>
      <SelectTrigger size="sm" aria-label={t("lobby_series_filter_label")} className="w-44 max-w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {items.map((item) => (
          <SelectItem key={item.value} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
