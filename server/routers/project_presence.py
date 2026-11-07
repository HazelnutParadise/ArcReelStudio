"""
项目在线成员：工作区的每个标签页定时报到正在看的位置，关闭时离开；名单变化经项目事件流广播。
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from lib.infra.api_errors import BadRequestError, NotFoundError
from lib.project.project_manager import get_project_manager
from server.auth import CurrentUser
from server.services.project.project_presence import ProjectPresenceService

router = APIRouter()

#: 标签页标识由前端生成，只允许字母、数字、下划线与连字符。
_CLIENT_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class PresenceHeartbeat(BaseModel):
    client_id: str = Field(pattern=_CLIENT_ID_PATTERN, description="标签页标识，同一标签页每次报到不变")
    view: str | None = Field(
        default=None, max_length=200, description="正在看的工作区位置（如 episodes/3），不在具体页面时为空"
    )


class PresenceMember(BaseModel):
    user_id: str
    username: str
    views: list[str] = Field(description="这位成员各标签页正在看的位置，去重排序")


class PresenceRoster(BaseModel):
    members: list[PresenceMember]


def get_project_presence_service(request: Request) -> ProjectPresenceService:
    return request.app.state.project_presence_service


PresenceService = Annotated[ProjectPresenceService, Depends(get_project_presence_service)]


async def _existing_project(project_name: str) -> str:
    try:
        await asyncio.to_thread(get_project_manager().get_project_path, project_name)
    except FileNotFoundError as exc:
        raise NotFoundError("project_not_found", name=project_name) from exc
    except ValueError as exc:
        raise BadRequestError("invalid_project_name", name=project_name) from exc
    return project_name


@router.put("/projects/{project_name}/presence", response_model=PresenceRoster)
async def report_presence(
    project_name: Annotated[str, Depends(_existing_project)],
    body: PresenceHeartbeat,
    user: CurrentUser,
    presence: PresenceService,
) -> dict:
    """标签页报到（打开项目时与每 20 秒各一次，切换页面时立即再报）；返回项目当前的在线名单。"""
    members = presence.heartbeat(
        project_name,
        body.client_id,
        user_id=user.id,
        username=user.username or user.sub,
        view=body.view,
    )
    return {"members": members}


@router.delete("/projects/{project_name}/presence/{client_id}", status_code=204)
async def leave_presence(project_name: str, client_id: str, user: CurrentUser, presence: PresenceService) -> Response:
    """标签页关闭或离开项目时调用；只移除本人的标签页，未登记时不做任何事。"""
    presence.leave(project_name, client_id, user_id=user.id)
    return Response(status_code=204)
