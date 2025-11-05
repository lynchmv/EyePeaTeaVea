# EyePeaTeaVea
Stremio addon to curate m3u playlists from around the globe, supporting multiple user configurations via a unique `secret_str`.


# Configuration
This addon uses a `secret_str` to manage individual user configurations, allowing for personalized M3U sources. Instead of configuring global environment variables for sources, each user generates their own `secret_str`.

## Initial Setup

1.  **Redis URL**: Ensure your `.env` file contains the `REDIS_URL`:
    ```
    REDIS_URL="redis://localhost:6379/0"
    ```
    (Adjust the Redis URL as per your setup, especially if running in Docker.)

2.  **Start the Addon**: Run the FastAPI application.

3.  **Configure User Settings**: Access the `/configure` endpoint to set up your M3U sources. You can do this using a tool like `curl` or a web browser (for a simple GET request, though POST is recommended for security).

    Example `curl` command to configure:
    ```bash
    curl -X POST "http://localhost:8020/configure" \
         -H "Content-Type: application/json" \
         -d '{
               "m3u_sources": ["https://example.com/my_playlist.m3u"],
               "parser_schedule_crontab": "0 */6 * * *",
               "host_url": "http://your-public-addon-url.com",
               "addon_password": "mysecurepassword"
             }'
    ```
    This will return a `secret_str` which is unique to your configuration.

## Using the Addon

Once you have your `secret_str`, you will use it in your Stremio addon URL. The base URL for your addon will be `http://your-public-addon-url.com/{your_secret_str}`.

For example, if your `host_url` is `http://localhost:8020` and your generated `secret_str` is `abc123xyz`:

*   **Manifest URL**: `http://localhost:8020/abc123xyz/manifest.json`

If you set an `addon_password` during configuration, the Stremio manifest will indicate `configurationRequired: True`, and you will need to provide the password when adding the addon in Stremio.
