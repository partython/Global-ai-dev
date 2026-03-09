# ============================================================
# Priya Global Platform — Makefile
# ============================================================

.PHONY: help build build-base build-services build-dashboard \
        up down restart logs ps \
        up-core up-channels up-business up-advanced up-ops

COMPOSE = docker compose
REGISTRY ?= priya-global

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Build ───

build-base: ## Build Python base image
	docker build -f Dockerfile.python-base -t $(REGISTRY)/python-base:latest .

build-services: build-base ## Build all service images
	@for svc in gateway auth tenant channel_router ai_engine \
		whatsapp email voice social webchat sms telegram \
		billing analytics marketing ecommerce notification plugins handoff leads \
		conversation_intel appointments knowledge voice_ai video rcs workflows \
		advanced_analytics ai_training marketplace \
		compliance health_monitor cdn_manager deployment tenant_config; do \
		port=$$(grep -A5 "$$svc" config/ecosystem.config.js | grep -oP '\d{4}' | head -1); \
		echo "Building $$svc (port $$port)..."; \
		docker build -f Dockerfile.service \
			--build-arg SERVICE_NAME=$$svc \
			--build-arg SERVICE_PORT=$$port \
			-t $(REGISTRY)/$$svc:latest . || exit 1; \
	done

build-dashboard: ## Build dashboard image
	docker build -f Dockerfile.dashboard -t $(REGISTRY)/dashboard:latest .

build: build-services build-dashboard ## Build everything

# ─── Run ───

up-infra: ## Start infrastructure (postgres, redis, kafka)
	$(COMPOSE) --profile infra up -d

up-core: up-infra ## Start core services
	$(COMPOSE) --profile core up -d

up-channels: ## Start channel services
	$(COMPOSE) --profile channels up -d

up-business: ## Start business services
	$(COMPOSE) --profile business up -d

up-advanced: ## Start advanced services
	$(COMPOSE) --profile advanced up -d

up-ops: ## Start ops services
	$(COMPOSE) --profile ops up -d

up: ## Start ALL services
	$(COMPOSE) --profile infra --profile core --profile channels --profile business --profile advanced --profile ops up -d

down: ## Stop all services
	$(COMPOSE) down

restart: down up ## Restart all services

logs: ## Tail all logs
	$(COMPOSE) logs -f --tail=50

ps: ## Show running services
	$(COMPOSE) ps

# ─── Individual service ───

up-%: ## Start a specific service (e.g., make up-gateway)
	$(COMPOSE) up -d $*

logs-%: ## Tail logs for a specific service
	$(COMPOSE) logs -f --tail=50 $*

restart-%: ## Restart a specific service
	$(COMPOSE) restart $*

# ─── Database ───

db-shell: ## Open PostgreSQL shell
	docker exec -it priya-postgres psql -U priya -d priya_global

redis-shell: ## Open Redis CLI
	docker exec -it priya-redis redis-cli

# ─── Cleanup ───

clean: ## Remove all containers and volumes
	$(COMPOSE) down -v --remove-orphans
	docker image prune -f
