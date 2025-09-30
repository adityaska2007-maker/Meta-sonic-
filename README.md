# Meta Music — Discord Music Bot (Python 3.11)

This is a ready-to-run Discord music bot project aimed at Python 3.11 and Pterodactyl servers.
It uses `discord.py` (2.x), `yt-dlp` for streaming YouTube, and optional Spotify lookups via `spotipy`.

## Quick setup (Pterodactyl)
1. Upload and extract this repository into `/home/container/`.
2. Rename `config.example.env` to `.env` and fill in your `DISCORD_TOKEN` and optionally Spotify creds.
3. Install dependencies (in the server console):
   ```bash
   python -m pip install -r requirements.txt
   ```
4. Ensure `ffmpeg` is available on the host (ask your provider or use a custom egg).
5. Start the server — default startup command should be `python main.py`.

Commands (prefix: `+` or mention the bot)
- `+help` — show the help embed
- `+play <query|url|spotify_url>` — plays or queues and auto-joins your VC
- `+skip` / `+pause` / `+resume` / `+stop` / `+join` / `+leave` / `+np` / `+queue`

If something fails, paste the server console traceback here and I will help fix it.
