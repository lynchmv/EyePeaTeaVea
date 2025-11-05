import requests
import json

# Replace with your actual domain
HOST = "https://stremio-dev.lynuxss.com"
CONFIGURE_URL = f"{HOST}/configure"

# Example configuration data
# You should replace these with your actual M3U and EPG sources,
# desired cron schedule, and an optional addon password.
config_data = {
    "m3u_sources": ["https://raw.githubusercontent.com/BuddyChewChew/buddylive/refs/heads/main/buddylive_v1.m3u"],
    "epg_sources": ["https://raw.githubusercontent.com/BuddyChewChew/buddylive/refs/heads/main/en/videoall.xml"],
    "parser_schedule_crontab": "0 */6 * * *",
    "host_url": HOST,
    "addon_password": "12DevServer3!"
}

headers = {
    "Content-Type": "application/json"
}

try:
    response = requests.post(CONFIGURE_URL, headers=headers, data=json.dumps(config_data))
    response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

    result = response.json()
    secret_str = result.get("secret_str")
    message = result.get("message")

    if secret_str:
        print(f"Successfully configured addon!")
        print(f"Secret String: {secret_str}")
        print(f"Message: {message}")
        print(f"\nUse this secret_str in your Stremio addon URL: {HOST}/{secret_str}/manifest.json")
    else:
        print(f"Configuration successful, but secret_str not found in response. Message: {message}")

except requests.exceptions.RequestException as e:
    print(f"An error occurred during the request: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"Response status code: {e.response.status_code}")
        print(f"Response body: {e.response.text}")
except json.JSONDecodeError:
    print(f"Failed to decode JSON response. Response content: {response.text}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
