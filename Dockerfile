# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install git, fonts, CA certificates, and SVG rendering libraries
# SVG libraries (libcairo2-dev, libpango1.0-dev) are required for cairosvg
# Note: libgdk-pixbuf2.0-dev is not available in Debian Trixie, but cairosvg works without it
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    fonts-dejavu-core \
    fonts-liberation \
    libcairo2-dev \
    libpango1.0-dev \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install any needed packages specified in requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Optional: Clone tv-logos repository if CLONE_TV_LOGOS build arg is set
# Usage: docker build --build-arg CLONE_TV_LOGOS=true -t eyepeateavea .
ARG CLONE_TV_LOGOS=false
RUN if [ "$CLONE_TV_LOGOS" = "true" ]; then \
        echo "Cloning tv-logos repository..."; \
        git clone --depth 1 https://github.com/tv-logo/tv-logos.git /app/tv-logos && \
        echo "tv-logos repository cloned successfully" && \
        ls -la /app/tv-logos | head -20 && \
        echo "Verifying repository structure..." && \
        test -d /app/tv-logos/countries && echo "✓ Repository structure verified" || echo "✗ Warning: Repository structure incomplete"; \
    else \
        echo "Skipping tv-logos repository clone (set CLONE_TV_LOGOS=true to enable)"; \
    fi

# Expose the port the app runs on
EXPOSE 8020

# Define environment variables
ENV PYTHONUNBUFFERED 1

# Set TV_LOGOS_REPO_PATH unconditionally - the application will check if the directory exists
# Users can override this via environment variable at runtime if needed
ENV TV_LOGOS_REPO_PATH=/app/tv-logos

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8020"]