#!/bin/sh
set -eu

TEST_DB="${POSTGRES_TEST_DB:-agentic_ose_test}"

if [ -z "${TEST_DB}" ]; then
  exit 0
fi

EXISTS="$(psql -U "${POSTGRES_USER}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${TEST_DB}'")"

if [ "${EXISTS}" != "1" ]; then
  psql -U "${POSTGRES_USER}" -d postgres -c "CREATE DATABASE \"${TEST_DB}\""
fi
