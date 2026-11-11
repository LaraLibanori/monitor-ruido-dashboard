# =============================================
# manage.py - Tarefas de linha de comando
# =============================================
# Criar o primeiro administrador (dentro do Docker):
#   docker compose exec app python manage.py create-admin
# Sem perguntas (ex.: automação/CI):
#   ADMIN_PASSWORD=... python manage.py create-admin --name "Síndico" --email sindico@exemplo.com
# =============================================

import argparse
import getpass
import os
import sys

from auth_service import AuthService, ServiceError
from database import Database
from user_repository import UserRepository


def create_admin(args) -> int:
    name = args.name or input("Nome do administrador: ").strip()
    email = args.email or input("E-mail: ").strip()
    password = os.getenv("ADMIN_PASSWORD") or ""
    if not password:
        password = getpass.getpass("Senha (mínimo 8 caracteres): ")
        if password != getpass.getpass("Repita a senha: "):
            print("As senhas não conferem.", file=sys.stderr)
            return 1

    db = Database()
    db.connect()  # também aplica as migrações pendentes
    try:
        user = AuthService(UserRepository(db)).create_admin(
            name=name, email=email, password=password, phone=args.phone
        )
    except ServiceError as exc:
        print(f"Erro: {exc.message}", file=sys.stderr)
        return 1
    finally:
        db.disconnect()
    print(f"Administrador criado: {user['name']} <{user['email']}> (id {user['id']})")
    print("Entre em http://SEU-IP:5000/admin")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Monitor de Ruído - tarefas administrativas")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="Cria um usuário administrador")
    admin.add_argument("--name")
    admin.add_argument("--email")
    admin.add_argument("--phone")
    admin.set_defaults(func=create_admin)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
