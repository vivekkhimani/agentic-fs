# agentic-fs — single entry point for local dev tasks.
# Run `make` (or `make help`) to list targets.

.DEFAULT_GOAL := help
.PHONY: help sync test lint fmt bump up down logs seed dev docker-build clean

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- Python workspace ---

sync: ## Install/sync the uv workspace
	uv sync

test: ## Run the Python test suite
	uv run pytest packages

lint: ## Lint + format check
	uv run ruff check packages
	uv run ruff format --check packages

fmt: ## Auto-format and autofix
	uv run ruff format packages
	uv run ruff check --fix packages

bump: ## Cut a release: compute the SemVer bump from commits, update versions + CHANGELOG, tag
	uv run --group release cz bump
	@echo "Now: git push --follow-tags  (the tag triggers release.yml → publish)"

# --- Local stack (MinIO + DynamoDB Local + the API) ---

up: ## Start the local stack
	docker compose up -d --build

down: ## Stop the local stack
	docker compose down

logs: ## Tail stack logs
	docker compose logs -f

# Creates the dev bucket + catalog table by running the aws CLI inside a
# throwaway container on the compose network (no host aws CLI, dummy creds, local
# endpoints only). Schema mirrors terraform/modules/catalog_dynamodb — keep in sync.
seed: ## Create the local bucket + catalog table (idempotent)
	docker compose run --rm awscli --endpoint-url http://minio:9000 \
		s3api create-bucket --bucket agentic-fs-data || true
	docker compose run --rm awscli --endpoint-url http://dynamodb:8000 \
		dynamodb create-table --table-name agentic-fs-catalog \
		--billing-mode PAY_PER_REQUEST \
		--attribute-definitions \
			AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
			AttributeName=GSI1PK,AttributeType=S AttributeName=GSI2PK,AttributeType=S \
			AttributeName=GSI3PK,AttributeType=S AttributeName=GSI3SK,AttributeType=S \
		--key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
		--global-secondary-indexes \
			'IndexName=gsi1_by_doc,KeySchema=[{AttributeName=GSI1PK,KeyType=HASH}],Projection={ProjectionType=ALL}' \
			'IndexName=gsi2_by_checksum,KeySchema=[{AttributeName=GSI2PK,KeyType=HASH}],Projection={ProjectionType=ALL}' \
			'IndexName=gsi3_by_extraction_status,KeySchema=[{AttributeName=GSI3PK,KeyType=HASH},{AttributeName=GSI3SK,KeyType=RANGE}],Projection={ProjectionType=ALL}' \
		|| true

dev: up ## Start the stack and seed it (one command)
	@echo "waiting for services to become healthy..."
	@sleep 4
	@$(MAKE) --no-print-directory seed
	@echo "ready -> curl localhost:8080/v1/healthz"

docker-build: ## Build the API image
	docker build -t agentic-fs-api .

clean: ## Stop the stack and remove volumes (DESTRUCTIVE)
	docker compose down -v
