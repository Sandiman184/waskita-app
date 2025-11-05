# Waskita - Makefile untuk Docker Management
# Minimal Setup - Simplified Configuration

.PHONY: help install-build build clean status logs restart stop

help: ## Tampilkan bantuan
	@echo "Waskita - Docker Management Commands"
	@echo "===================================="
	@echo ""
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
	@echo ""

install-build: ## Install build dengan opsi clean untuk fresh installation
	@echo "Building Waskita dengan Docker..."
	@if [ "$(CLEAN)" = "true" ]; then \
		echo "Performing clean installation..."; \
		powershell -ExecutionPolicy Bypass -File install-build.ps1 -Clean; \
	else \
		powershell -ExecutionPolicy Bypass -File install-build.ps1; \
	fi

build: ## Normal build dengan data persistent
	@echo "🛠️  Starting normal build..."
	docker-compose -f docker/docker-compose.yml up --build -d
	@echo ""
	@echo "✅ Build completed!"
	@echo "🌐 Access: http://localhost:5000"

clean: ## Hapus semua container dan volume
	@echo "🧹 Cleaning up..."
	docker-compose -f docker/docker-compose.yml down --volumes --remove-orphans
	docker volume rm waskita_postgres_data -f 2>/dev/null || true
	docker system prune -f
	@echo "✅ Cleanup completed!"

status: ## Tampilkan status container
	@echo "📊 Container Status:"
	@docker-compose -f docker/docker-compose.yml ps

logs: ## Tampilkan logs aplikasi
	@echo "📋 Application Logs:"
	@docker-compose -f docker/docker-compose.yml logs -f web

restart: ## Restart services
	@echo "🔄 Restarting services..."
	docker-compose -f docker/docker-compose.yml restart
	@echo "✅ Services restarted!"

stop: ## Stop semua services
	@echo "⏹️  Stopping all services..."
	docker-compose -f docker/docker-compose.yml down
	@echo "✅ All services stopped!"