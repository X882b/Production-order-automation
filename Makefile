.PHONY: start stop logs watcher gui status

start:
	@echo "Starting Yu-Label services..."
	docker compose up -d
	@echo "✔ Services are running"

stop:
	@echo "Stopping Yu-Label services..."
	docker compose down

status:
	docker compose ps

watcher:
	docker compose logs -f watcher

logs:
	docker compose logs -f

gui:
	@echo "Starting GUI..."
	cd "$(CURDIR)" && . .venv/bin/activate && python3 client/gui_main.py

# cd "/path/to/project"

