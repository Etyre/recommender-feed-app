REPO := $(shell pwd)
VENV := backend/.venv
PY := $(VENV)/bin/python
PLIST := com.elityre.feedapp.pipeline.plist

.PHONY: setup dev-backend dev-frontend build run pipeline seed schedule unschedule

setup: $(VENV) frontend/node_modules
	@echo "Setup done. Put your API key in data/.env:  ANTHROPIC_API_KEY=sk-ant-..."

$(VENV):
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -r backend/requirements.txt

frontend/node_modules:
	cd frontend && npm install

# Development: run both of these (in two terminals), open http://localhost:5173
dev-backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# "Prod": one process at http://localhost:8000 serving API + built frontend
build:
	cd frontend && npm run build

run: build
	cd backend && .venv/bin/uvicorn app.main:app --port 8000

pipeline:
	cd backend && .venv/bin/python -m app.pipeline --trigger manual

seed:
	cd backend && .venv/bin/python -m app.seed

schedule:
	mkdir -p data/logs
	cp launchd/$(PLIST) ~/Library/LaunchAgents/$(PLIST)
	-launchctl bootout gui/$$(id -u)/com.elityre.feedapp.pipeline 2>/dev/null
	launchctl bootstrap gui/$$(id -u) ~/Library/LaunchAgents/$(PLIST)
	@echo "Scheduled: pipeline runs at 7:30, 12:30, 17:30, 21:30."

unschedule:
	launchctl bootout gui/$$(id -u)/com.elityre.feedapp.pipeline
	rm ~/Library/LaunchAgents/$(PLIST)
