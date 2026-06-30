"""MySQL connection URL parsing and async connect helpers."""

from urllib.parse import urlparse


def parse_host(url: str) -> str:
    return urlparse(url).hostname or "localhost"


def parse_port(url: str) -> int:
    return urlparse(url).port or 3306


def parse_user(url: str) -> str:
    return urlparse(url).username or "root"


def parse_password(url: str) -> str:
    return urlparse(url).password or ""


def parse_db(url: str) -> str:
    return (urlparse(url).path or "/").lstrip("/")


async def connect_mysql(connection_url: str):
    import aiomysql

    return await aiomysql.connect(
        host=parse_host(connection_url),
        port=parse_port(connection_url),
        user=parse_user(connection_url),
        password=parse_password(connection_url),
        db=parse_db(connection_url),
    )
