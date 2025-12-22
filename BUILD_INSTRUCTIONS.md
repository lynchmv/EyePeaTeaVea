# Build Instructions

## Recommended: Using Docker Compose

Since you have a `.env` file with `CLONE_TV_LOGOS=true`, docker-compose will automatically use it:

```bash
# Build and start everything
docker-compose up -d --build

# Or just rebuild the app service
docker-compose build app
docker-compose up -d app

# To rebuild without cache (if you want a fresh clone)
docker-compose build --no-cache app
docker-compose up -d app
```

**Advantages:**
- Automatically reads `CLONE_TV_LOGOS=true` from `.env`
- Manages both app and redis services together
- Simpler workflow

## Alternative: Using Docker Build Directly

If you prefer to build the image manually:

```bash
# Build with tv-logos repository
docker build --build-arg CLONE_TV_LOGOS=true -t eyepeateavea .

# Then run with docker-compose (it will use your built image if tagged correctly)
# OR run manually with docker run
```

**Note:** If you build manually and then use `docker-compose up`, docker-compose might rebuild its own image unless you tag it correctly.

## When to Rebuild

- **After code changes**: Always rebuild
- **To update tv-logos repository**: Rebuild with `--no-cache` to get latest logos
- **After dependency changes**: Rebuild (requirements.txt, Dockerfile, etc.)

## Current Setup

Your `.env` file contains:
```
CLONE_TV_LOGOS=true
```

This means docker-compose will automatically clone the tv-logos repository during build.

## Troubleshooting

If you see the warning `⚠ TV_LOGOS_REPO_PATH set to '/app/tv-logos' but directory does not exist`:

1. Check that `.env` has `CLONE_TV_LOGOS=true`
2. Rebuild: `docker-compose build --no-cache app`
3. Restart: `docker-compose up -d app`
4. Verify: `docker exec eyepeateavea-app-1 ls -la /app/tv-logos`
