SHELL := /bin/bash
.DEFAULT_GOAL := help

# Ansible (and molecule) only auto-discover a collection when the source
# lives at <something>/ansible_collections/<ns>/<name>/. We materialise
# that path via a symlink shim so `make` can be run straight from the
# repo root without any prior setup.
COLLECTION_ROOT := $(CURDIR)/.collection-root
COLLECTION_LINK := $(COLLECTION_ROOT)/ansible_collections/hacode/infra

SCENARIOS := app certbot certificate docker gitlab_runner gost k3s \
             machine maria_db nginx node_js php prometheus ssh_tunnel \
             wireguard

# Note: do NOT add `test/molecule/<scenario>` here. Listing those in
# .PHONY forces Make to treat them as standalone phony targets, which
# prevents the `test/molecule/%` pattern rule below from matching. The
# files never exist on disk, so the pattern rule fires every time anyway.
PROMETHEUS_IMAGE := prom/prometheus:latest
PROMETHEUS_RULES_DIR := $(CURDIR)/roles/prometheus/files/rules
MARKDOWNLINT_IMAGE := davidanson/markdownlint-cli2:latest

.PHONY: help \
        install install/python install/collections \
        lint lint/yaml lint/ansible lint/markdown \
        test test/molecule test/prometheus-rules \
        build build/collection \
        clean clean/molecule clean/cache

## ───── help ─────────────────────────────────────────────────────────────

help:  ## Print this help
	@awk 'BEGIN { \
	        FS = ":.*## "; \
	        printf "\nUsage:\n  make <target>\n\nTargets:\n"; \
	      } \
	      /^[a-zA-Z][a-zA-Z0-9_\/.-]+:.*## / { \
	        printf "  %-30s %s\n", $$1, $$2; \
	      }' $(MAKEFILE_LIST)
	@echo
	@echo "  test/molecule/<scenario>       Run one molecule scenario; <scenario> ∈"
	@echo "                                 { $(SCENARIOS) }"

## ───── install ──────────────────────────────────────────────────────────

install: install/python install/collections  ## Install everything

install/python:  ## Install Python deps (molecule, ansible-core, linters)
	pip install -r test-requirements.txt

install/collections:  ## Install Galaxy collection deps used by the roles
	ansible-galaxy collection install -r requirements.yml

## ───── lint ─────────────────────────────────────────────────────────────

lint: lint/yaml lint/ansible lint/markdown  ## Run yamllint + ansible-lint + markdownlint

lint/yaml:  ## Run yamllint over the whole tree
	yamllint .

lint/ansible: $(COLLECTION_LINK)  ## Run ansible-lint (production profile)
	cd $(COLLECTION_LINK) && ansible-lint

lint/markdown:  ## Run markdownlint-cli2 over every Markdown file
	@docker run --rm -v "$(CURDIR):/workdir" $(MARKDOWNLINT_IMAGE) "**/*.md"

## ───── test ─────────────────────────────────────────────────────────────

test: lint test/molecule test/prometheus-rules  ## Lint + molecule + prometheus alert rule tests

test/molecule: $(addprefix test/molecule/,$(SCENARIOS))  ## Run every molecule scenario sequentially

# `make test/molecule/<scenario>` runs one scenario end-to-end
# (dependency → destroy → syntax → create → prepare → converge →
#  idempotence → verify → destroy).
test/molecule/%: $(COLLECTION_LINK)
	cd $(COLLECTION_LINK) && molecule test -s $*

test/prometheus-rules:  ## promtool check rules + unit tests for prometheus role's alerts
	@docker run --rm \
	    -v "$(PROMETHEUS_RULES_DIR):/rules:ro" \
	    --entrypoint sh $(PROMETHEUS_IMAGE) \
	    -c 'set -e; \
	        echo "==> Checking rules syntax"; \
	        promtool check rules /rules/*.yml; \
	        for f in /rules/tests/*.test.yml; do \
	          echo "==> Unit testing $$f"; \
	          promtool test rules "$$f"; \
	        done'

## ───── build ────────────────────────────────────────────────────────────

build: build/collection  ## Build everything (currently just the collection tarball)

build/collection: $(COLLECTION_LINK)  ## Build a Galaxy collection tarball into dist/
	cd $(COLLECTION_LINK) && ansible-galaxy collection build --force --output-path dist/

## ───── clean ────────────────────────────────────────────────────────────

clean: clean/molecule clean/cache  ## clean/molecule + clean/cache + dist/
	rm -rf dist

clean/molecule: $(COLLECTION_LINK)  ## `molecule destroy` across every scenario
	@cd $(COLLECTION_LINK) && for s in $(SCENARIOS); do \
	  echo ">>> molecule destroy -s $$s"; \
	  molecule destroy -s $$s || true; \
	done

clean/cache:  ## Drop the symlink shim and molecule / ansible caches
	rm -rf .collection-root .molecule .cache .facts_cache

## ───── internal ─────────────────────────────────────────────────────────

# Symlink shim: <repo>/.collection-root/ansible_collections/hacode/infra
# → <repo>. Ansible-lint and molecule then pick up cwd as a real
# collection and FQCN refs (hacode.infra.<role>) resolve.
$(COLLECTION_LINK):
	@mkdir -p $(dir $(COLLECTION_LINK))
	@ln -snf $(CURDIR) $(COLLECTION_LINK)
