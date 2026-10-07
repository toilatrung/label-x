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
DETECTOR := $(ROOT)/src/detector_worker
COMPOSE  := docker compose -f "$(ROOT)/infrastructure/docker-compose.dev.yml"
UV       := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)
PYTHON_VERSION := 3.12
NODE_MAJOR_MIN := 22

.DEFAULT_GOAL := help
.PHONY: help setup doctor tools env infra-up infra-down infra-logs infra-reset \
        cvat-up cvat-down cvat-logs cvat-ps cvat-superuser cvat-import-sample cvat-bdd100k-sample cvat-audit-learner cvat-hash \
        backend-install frontend-install migrate superuser \
        dev-backend dev-worker dev-beat dev-frontend \
        check lint format test detector-lint detector-test detector-image typecheck gen-api validate-kit clean

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

# CVAT uses the complete upstream Compose bundle pinned by infrastructure/cvat/version.conf.
cvat-up: ## Bật CVAT dev đã pin tại :8080
	bash "$(ROOT)/scripts/development/cvat-dev.sh" up

cvat-down: ## Tắt CVAT dev (giữ volume dữ liệu)
	bash "$(ROOT)/scripts/development/cvat-dev.sh" down

cvat-logs: ## Theo dõi log CVAT dev
	bash "$(ROOT)/scripts/development/cvat-dev.sh" logs

cvat-ps: ## Xem trạng thái container CVAT dev
	bash "$(ROOT)/scripts/development/cvat-dev.sh" ps

cvat-superuser: ## Tạo tài khoản quản trị CVAT dev
	bash "$(ROOT)/scripts/development/cvat-dev.sh" create-superuser

cvat-import-sample: ## Nạp manifest tường minh; cần SAMPLE_IMAGES, SAMPLE_ANNOTATIONS, TOKEN_FILE
	@test -n "$(SAMPLE_IMAGES)" || (echo "Thiếu SAMPLE_IMAGES=/đường/dẫn/images" >&2; exit 2)
	@test -n "$(SAMPLE_ANNOTATIONS)" || (echo "Thiếu SAMPLE_ANNOTATIONS=/đường/dẫn/manifest.json" >&2; exit 2)
	@test -n "$(TOKEN_FILE)" || (echo "Thiếu TOKEN_FILE=/đường/dẫn/dev-tokens.json" >&2; exit 2)
	cd "$(ROOT)" && "$(UV)" run --project "$(BACKEND)" --frozen python \
		scripts/development/cvat_sample.py --images "$(SAMPLE_IMAGES)" \
		--annotations "$(SAMPLE_ANNOTATIONS)" --token-file "$(TOKEN_FILE)" \
		$(if $(BDD100K_IMAGES_ROOT),--bdd100k-images-root "$(BDD100K_IMAGES_ROOT)",)

cvat-bdd100k-sample: ## Tạo manifest BDD100K cache; cần BDD100K_ROOT, FIFTYONE_SAMPLES
	@test -n "$(BDD100K_ROOT)" || (echo "Thiếu BDD100K_ROOT=/đường/dẫn/BDD100K" >&2; exit 2)
	@test -n "$(FIFTYONE_SAMPLES)" || (echo "Thiếu FIFTYONE_SAMPLES=/đường/dẫn/samples.json" >&2; exit 2)
	cd "$(ROOT)" && "$(UV)" run --project "$(BACKEND)" --frozen python \
		scripts/development/bdd100k_sample.py --dataset-root "$(BDD100K_ROOT)" \
		--fiftyone-samples "$(FIFTYONE_SAMPLES)" --splits val --per-split 5

cvat-audit-learner: ## Audit YOLO learner ZIP; cần LEARNER_EXPORTS và BDD100K_IMAGES_ROOT
	@test -n "$(LEARNER_EXPORTS)" || (echo "Thiếu LEARNER_EXPORTS='/path/a.zip /path/b.zip'" >&2; exit 2)
	@test -n "$(BDD100K_IMAGES_ROOT)" || (echo "Thiếu BDD100K_IMAGES_ROOT=/path/images/100k" >&2; exit 2)
	cd "$(ROOT)" && "$(UV)" run --project "$(BACKEND)" --frozen python \
		scripts/development/learner_annotation_audit.py \
		$(foreach export,$(LEARNER_EXPORTS),--export "$(export)") \
		--bdd100k-images-root "$(BDD100K_IMAGES_ROOT)"

cvat-hash: ## Đọc/hash một job; cần JOB_ID và token trong backend .env
	@test -n "$(JOB_ID)" || (echo "Thiếu JOB_ID=<id>" >&2; exit 2)
	cd "$(BACKEND)" && "$(UV)" run --frozen python manage.py hash_cvat_job "$(JOB_ID)"

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

check: lint typecheck test detector-lint detector-test validate-kit ## Toàn bộ kiểm tra trước khi tạo PR

lint: ## Ruff + ESLint
	cd "$(BACKEND)" && "$(UV)" run --frozen ruff check . && "$(UV)" run --frozen ruff format --check .
	cd "$(FRONTEND)" && npm run lint

format: ## Tự format backend
	cd "$(BACKEND)" && "$(UV)" run --frozen ruff check --fix . && "$(UV)" run --frozen ruff format .

typecheck: ## mypy + tsc
	cd "$(BACKEND)" && "$(UV)" run --frozen mypy config accounts guideline cvat_adapter
	cd "$(FRONTEND)" && npm run typecheck

test: ## pytest (cần infra-up) + npm test
	cd "$(BACKEND)" && "$(UV)" run --frozen pytest -q
	cd "$(FRONTEND)" && npm test

detector-test: ## Test worker Detector độc lập (không cần GPU/MMDetection)
	cd "$(DETECTOR)" && "$(UV)" run --frozen --extra dev pytest -q

detector-lint: ## Ruff worker Detector (target Python 3.7 của image MMDetection 2.x)
	cd "$(DETECTOR)" && "$(UV)" run --frozen --extra dev ruff check . && "$(UV)" run --frozen --extra dev ruff format --check .

detector-image: ## Build image GPU worker Detector (vẫn chạy được với --device cpu)
	docker build -f "$(ROOT)/infrastructure/detector-worker/Dockerfile" -t labelx-detector-worker:dev "$(ROOT)"

gen-api: ## Sinh type TypeScript từ OpenAPI (cần dev-backend đang chạy)
	cd "$(FRONTEND)" && npm run gen:api

validate-kit: ## Kiểm tra cấu trúc agentic-sdlc-kit (.agent/, docs/)
	cd "$(ROOT)" && "$(UV)" run --no-project --python 3.12 python scripts/validate-framework.py

clean: ## Xoá môi trường cài đặt local (.venv, node_modules, .next)
	node "$(ROOT)/scripts/development/clean.cjs"
