# System architecture

A modular Python application shares an authoritative PostgreSQL database. SQLAlchemy models
define the schema. FastAPI routers call services; dependencies supply settings and sessions.
Engine creation is lazy; startup does not create or seed the database. CLI commands make
those mutations explicit. `create_app()` supports isolated API tests.

ETL owns source mappings, validated load transactions, audit and quarantine; analytics owns reporting views;
planning owns explainable recommendations. Modules may depend on database contracts but
must not silently change them. See ADR 001 and the README target diagram.
