"""Publish and activate new anti-hallucination prompt versions from DEFAULT_PROMPTS."""

import asyncio

from backend.db.prompts import DEFAULT_PROMPTS, UPGRADABLE_PROMPT_ROLES, create_prompt_version
from backend.db.session import async_session_factory, engine


async def upgrade_prompts() -> None:
    async with async_session_factory() as session:
        for role in UPGRADABLE_PROMPT_ROLES:
            content = DEFAULT_PROMPTS[role]
            prompt = await create_prompt_version(session, role, content, activate=True)
            print(f"Activated {role} v{prompt.version}")


async def main() -> None:
    await upgrade_prompts()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
