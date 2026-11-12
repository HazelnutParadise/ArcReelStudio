"""系列 ORM model：项目之上的一层，几个项目共用世界观、剧情设定与一组资产（docs/adr/0129）。"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin

SERIES_NAME_MAX_LENGTH = 80
#: 世界观与剧情设定各自的字数上限：会整段放进 Agent 的系统提示。
SERIES_SETTING_MAX_LENGTH = 6000


class Series(TimestampMixin, Base):
    """一个系列。``world_setting`` 与 ``plot_setting`` 是系列内各项目共用的设定，Agent 开始会话时读到。"""

    __tablename__ = "series"
    __table_args__ = (Index("uq_series_name", "name", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(SERIES_NAME_MAX_LENGTH), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    world_setting: Mapped[str] = mapped_column(Text, default="", nullable=False)
    plot_setting: Mapped[str] = mapped_column(Text, default="", nullable=False)


class SeriesProject(TimestampMixin, Base):
    """项目属于哪个系列。项目没有数据库表，这里以项目名（即项目 ID）为主键：一个项目至多属于一个系列。"""

    __tablename__ = "series_project"
    __table_args__ = (Index("ix_series_project_series_id", "series_id"),)

    project_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), nullable=False)


class SeriesAsset(TimestampMixin, Base):
    """系列共用的全局资产库条目。系列只记「用哪几条」，资产本身仍在资产库里，套用到项目时复制一份。"""

    __tablename__ = "series_asset"

    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
