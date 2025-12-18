# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install git for cloning tv-logos repository (optional)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

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
        echo "tv-logos repository cloned successfully"; \
    else \
        echo "Skipping tv-logos repository clone (set CLONE_TV_LOGOS=true to enable)"; \
    fi

# Expose the port the app runs on
EXPOSE 8020

# Define environment variables
ENV PYTHONUNBUFFERED 1

# Set TV_LOGOS_REPO_PATH if repository was cloned
# The application will check if the directory exists, so it's safe to set this
# Users can override this via environment variable at runtime if needed
ENV TV_LOGOS_REPO_PATH=/app/tv-logos

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8020"]