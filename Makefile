check:
	@poetry run ruff check
	@poetry run ruff format --check
	@poetry run pytest -q

codefix:
	@poetry run ruff check --fix
	@poetry run ruff format

.PHONY: check codefix
