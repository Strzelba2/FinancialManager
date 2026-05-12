# Local DB Backup

`session-db`, `stock-db`, and `wallet-db` already store PostgreSQL data in Docker volumes, so a regular rebuild such as `docker compose up --build` should not remove your data.

The risky command is:

```bash
make down-v CONFIRM=1
```

That removes containers together with Docker volumes.

## Backup commands

Create backups for all supported databases:

```bash
make db-backup
```

Create a backup only for `session`:

```bash
make db-backup-session
```

Create a backup only for `stock`:

```bash
make db-backup-stock
```

Create a backup only for `wallet`:

```bash
make db-backup-wallet
```

Backups are written to:

```text
backups/db/<timestamp>/
```

Each directory contains:

```text
session.sql.gz
stock.sql.gz
wallet.sql.gz
metadata.txt
```

Example real location:

```text
backups/db/20260505_101530/
```

That folder will live under your project root:

```text
/home/artur/PYTHON/FinancialManager/backups/db/<timestamp>/
```

## Restore commands

Restore the latest `session` backup:

```bash
make db-restore-session-latest
```

Restore the latest `stock` backup:

```bash
make db-restore-stock-latest
```

Restore the latest `wallet` backup:

```bash
make db-restore-wallet-latest
```

Restore all supported databases from the latest backup directory:

```bash
make db-restore-all-latest
```

Restore from a specific backup file or directory:

```bash
make db-restore-session FILE=backups/db/<timestamp>/session.sql.gz
make db-restore-stock FILE=backups/db/<timestamp>/stock.sql.gz
make db-restore-wallet FILE=backups/db/<timestamp>/wallet.sql.gz
make db-restore-all DIR=backups/db/<timestamp>
```

You can also restore from an absolute path if you prefer:

```bash
make db-restore-session FILE=/home/artur/PYTHON/FinancialManager/backups/db/<timestamp>/session.sql.gz
```

List available backup directories:

```bash
make db-list-backups
```

## Notes

- Restore temporarily stops only the currently running application services that use the selected database, then starts those same services again afterwards.
- The backup directory is ignored by Git, so your local dumps will not be committed by accident.
- `make db-list-backups` shows the available timestamp directories that you can use in restore commands.
