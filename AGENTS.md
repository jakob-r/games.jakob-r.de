# AGENTS

General concept lives in `idea.md`.
Architecture, patterns, and tech stack live in `ARCHITECTURE.md`.
Agents update `ARCHITECTURE.md` (and this file) as they make decisions.

## Frontend

Mobile first.

## Python

- Python 3.13
- `uv`, `ruff` modern tools

## Local Development (`Makefile`)

- Agents should always create or update the root `Makefile` so running the project locally can be done with `make dev`.

## Git

We use git, all in main branch. 
Agents commit and push to main branch regularly.
If you encounter unstaged changes commit them if it looks like the user just forgot to commit. Otherwise ask the user to commit.