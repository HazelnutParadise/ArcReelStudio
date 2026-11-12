/** 系列（docs/adr/0129）：项目之上的一层，几个项目共用世界观、剧情设定与一组全局资产库条目。 */
export interface Series {
  id: number;
  name: string;
  description: string;
  /** 世界观：系列内各项目共用，Agent 开始会话时读到。 */
  world_setting: string;
  /** 剧情设定：系列内各项目共用，Agent 开始会话时读到。 */
  plot_setting: string;
  /** 属于这个系列、且目前存在的项目（项目 ID）。一个项目至多属于一个系列。 */
  project_names: string[];
  /** 这个系列共用的全局资产库条目 id。套用到项目时复制一份，之后各自独立。 */
  asset_ids: string[];
  updated_at: string | null;
}

export type SeriesSettingsPatch = Partial<Pick<Series, "name" | "description" | "world_setting" | "plot_setting">>;
