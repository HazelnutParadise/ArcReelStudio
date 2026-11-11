import { useEffect, useMemo, useState } from "react";
import { API } from "@/api";
import type { Series } from "@/types/series";
import { seriesByProject } from "./lobby-projects";

/**
 * 大厅用的系列列表。加载失败时按「没有系列」处理，大厅不显示系列标记与筛选，其余照常工作；
 * 不弹错误提示，系列只是对项目卡片的补充。
 */
export function useLobbySeries() {
  const [series, setSeries] = useState<Series[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    API.listSeries().then(
      (res) => {
        if (!controller.signal.aborted) setSeries(res.series);
      },
      () => {},
    );
    return () => controller.abort();
  }, []);

  const byProject = useMemo(() => seriesByProject(series), [series]);
  return { series, byProject };
}
