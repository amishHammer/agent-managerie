# SPDX-License-Identifier: AGPL-3.0-only

.PHONY: test
test:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python python3 -m unittest discover -s tests

.PHONY: compose-up
compose-up:
	docker compose up --build
