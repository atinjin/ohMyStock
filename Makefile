# OhMyStock — 서버 실행/정지
# 백엔드(FastAPI/uvicorn)와 프론트엔드(Vite) 개발 서버를 백그라운드로 띄우고 정지한다.
# PID/로그는 .run/ 에 저장된다.

BACKEND_PORT  ?= 8000
FRONTEND_PORT ?= 5173
RUN_DIR       := .run

BACKEND_PID   := $(RUN_DIR)/backend.pid
FRONTEND_PID  := $(RUN_DIR)/frontend.pid
BACKEND_LOG   := $(RUN_DIR)/backend.log
FRONTEND_LOG  := $(RUN_DIR)/frontend.log

.DEFAULT_GOAL := help

.PHONY: help install start stop restart status logs \
        backend frontend start-backend start-frontend stop-backend stop-frontend \
        test web-build

help: ## 사용 가능한 명령 보기
	@echo "OhMyStock 서버 명령:"
	@echo "  make start            백엔드+프론트 백그라운드 실행"
	@echo "  make stop             백엔드+프론트 정지"
	@echo "  make restart          정지 후 재실행"
	@echo "  make status           실행 상태 확인"
	@echo "  make logs             백그라운드 로그 따라보기 (Ctrl-C로 종료)"
	@echo "  make backend          백엔드만 포그라운드 실행 (Ctrl-C로 종료)"
	@echo "  make frontend         프론트만 포그라운드 실행 (Ctrl-C로 종료)"
	@echo "  make start-backend    백엔드만 백그라운드 실행"
	@echo "  make start-frontend   프론트만 백그라운드 실행"
	@echo "  make stop-backend     백엔드만 정지"
	@echo "  make stop-frontend    프론트만 정지"
	@echo "  make install          의존성 설치 (uv sync + npm install)"
	@echo "  make test             pytest 실행"
	@echo "  make web-build        프론트 타입체크 + 빌드"
	@echo ""
	@echo "포트 변경: make start BACKEND_PORT=9000 FRONTEND_PORT=3000"

$(RUN_DIR):
	@mkdir -p $(RUN_DIR)

install: ## 의존성 설치
	uv sync
	cd web && npm install

# ---- 포그라운드 (개발 중 직접 보기) ----

backend: ## 백엔드 포그라운드 실행
	uv run uvicorn server.app:app --host 0.0.0.0 --port $(BACKEND_PORT)

frontend: ## 프론트 포그라운드 실행
	npm --prefix web run dev -- --port $(FRONTEND_PORT)

# ---- 백그라운드 실행 ----

start: start-backend start-frontend ## 백엔드+프론트 백그라운드 실행
	@echo "▶ 대시보드: http://localhost:$(FRONTEND_PORT)   API: http://localhost:$(BACKEND_PORT)"

start-backend: | $(RUN_DIR) ## 백엔드 백그라운드 실행
	@if [ -f $(BACKEND_PID) ] && kill -0 `cat $(BACKEND_PID)` 2>/dev/null; then \
		echo "백엔드 이미 실행 중 (pid `cat $(BACKEND_PID)`)"; \
	else \
		nohup uv run uvicorn server.app:app --host 0.0.0.0 --port $(BACKEND_PORT) > $(BACKEND_LOG) 2>&1 & echo $$! > $(BACKEND_PID); \
		echo "백엔드 시작 (pid `cat $(BACKEND_PID)`, port $(BACKEND_PORT), log $(BACKEND_LOG))"; \
	fi

start-frontend: | $(RUN_DIR) ## 프론트 백그라운드 실행
	@if [ -f $(FRONTEND_PID) ] && kill -0 `cat $(FRONTEND_PID)` 2>/dev/null; then \
		echo "프론트 이미 실행 중 (pid `cat $(FRONTEND_PID)`)"; \
	else \
		nohup npm --prefix web run dev -- --port $(FRONTEND_PORT) > $(FRONTEND_LOG) 2>&1 & echo $$! > $(FRONTEND_PID); \
		echo "프론트 시작 (pid `cat $(FRONTEND_PID)`, port $(FRONTEND_PORT), log $(FRONTEND_LOG))"; \
	fi

# ---- 정지 ----

stop: stop-frontend stop-backend ## 백엔드+프론트 정지

stop-backend: ## 백엔드 정지 (PID + 포트 기준)
	@if [ -f $(BACKEND_PID) ]; then \
		kill `cat $(BACKEND_PID)` 2>/dev/null && echo "백엔드 정지 (pid `cat $(BACKEND_PID)`)" || echo "백엔드 프로세스 없음"; \
		rm -f $(BACKEND_PID); \
	else echo "백엔드 PID 파일 없음"; fi
	@-lsof -ti tcp:$(BACKEND_PORT) | xargs kill 2>/dev/null || true

stop-frontend: ## 프론트 정지 (PID + 포트 기준)
	@if [ -f $(FRONTEND_PID) ]; then \
		kill `cat $(FRONTEND_PID)` 2>/dev/null && echo "프론트 정지 (pid `cat $(FRONTEND_PID)`)" || echo "프론트 프로세스 없음"; \
		rm -f $(FRONTEND_PID); \
	else echo "프론트 PID 파일 없음"; fi
	@-lsof -ti tcp:$(FRONTEND_PORT) | xargs kill 2>/dev/null || true

restart: stop start ## 정지 후 재실행

status: ## 실행 상태 확인
	@printf "백엔드  (port %s): " "$(BACKEND_PORT)"; \
	if [ -f $(BACKEND_PID) ] && kill -0 `cat $(BACKEND_PID)` 2>/dev/null; then echo "실행 중 (pid `cat $(BACKEND_PID)`)"; else echo "정지"; fi
	@printf "프론트  (port %s): " "$(FRONTEND_PORT)"; \
	if [ -f $(FRONTEND_PID) ] && kill -0 `cat $(FRONTEND_PID)` 2>/dev/null; then echo "실행 중 (pid `cat $(FRONTEND_PID)`)"; else echo "정지"; fi

logs: ## 백그라운드 로그 따라보기
	@touch $(BACKEND_LOG) $(FRONTEND_LOG)
	tail -f $(BACKEND_LOG) $(FRONTEND_LOG)

# ---- 기타 ----

test: ## pytest 실행
	uv run pytest -q

web-build: ## 프론트 타입체크 + 빌드
	cd web && npm run build
