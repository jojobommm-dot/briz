"""Сотрудники кабинета менеджера: добавить, сменить пароль, отключить, список.

    venv\\Scripts\\python tools/staff.py add olga "Ольга" --password ...
    venv\\Scripts\\python tools/staff.py password olga --password ...
    venv\\Scripts\\python tools/staff.py disable olga
    venv\\Scripts\\python tools/staff.py list

Без --password пароль спросится в консоли и не останется в истории команд.
"""

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import database  # noqa: E402
from app.lunch_order import now_local  # noqa: E402
from app.models import Staff  # noqa: E402
from app.security import hash_password  # noqa: E402


def ask_password(given: str | None) -> str:
    password = given or getpass.getpass("Пароль: ")
    if len(password) < 8:
        sys.exit("Пароль сотрудника — не короче 8 символов")
    return password


async def main(args) -> None:
    await database.init_db()
    database.engine()
    async with database._sessions() as session:
        staff = await session.scalar(
            select(Staff).where(Staff.login == getattr(args, "login", "").lower())
        )
        if args.cmd == "list":
            for s in (await session.scalars(select(Staff).order_by(Staff.id))).all():
                print(
                    f"{s.login:15} {s.name:20} {s.role:10} {'активен' if s.is_active else 'отключён'}"
                )
        elif args.cmd == "add":
            if staff:
                sys.exit(f"Логин {args.login} уже есть")
            session.add(Staff(login=args.login.lower(), name=args.name, role=args.role,
                              password_hash=hash_password(ask_password(args.password)), created_at=now_local()))  # fmt: skip
            print(f"Добавлен {args.login}")
        elif staff is None:
            sys.exit(f"Нет сотрудника {args.login}")
        elif args.cmd == "password":
            staff.password_hash = hash_password(ask_password(args.password))
            staff.is_active = True
            print(f"Пароль {args.login} изменён")
        elif args.cmd == "disable":
            staff.is_active = False
            print(f"{args.login} отключён")
        await session.commit()
    await database.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("login")
    a.add_argument("name")
    a.add_argument("--role", default="manager")
    a.add_argument("--password")
    pw = sub.add_parser("password")
    pw.add_argument("login")
    pw.add_argument("--password")
    sub.add_parser("disable").add_argument("login")
    sub.add_parser("list")
    asyncio.run(main(p.parse_args()))
