import { useEffect, useRef, useState } from "react";
import { API } from "@/api";
import type { Asset } from "@/types/asset";

/**
 * 按 id 逐个读取系列里的资产。读不到（已从资产库删除）记为 null，界面上用占位说明；已读过的 id 不再重复请求。
 */
export function useSeriesAssets(ids: string[]): Record<string, Asset | null | undefined> {
  const [assets, setAssets] = useState<Record<string, Asset | null>>({});
  const requested = useRef(new Set<string>());
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const key = ids.join("\n");
  useEffect(() => {
    for (const id of key ? key.split("\n") : []) {
      if (requested.current.has(id)) continue;
      requested.current.add(id);
      API.getAsset(id).then(
        ({ asset }) => {
          if (mounted.current) setAssets((prev) => ({ ...prev, [id]: asset }));
        },
        () => {
          if (mounted.current) setAssets((prev) => ({ ...prev, [id]: null }));
        },
      );
    }
  }, [key]);

  return assets;
}
