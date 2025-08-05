# --- Stage 1: Builder ---
# This stage installs dependencies into a virtual environment.
FROM python:3.12-slim as builder

WORKDIR /app

# Install uv, the fast Python package installer
RUN pip install uv

# Copy only the files needed to install dependencies
COPY pyproject.toml ./

# Install dependencies into a virtual environment at /app/.venv
RUN uv venv && . .venv/bin/activate && uv sync

# --- Stage 2: Final Image ---
# This stage creates the final, lightweight image for running the application.
FROM python:3.12-slim

WORKDIR /app

# Create a non-root user to run the application for better security
RUN useradd --create-home --shell /bin/bash appuser

# Copy the virtual environment with all dependencies from the builder stage
COPY --from=builder /app/.venv ./.venv

# Set the PATH to include the virtual environment's bin directory
ENV PATH="/app/.venv/bin:$PATH"

# Copy the application source code
COPY ./stremio_addon ./stremio_addon
COPY ./stremio_addon/static ./stremio_addon/static

# --- Start of HTTPS Changes ---
# Copy your SSL certificate and key into the container
COPY ./mediafusion.lynuxss.com.pem /app/cert.pem
COPY ./mediafusion.lynuxss.com-key.pem /app/key.pem

# Ensure the appuser can read the certificate files
RUN chown appuser:appuser /app/cert.pem /app/key.pem
# --- End of HTTPS Changes ---

# Change ownership of the app directory to the non-root user
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Expose the port the application will run on
EXPOSE 8000

# --- Updated CMD to enable HTTPS ---
# Command to run the application using Gunicorn with SSL enabled
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", \
     "stremio_addon.api.main:app", \
     "--bind", "0.0.0.0:8000", \
     "--certfile=/app/cert.pem", \
     "--keyfile=/app/key.pem"]

