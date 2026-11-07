"""在服务器上管理 ArcReel 账号：列出账号、重设密码。忘记密码或管理员无法登录时使用。

    uv run python -m scripts.manage_users list
    uv run python -m scripts.manage_users reset-password <用户名> [--password 新密码]

在仓库根目录（Docker 镜像中为 ``/app``）执行。Docker 部署在 Compose 目录执行
``docker compose exec arcreel uv run python -m scripts.manage_users ...``。
连接的数据库与服务相同（``DATABASE_URL``，未设置时为数据根下的 SQLite）。重设密码会让该账号现有的登录失效。
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from collections.abc import Sequence

from lib.db import async_session_factory, close_db
from lib.db.repositories.user_repo import UserRepository
from lib.infra.api_errors import ApiError
from lib.infra.data_root_layout import DataRootLayout
from server.services import accounts


def _read_password(prompt: str) -> str:
    """终端里不回显地读入；标准输入不是终端（例如管道）时逐行读取，不打印提示。"""
    if sys.stdin.isatty():
        return getpass.getpass(prompt)
    return sys.stdin.readline().rstrip("\r\n")


def _prompt_new_password() -> str | None:
    """请用户输入两次新密码；两次不一致时返回 None。"""
    first = _read_password("新密码：")
    second = _read_password("再输入一次：")
    return first if first == second else None


async def _list() -> int:
    async with async_session_factory() as session:
        users = await accounts.list_accounts(session)
    for user in users:
        status = "启用" if user.is_active else "停用"
        print(f"{user.username}\t{user.role}\t{status}")
    return 0


async def _reset_password(username: str, password: str | None) -> int:
    async with async_session_factory() as session:
        user = await UserRepository(session).get_by_username(accounts.normalize_username(username))
    if user is None:
        print(f"找不到账号：{username}", file=sys.stderr)
        return 1
    # 新密码只从参数或输入读取，不由命令生成，也就不会出现在终端输出与日志里
    new_password = password if password is not None else _prompt_new_password()
    if new_password is None:
        print("两次输入的密码不一致，密码没有修改。", file=sys.stderr)
        return 1
    async with async_session_factory() as session, session.begin():
        await accounts.update_account(
            session,
            actor_id="",
            user_id=user.id,
            password=new_password,
            initial_password_path=DataRootLayout.current().initial_admin_password_path,
        )
    print(f"已重设 {user.username} 的密码。")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.manage_users",
        description="管理 ArcReel 账号：列出账号、重设密码。",
    )
    commands = parser.add_subparsers(dest="command", metavar="<命令>")
    commands.add_parser("list", help="列出所有账号的用户名、角色与启用状态")
    reset = commands.add_parser(
        "reset-password",
        help="重设账号密码，该账号现有的登录随之失效",
        description="重设账号密码。不给 --password 时请你输入两次新密码，输入时不显示。",
    )
    reset.add_argument("username", help="要重设密码的用户名（不区分大小写）")
    reset.add_argument("--password", help=f"新密码，至少 {accounts.MIN_PASSWORD_LENGTH} 个字符")
    return parser


async def _run(args: argparse.Namespace) -> int:
    try:
        if args.command == "list":
            return await _list()
        return await _reset_password(args.username, args.password)
    except ApiError as exc:
        print(f"操作失败：{exc.key}", file=sys.stderr)
        return 1
    finally:
        await close_db()


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
