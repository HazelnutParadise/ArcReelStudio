import { useTranslation } from "react-i18next";

import { API } from "@/api";
import { StockPickerDialog } from "@/components/stock/StockPickerDialog";
import type { AssetSheetType } from "@/types";
import type { StockItem } from "@/types/stock";

import { rejectIfAssetBusy } from "./assetBusyGuard";

interface AssetStockImageDialogProps {
  projectName: string;
  assetType: AssetSheetType;
  name: string;
  /** 存图在途时为 true，卡片据此禁用其他会写这张资产图的入口。 */
  onUploadingChange: (uploading: boolean) => void;
  onReload?: () => Promise<unknown> | void;
  onClose: () => void;
}

/**
 * 从免版权素材库给一张资产图挑图（docs/adr/0128）：选中的图片与上传走同一条路，
 * 取回档案后经图片上传接口存成这张资产图。
 */
export function AssetStockImageDialog({
  projectName,
  assetType,
  name,
  onUploadingChange,
  onReload,
  onClose,
}: AssetStockImageDialogProps) {
  const { t } = useTranslation(["dashboard", "assets"]);

  const store = async (item: StockItem) => {
    if (rejectIfAssetBusy(assetType, projectName, name, t)) return;
    onUploadingChange(true);
    try {
      const blob = await API.fetchStockImage(item);
      const extension = blob.type === "image/png" ? "png" : blob.type === "image/webp" ? "webp" : "jpg";
      await API.uploadFile(projectName, assetType, new File([blob], `stock.${extension}`, { type: blob.type }), name);
      await onReload?.();
    } finally {
      onUploadingChange(false);
    }
  };

  return <StockPickerDialog kind="image" onPick={store} onClose={onClose} />;
}
