SHELL := /bin/sh
.DEFAULT_GOAL := help
PROJECT_ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3
DEV_PYTHON ?= $(PROJECT_ROOT).venv/bin/python

.PHONY: help setup dev api web check contracts evolution-smoke delegation-smoke workbench-smoke agent-smoke context-setup context-smoke judgment-setup judgment-smoke browser-install e2e clean clean-preview clean-cache clean-build clean-empty

help:
	@printf '%s\n' \
	  'make setup          安装锁定的 Python 与浏览器界面依赖' \
	  'make dev            启动本机前后端任务工作台' \
	  'make evolution-smoke 真实 Skill 隔离验收（使用 API 额度）' \
	  'make delegation-smoke 真实单/多 Agent 成对验收（使用 API 额度）' \
	  'make workbench-smoke 显式运行真实浏览器任务与重启验收（使用 API 额度）' \
	  'make api / web      单独启动后端 / 前端' \
	  'make check          运行代码、类型、契约、边界和构建检查' \
	  'make contracts      重新导出 API 与前端类型' \
	  'make agent-smoke    显式运行真实 Agent 验收（使用 API 额度）' \
	  'make context-setup / context-smoke 下载固定 tokenizer / 本地计数验收' \
	  'make browser-install 安装浏览器验收所需 Chromium' \
	  'make e2e            启动临时服务并运行 Python 浏览器验收' \
	  'make clean          清除缓存、临时编译产物和所有空目录' \
	  'make clean-preview  预览清理数量，不删除文件' \
	  'make clean-cache    只清理工具缓存和 Python 字节码' \
	  'make clean-build    只清理构建产物和打包元数据' \
	  'make clean-empty    只递归删除空目录'

setup:
	@$(PYTHON) "$(PROJECT_ROOT)scripts/setup.py"

dev:
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/dev.py" all

api:
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/dev.py" api

web:
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/dev.py" web

check:
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/dev.py" check

contracts:
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/dev.py" contracts

browser-install:
	@"$(DEV_PYTHON)" -m playwright install chromium

e2e:
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/dev.py" e2e

clean:
	@$(PYTHON) "$(PROJECT_ROOT)scripts/clean.py" --scope all

clean-preview:
	@$(PYTHON) "$(PROJECT_ROOT)scripts/clean.py" --scope all --dry-run

clean-cache:
	@$(PYTHON) "$(PROJECT_ROOT)scripts/clean.py" --scope cache

clean-build:
	@$(PYTHON) "$(PROJECT_ROOT)scripts/clean.py" --scope build

clean-empty:
	@$(PYTHON) "$(PROJECT_ROOT)scripts/clean.py" --scope empty

judgment-setup:
	@uv sync --extra judgment
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/download_laya.py"

judgment-smoke:
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/judgment_smoke.py"

context-setup:
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/download_context_tokenizers.py"

context-smoke:
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/context_smoke.py"

agent-smoke:
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/agent_smoke.py"

workbench-smoke:
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/workbench_smoke.py"

delegation-smoke:
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/delegation_smoke.py"

evolution-smoke:
	@"$(DEV_PYTHON)" "$(PROJECT_ROOT)scripts/evolution_smoke.py"
