# KampusDey tasks. Local (venv) by default; Docker targets kept for later use.
# On Windows without `make`, use the PowerShell equivalent: .\make.ps1 <target>

ifeq ($(OS),Windows_NT)
PY ?= .venv/Scripts/python
else
PY ?= .venv/bin/python
endif
MANAGE = $(PY) manage.py

.PHONY: install run migrate makemigrations test test-fast lint fmt tailwind tailwind-watch vendor seed \
        import-locations import-external seed-demo periodic shell check up down

install:
	python -m venv .venv
	$(PY) -m pip install -r requirements-dev.txt
	npm install
	npm run vendor
	npm run build:css

run:
	$(MANAGE) runserver

migrate:
	$(MANAGE) migrate
	$(MANAGE) createcachetable

makemigrations:
	$(MANAGE) makemigrations

test:
	$(PY) -m pytest

test-fast:
	$(PY) -m pytest apps/core apps/accounts apps/listings -x

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

fmt:
	$(PY) -m ruff format .
	$(PY) -m ruff check --fix .

tailwind:
	npm run build:css

tailwind-watch:
	npm run watch:css

vendor:
	npm run vendor

seed:
	$(MANAGE) seed_locations

import-locations:
	$(MANAGE) import_locations

import-external:
	$(MANAGE) import_external

seed-demo:
	$(MANAGE) seed_demo

periodic:
	$(MANAGE) run_periodic --loop

shell:
	$(MANAGE) shell

check:
	$(MANAGE) check
	$(MANAGE) makemigrations --check --dry-run

# Docker Compose (optional, not required locally)
up:
	docker compose up -d --build

down:
	docker compose down
