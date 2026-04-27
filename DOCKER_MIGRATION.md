# Docker Deployment And DB Migration

## 1. Build and start infrastructure

```bash
docker compose up -d postgres redis
docker compose run --rm migrate
```

Then start app services:

```bash
docker compose up -d web worker worker_similarity
```

Services:
- `web`: Flask app via Gunicorn on `http://localhost:8084`
- `worker`: Celery worker for main checks queue (`paste_queue`)
- `worker_similarity`: dedicated Celery worker for anti-plagiarism queue (`similarity_queue`, concurrency = 1)
- `postgres`: PostgreSQL 16 (`localhost:5433` -> container `5432`)
- `redis`: Redis 7

## 2. Migrate current DB into Docker Postgres

Before migration, make a backup of current DB.

### Example A: current DB is SQLite (`database.sqlite`)

```bash
python3 scripts/migrate_db.py \
  --source sqlite:///database.sqlite \
  --target postgresql+psycopg2://postgres:postgres@localhost:5433/geekpaste
```

### Example B: current DB is external Postgres

```bash
python3 scripts/migrate_db.py \
  --source postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME \
  --target postgresql+psycopg2://postgres:postgres@localhost:5433/geekpaste
```

By default the script truncates target tables before copy.
To append data instead of truncating, pass:

```bash
python3 scripts/migrate_db.py --no-truncate ...
```

## 3. Verify

```bash
docker compose logs -f web worker worker_similarity
```

Open `http://localhost:8084`.

## Notes

- App containers use Docker socket (`/var/run/docker.sock`) to run code-check containers.
- In container mode, runner uses `DOCKER_TRANSFER_MODE=cp` (files are copied with `docker cp`).
- ZIP originals are stored in Docker volume `zip_archives_data`.
