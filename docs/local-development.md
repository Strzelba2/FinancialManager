# Local Development

This repository is designed to run fully locally with Docker Compose.

## Normal workflow

Start or rebuild the full local stack:

```bash
make build
```

Run the local Robot smoke tests after startup:

```bash
make smoke-test
```

Run browser-level Robot functional tests for `next-ui`:

```bash
make functional-test
```

Run component and integration suites from the root `tests/` tree:

```bash
make component-test
make integration-test
```

Run service unit tests collected from each service `tests/` folder:

```bash
make unit-test
```

This includes Python backend unit suites and the `next-ui` frontend unit suite.

Run unit coverage reports and quality checks:

```bash
make coverage-unit
make quality-test
```

`make coverage-unit` enforces the current backend coverage gates and generates the
reported `next-ui` Vitest coverage baseline.

Generate and serve an aggregated Allure report:

```bash
make allure-report
make allure-up
```

Run the entire test stack and open the final Allure report in one command:

```bash
make test-all
```

Start the stack without rebuilding images:

```bash
make up
```

Recreate only one service:

```bash
make recreate-session
make recreate-wallet
make recreate-stock
make recreate-next-ui
```

All `make` targets that need Docker Compose automatically ensure the `financial_manager` Docker network exists first.

## Migrations

`session-auth`, `wallet`, and `stock` already run migrations on container startup.

Manual migration commands are still available when you want them explicitly:

```bash
make session-migrate
make wallet-migrate
make stock-migrate
```

Create Django migrations for `session-auth`:

```bash
make session-makemigrations
```

Legacy aliases still work:

```bash
make migrate
make makemigrations
```

## Common local URLs

- `http://wallet.localhost:8081`
- `http://next.localhost:8081`
- `http://session-auth.localhost:8081/admin`
- `http://localhost:5050` for pgAdmin
- `http://localhost:8025` for Mailpit

## Stopping the stack

Normal stop:

```bash
make down
```

Destructive stop that also removes Docker volumes:

```bash
make down-v CONFIRM=1
```

If you care about your local data, create a backup first:

```bash
make db-backup
```

Backup and restore commands are described in [local-db-backup.md](./local-db-backup.md).

The full test layout and conventions are documented in [../tests/README.md](../tests/README.md)
and [testing-strategy.md](./testing-strategy.md).
