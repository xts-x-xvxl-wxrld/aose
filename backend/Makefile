.PHONY: api-test api-test-auth api-test-build

api-test-build:
	docker compose -f ../docker-compose.yml build api-test

api-test:
	docker compose -f ../docker-compose.yml run --rm --no-deps --build api-test pytest -q

api-test-auth:
	docker compose -f ../docker-compose.yml run --rm --no-deps --build api-test pytest -q tests/test_identity_api.py tests/test_zitadel_auth.py
