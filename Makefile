REPO := $(shell pwd)
# Private data dir (db, .env, backups, logs). Mirrors backend/app/config.py: env var,
# else the sibling ../data (data kept outside the git checkout), else ./data.
DATA := $(or $(FEEDAPP_DATA_DIR),$(if $(wildcard $(REPO)/../data/.),$(abspath $(REPO)/../data),$(REPO)/data))
export FEEDAPP_DATA_DIR := $(DATA)
VENV := backend/.venv
PY := $(VENV)/bin/python
SERVER_LABEL := com.elityre.feedapp.server
PIPELINE_LABEL := com.elityre.feedapp.pipeline
AGENTS := $(HOME)/Library/LaunchAgents
UID_ := $(shell id -u)

.PHONY: setup dev-backend dev-frontend build run pipeline backup seed where \
        install uninstall restart schedule unschedule status

setup: $(VENV) frontend/node_modules
	@mkdir -p $(DATA)
	@echo "Setup done. Data dir: $(DATA)"
	@echo "Put your API key in $(DATA)/.env:  ANTHROPIC_API_KEY=sk-ant-..."

$(VENV):
	python3 -m venv $(VENV)
	$(PY) -m pip install -r backend/requirements.txt

frontend/node_modules:
	cd frontend && npm install

# Development: run both of these (in two terminals), open http://localhost:5173
dev-backend:
	cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# "Prod": one process at http://localhost:8000 serving API + built frontend
build:
	cd frontend && npm run build

run: build
	cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000

pipeline:
	cd backend && .venv/bin/python -m app.pipeline --trigger manual

backup:
	cd backend && .venv/bin/python -c "from app.db import connect, migrate; \
	from app.services.backup import run_backup; migrate(); \
	import json; print(json.dumps(run_backup(connect()), indent=1))"

seed:
	cd backend && .venv/bin/python -m app.seed

where:
	@echo "repo: $(REPO)"
	@echo "data: $(DATA)"

# ---- launchd -----------------------------------------------------------------
# Plists in launchd/ are templates: __REPO__ -> this checkout, __DATA__ -> the data dir.

define install_plist
	mkdir -p $(DATA)/logs $(AGENTS)
	sed -e 's|__REPO__|$(REPO)|g' -e 's|__DATA__|$(DATA)|g' launchd/$(1).plist > $(AGENTS)/$(1).plist
	-launchctl bootout gui/$(UID_)/$(1) 2>/dev/null
	launchctl bootstrap gui/$(UID_) $(AGENTS)/$(1).plist
endef

# Always-on server: starts at login, restarts if it dies. App lives at http://localhost:8000
install: build
	$(call install_plist,$(SERVER_LABEL))
	@echo "Installed. The app is always at http://localhost:8000 (logs: $(DATA)/logs/server.log)."

uninstall:
	-launchctl bootout gui/$(UID_)/$(SERVER_LABEL)
	rm -f $(AGENTS)/$(SERVER_LABEL).plist

# After changing backend or frontend code: rebuild and bounce the server.
restart: build
	launchctl kickstart -k gui/$(UID_)/$(SERVER_LABEL)

# Pipeline runs at 7:30 / 12:30 / 17:30 / 21:30; missed runs coalesce on wake.
schedule:
	$(call install_plist,$(PIPELINE_LABEL))
	@echo "Scheduled: pipeline runs at 7:30, 12:30, 17:30, 21:30."

unschedule:
	-launchctl bootout gui/$(UID_)/$(PIPELINE_LABEL)
	rm -f $(AGENTS)/$(PIPELINE_LABEL).plist

status:
	@for l in $(SERVER_LABEL) $(PIPELINE_LABEL); do \
	  echo "== $$l"; launchctl print gui/$(UID_)/$$l 2>/dev/null | grep -E '^\s*(state|pid|last exit code)' || echo "   not installed"; \
	done
