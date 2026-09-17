Create a CLAUDE.md file at the repo root for this project. Do not create any other files or run any commands.

Project: humanq, an open-source task board where AI agents post requests for human decisions over HTTP, the board ranks them by how much work is blocked behind each, a human resolves them, and agents poll for the resolution. The board itself never calls an LLM.

Include these sections:

Layout: board/ is a FastAPI service with SQLite, served with uvicorn, static HTML board in board/static. sdk/humanq is a pip-installable client with only httpx as a dependency. examples/ holds a Claude Code hook and a generic OpenAI-compatible worker. tests/ uses pytest. Managed with uv as a workspace, Python 3.12.

Locked decisions: request types are exactly approval, choice, credential, clarification. Ranking score is blocked_tasks * 10 + minutes_waiting, with a bonus for credential type. Agents poll every 5 seconds. SQLite only, single node, no Postgres, no Redis, no frontend framework.

Code rules: no comments or docstrings in code, no emojis anywhere, no long hyphens in code or docs, type hints on all functions, ruff for lint and format, tests for every module before moving to the next, Pydantic v2 and SQLAlchemy 2.0 style, pydantic-settings for config.

Working rules: before writing code that uses a library, check the installed version in uv.lock and read its current docs rather than relying on memory, since APIs change. Make one focused change at a time. Run uv run pytest and uv run ruff check . after every change and show the real output. Never install with pip, only uv add. Never read or print the contents of .env or any .db file. Ask before adding a new dependency.

Keep the file under 60 lines and write it in plain prose and short lists.