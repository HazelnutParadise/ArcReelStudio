"""免版权素材来源的密钥 ORM model。"""

from __future__ import annotations

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from lib.db.base import Base, TimestampMixin

#: 工作区共用密钥的 ``owner`` 值；成员自己的密钥以账号 id 为 ``owner``。
WORKSPACE_OWNER = ""


class StockSourceKey(TimestampMixin, Base):
    """一个素材来源的一把密钥（docs/adr/0128）。

    ``owner`` 为空串的是整个工作区共用的密钥（Pixabay、Pexels），由管理员设置；否则是某位成员自己的密钥
    （Freesound），只在这位成员搜索与导入时使用。密钥明文落库，读出 API 时经 ``mask_secret`` 掩码，
    与供应商凭证同一规则。
    """

    __tablename__ = "stock_source_key"
    __table_args__ = (Index("uq_stock_source_key_source_owner", "source", "owner", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False, default=WORKSPACE_OWNER)
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
