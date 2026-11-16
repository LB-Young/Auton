SHELL := /bin/sh
.DEFAULT_GOAL := help
PROJECT_ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3

.PHONY: help clean clean-preview clean-cache clean-build clean-empty

help:
	@printf '%s\n' \
	  'make clean          清除缓存、临时编译产物和所有空目录' \
	  'make clean-preview  预览清理数量，不删除文件' \
	  'make clean-cache    只清理工具缓存和 Python 字节码' \
	  'make clean-build    只清理构建产物和打包元数据' \
	  'make clean-empty    只递归删除空目录'

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
