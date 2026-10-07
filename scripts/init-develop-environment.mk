# LabelX — cài đặt và chạy môi trường dev.
#
# Dev mới: xem env-setup.html; bootstrap không cần Make.
# Hoặc gọi trực tiếp: make -f scripts/init-develop-environment.mk setup
#
# Bootstrap Ubuntu/WSL: bash scripts/init-develop-environment.sh --install-global; Windows: script .ps1.
# Make chỉ là wrapper Bash cho các lệnh dev; không cần Make để bootstrap.

SHELL := /bin/bash
ROOT     := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)
BACKEND  := $(ROOT)/src/backend
FRONTEND := $(ROOT)/src/frontend
COMPOSE  := docker compose -f "$(ROOT)/infrastructure/docker-compose.dev.yml"
UV       := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)
PYTHON_VERSION := 3.12
NODE_MAJOR_MIN := 22

.DEFAULT_GOAL := help
.PHONY: help setup doctor tools env infra-up infra-down infra-logs infra-reset \
        backend-install frontend-install migrate superuser \
        dev-backend dev-worker dev-beat dev-frontend \
        check lint format test typecheck gen-api validate-kit clean

help: ## Liệt kê lệnh
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup

setup: ## Khởi tạo local tuần tự; cài global bằng script --install-global trước nếu thiếu
	bash "$(ROOT)/scripts/init-develop-environment.sh"

doctor: ## Kiểm tra công cụ, dependency, dịch vụ và migrations (không cài)
	bash "$(ROOT)/scripts/init-develop-environment.sh" --check

tools: ## Cài công cụ global và môi trường local trên Ubuntu/WSL
	bash "$(ROOT)/scripts/init-develop-environment.sh" --install-global

env: ## Tạo .env bằng secret ngẫu nhiên; giữ nguyên file đã có (cần Node)
	node "$(ROOT)/scripts/development/environment.cjs" env
# ---------------------------------------------------------------- infrastructure

infra-up: ## Bật PostgreSQL, Redis, SeaweedFS (S3) (đợi healthy)
	$(COMPOSE) up -d --wait postgres redis seaweedfs
	$(COMPOSE) run --rm seaweedfs-init

infra-down: ## Tắt hạ tầng (giữ dữ liệu)
	$(COMPOSE) down

infra-logs: ## Xem log hạ tầng
	$(COMPOSE) logs -f

infra-reset: ## XOÁ dữ liệu Postgres/SeaweedFS local rồi bật lại
	@read -p "Xoá toàn bộ dữ liệu dev local? [y/N] " ans; [ "$$ans" = "y" ] || exit 1
	$(COMPOSE) down -v
	$(MAKE) -f "$(ROOT)/scripts/init-develop-environment.mk" infra-up
	$(MAKE) -f "$(ROOT)/scripts/init-develop-environment.mk" migrate

# ---------------------------------------------------------------- dependencies

backend-install: ## Cài dependency Python theo uv.lock
	cd "$(BACKEND)" && "$(UV)" sync --frozen

frontend-install: ## Cài dependency Node theo package-lock.json
	cd "$(FRONTEND)" && npm ci --no-audit --no-fund

migrate: ## Chạy Django migrations
	cd "$(BACKEND)" && "$(UV)" run --frozen python manage.py migrate

superuser: ## Tạo tài khoản Django admin
	cd "$(BACKEND)" && "$(UV)" run --frozen python manage.py createsuperuser

# ---------------------------------------------------------------- run

dev-backend: ## Chạy Django API ở :8000
	cd "$(BACKEND)" && "$(UV)" run --frozen python manage.py runserver 0.0.0.0:8000

dev-worker: ## Chạy Celery worker
	cd "$(BACKEND)" && "$(UV)" run --frozen celery -A config worker -l info

dev-beat: ## Chạy Celery beat (chưa có task/lịch polling CVAT)
	cd "$(BACKEND)" && "$(UV)" run --frozen celery -A config beat -l info

dev-frontend: ## Chạy Next.js ở :3000
	cd "$(FRONTEND)" && npm run dev

# ---------------------------------------------------------------- quality

check: lint typecheck test validate-kit ## Toàn bộ kiểm tra trước khi tạo PR

lint: ## Ruff + ESLint
	cd "$(BACKEND)" && "$(UV)" run --frozen ruff check . && "$(UV)" run --frozen ruff format --check .
	cd "$(FRONTEND)" && npm run lint

format: ## Tự format backend
	cd "$(BACKEND)" && "$(UV)" run --frozen ruff check --fix . && "$(UV)" run --frozen ruff format .

typecheck: ## mypy + tsc
	cd "$(BACKEND)" && "$(UV)" run --frozen mypy config guideline
	cd "$(FRONTEND)" && npm run typecheck

test: ## pytest (cần infra-up)
	cd "$(BACKEND)" && "$(UV)" run --frozen pytest -q

gen-api: ## Sinh type TypeScript từ OpenAPI (cần dev-backend đang chạy)
	cd "$(FRONTEND)" && npm run gen:api

validate-kit: ## Kiểm tra cấu trúc agentic-sdlc-kit (.agent/, docs/)
	cd "$(ROOT)" && "$(UV)" run --no-project --python 3.12 python scripts/validate-framework.py

clean: ## Xoá môi trường cài đặt local (.venv, node_modules, .next)
	node "$(ROOT)/scripts/development/clean.cjs"
