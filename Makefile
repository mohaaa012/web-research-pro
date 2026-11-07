.PHONY: help dev test package install validate clean

help:
	@echo "make dev       - install development dependencies + Chromium"
	@echo "make test      - run the test suite"
	@echo "make validate  - validate the Claude Code plugin and marketplace manifests"
	@echo "make package   - build dist/web-research-pro.skill"
	@echo "make install   - install the skill into ~/.claude/skills"
	@echo "make clean     - remove build and cache files"

dev:
	python3 -m pip install -r requirements-dev.txt
	python3 -m playwright install chromium

test:
	python3 -m pytest -q

validate:
	claude plugin validate .

package:
	python3 tools/package_skill.py

install:
	bash install.sh

clean:
	rm -rf dist .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
