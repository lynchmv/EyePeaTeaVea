# EyePeaTeaVea
Stremio addon to curate m3u playlists and EPG from around the globe

The name of the project is EyePeaTeaVea and we need to utilize stremio-dev.lynuxss.com as the URL
for the manifest. The addon will parse and store m3u playlists (on a schedule) as well as parse and 
store (refresh every 6 hours) EPG data. This data will then be combined into the Stremio 'Discover' as
'IPTV' > 'Channels' > {groups}. The {groups} will be created via the 'group-title' in the m3u file.

# Configuration
Configuration is handled via your `.env` file, containing the following:

## A comma-separated list of M3U URLs
COMBINED_PLAYLIST_SOURCES="https://url1/playlist.m3u,https://url2/playlist.m3u"

## A comma-separated list of EPG URLs
COMBINED_EPG_SOURCES="https://url3/epg.xml,https://url4/epg2.xml.gz"

## Cron schedule to run the parser (e.g., every 4 hours)
PARSER_SCHEDULE_CRONTAB="0 */4 * * *"

## The public URL of your addon
HOST_URL="http://your-server-ip:8000"

REDIS_URL="redis://redis:6379"

## A secret password to protect your addon
ADDON_PASSWORD="your-secret-password"
