# Project Overview

This project, named "EyePeaTeaVea," is a Stremio addon designed to curate and provide access to M3U playlists. It is built with Python, using the FastAPI framework for the web server and Redis for data storage. The addon allows for multi-user configurations through a unique `secret_str` for each user, enabling personalized M3U sources.

The application parses M3U files, extracts channel information, and presents it through a Stremio-compatible API. It also includes features for image processing to generate posters and logos for the channels. The project is set up to be deployed using Docker, with a `docker-compose.yml` file orchestrating the application and a Redis container.

# Building and Running

## Running with Docker

The most straightforward way to run the project is by using Docker Compose:

```bash
docker-compose up -d
```

This will build the Docker image for the application and start both the `app` and `redis` services. The application will be accessible at `http://localhost:8020`.

## Running Locally

To run the application locally for development:

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Set up Environment:**
    Create a `.env` file in the project root and add the following:
    ```
    REDIS_URL="redis://localhost:6379/0"
    ```

3.  **Run the Application:**
    ```bash
    uvicorn src.main:app --host 0.0.0.0 --port 8020 --reload
    ```

## Testing

The project uses `pytest` for testing. To run the tests:

```bash
pytest
```

# Development Conventions

*   **Code Style:** The code follows the standard Python PEP 8 style guidelines.
*   **API:** The project uses a RESTful API built with FastAPI.
*   **Dependencies:** Python dependencies are managed with `pip` and are listed in the `requirements.txt` file.
*   **Configuration:** Application configuration is managed through environment variables and a `.env` file. User-specific configurations are stored in Redis.
*   **Asynchronous Code:** The application makes extensive use of Python's `asyncio` for asynchronous operations, particularly for handling HTTP requests and I/O.
# Security Considerations

## `secret_str` in URL

The `secret_str` is currently passed in the URL, which is not ideal from a security perspective. This is because the URL can be logged in server logs, browser history, and other places.

While this is the standard practice for Stremio addons, it is a potential security risk. A better approach would be to pass the `secret_str` in a request header, such as `X-Secret-Str`. However, this would require a significant change to the addon's architecture and might break compatibility with Stremio.

This is a known issue and a potential area for future improvement.
