# Docker Guide (Step by Step)

## 1. Prerequisites
- Install Docker Desktop.
- Ensure Docker is running.

## 2. Build images
```bash
docker compose build
```

## 3. Start only infra (Postgres + Redis)
```bash
docker compose up -d db redis
```

## 4. Run migrations
```bash
docker compose --profile tools run --rm migrate
```

## 5. Seed initial data
```bash
docker compose run --rm api python -m scripts.seed
```

## 6. Start API + worker
```bash
docker compose up -d api worker
```

## 7. Verify services
- API docs: `http://localhost:8000/docs`
- Admin: `http://localhost:8000/admin`

## 8. Useful commands
- View logs:
```bash
docker compose logs -f api
docker compose logs -f worker
```
- Open shell in API container:
```bash
docker compose exec api sh
```
- Stop all services:
```bash
docker compose down
```
- Stop and remove volumes (fresh DB):
```bash
docker compose down -v
```

## 9. Notes
- Docker overrides DB/Redis URLs internally to use service names (`db`, `redis`).
- Uploaded files are persisted on host in `./media` and `./storage`.
- OCR endpoint works in Docker because `tesseract-ocr` is installed in image.
