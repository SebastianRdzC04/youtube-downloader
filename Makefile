.PHONY: dev prod logs down rebuild validate

dev:
	docker compose -f docker-compose.dev.yml up -d --build

prod:
	docker compose -f docker-compose.prod.yml up -d --build

logs:
	docker compose -f docker-compose.dev.yml logs -f backend

down:
	docker compose -f docker-compose.dev.yml down
	docker compose -f docker-compose.prod.yml down

rebuild:
	docker compose -f docker-compose.dev.yml build --no-cache

validate:
	docker compose -f docker-compose.dev.yml config --quiet && echo "✓ dev compose OK"
	docker compose -f docker-compose.prod.yml config --quiet && echo "✓ prod compose OK"
