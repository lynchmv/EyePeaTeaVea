# TV Logos Repository Scripts

These scripts help manage a local clone of the [tv-logos](https://github.com/tv-logo/tv-logos) repository to avoid GitHub rate limiting when fetching channel logos.

## Why Use a Local Repository?

- **No rate limiting**: Avoids 429 (Too Many Requests) errors from GitHub
- **Faster access**: Local filesystem is faster than HTTP requests
- **More reliable**: No network dependency for image serving
- **Better control**: Update the repository on your own schedule

## Setup

### Option 1: Clone During Docker Build (Recommended)

Build the Docker image with the repository included:

```bash
docker build --build-arg CLONE_TV_LOGOS=true -t eyepeateavea .
```

The repository will be cloned to `/app/tv-logos` inside the container, and `TV_LOGOS_REPO_PATH` will be automatically set.

### Option 2: Clone Manually

1. Clone the repository:
```bash
./scripts/clone_tv_logos.sh
```

Or manually:
```bash
git clone --depth 1 https://github.com/tv-logo/tv-logos.git ./tv-logos
```

2. Set the environment variable:
```bash
export TV_LOGOS_REPO_PATH=./tv-logos
```

Or add to your `.env` file:
```
TV_LOGOS_REPO_PATH=./tv-logos
```

### Option 3: Use Existing Clone

If you already have the repository cloned elsewhere:

```bash
export TV_LOGOS_REPO_PATH=/path/to/tv-logos
```

## Updating the Repository

To update the local repository with the latest logos:

```bash
./scripts/update_tv_logos.sh
```

Or manually:
```bash
cd tv-logos
git pull origin main
```

## How It Works

When `TV_LOGOS_REPO_PATH` is set:

1. The application checks if an image URL matches the GitHub tv-logos pattern
2. If it matches, it converts the URL to a local file path
3. It checks if the file exists locally
4. If found, it serves from the local filesystem (fast, no rate limits)
5. If not found, it falls back to HTTP fetch with retry logic

This hybrid approach gives you the best of both worlds:
- Fast local access when available
- Graceful fallback to HTTP when needed

## Repository Size

The repository is approximately 450MB. Make sure you have sufficient disk space.

## Docker Compose Example

```yaml
services:
  app:
    build:
      context: .
      args:
        CLONE_TV_LOGOS: "true"
    environment:
      - TV_LOGOS_REPO_PATH=/app/tv-logos
      # ... other environment variables
```

## Notes

- The repository is cloned with `--depth 1` to save space (shallow clone)
- Images are still cached in Redis for performance
- The local repository is checked first, then falls back to HTTP
- If `TV_LOGOS_REPO_PATH` is not set, the application works normally with HTTP fetching only
