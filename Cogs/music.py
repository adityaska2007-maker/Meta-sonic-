import asyncio
import re
import yt_dlp as ytdl
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
from spotify_helper import spotify_to_queries, init_spotify
import os

YTDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0'  # ipv4
}

FFMPEG_OPTIONS = ['-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5']

ytdl_proc = ytdl.YoutubeDL(YTDL_OPTS)

def is_url(string: str) -> bool:
    return re.match(r'https?://', string) is not None

class GuildPlayer:
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.queue = asyncio.Queue()
        self.current = None
        self.voice = None
        self.play_next_song = asyncio.Event()
        self.loop_task = bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        await self.bot.wait_until_ready()
        while True:
            self.play_next_song.clear()
            track = await self.queue.get()
            self.current = track
            try:
                source = await YTDLSource.create_source(track, loop=self.bot.loop)
            except Exception as e:
                print('Error creating source:', e)
                continue
            if not self.voice or not self.voice.is_connected():
                # give short time for connection
                await asyncio.sleep(1)
                if not self.voice or not self.voice.is_connected():
                    continue
            def _after(err):
                self.bot.loop.call_soon_threadsafe(self.play_next_song.set)
                if err:
                    print('Player error:', err)
            self.voice.play(source, after=_after)
            await self.play_next_song.wait()

    async def add_tracks(self, tracks):
        for t in tracks:
            await self.queue.put(t)

    def stop(self):
        if self.voice and self.voice.is_playing():
            self.voice.stop()
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except Exception:
                break

class YTDLSource(FFmpegPCMAudio):
    def __init__(self, source_url, *, data):
        super().__init__(source_url, options=FFMPEG_OPTIONS)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url')
        self.thumbnail = data.get('thumbnail')

    @classmethod
    async def create_source(cls, search: str, *, loop):
        data = await loop.run_in_executor(None, lambda: ytdl_proc.extract_info(search, download=False))
        if not data:
            raise RuntimeError('yt-dlp returned no data')
        if 'entries' in data and data['entries']:
            data = data['entries'][0]
        # prefer direct url if provided
        if 'url' in data and data.get('url'):
            stream_url = data['url']
        else:
            formats = data.get('formats', [])
            stream_url = None
            for f in reversed(formats):
                if f.get('acodec') != 'none' and f.get('url'):
                    stream_url = f.get('url')
                    break
            if not stream_url:
                raise RuntimeError('No stream url found in extractor data')
        return cls(stream_url, data=data)

class Music(commands.Cog):
    """Music cog for Meta Music"""
    COLOR = 0x1DB954

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players = {}
        init_spotify()

    def get_player(self, ctx):
        guild_id = ctx.guild.id
        player = self.players.get(guild_id)
        if not player:
            player = GuildPlayer(self.bot, ctx.guild)
            self.players[guild_id] = player
        return player

    async def ensure_voice(self, ctx, player):
        if not ctx.author.voice:
            await ctx.send(embed=self.error_embed('You must be connected to a voice channel.'))
            return False
        if not player.voice or not player.voice.is_connected():
            try:
                player.voice = await ctx.author.voice.channel.connect()
            except Exception as e:
                await ctx.send(embed=self.error_embed(f'Could not connect to voice channel: {e}'))
                return False
        return True

    def success_embed(self, title, description=None):
        e = discord.Embed(title=title, description=description or '\u200b', color=self.COLOR)
        return e

    def error_embed(self, description):
        e = discord.Embed(title='Error', description=description, color=0xE02424)
        return e

    @commands.command(name='join')
    async def join(self, ctx):
        if not ctx.author.voice:
            return await ctx.send(embed=self.error_embed('You are not connected to a voice channel.'))
        channel = ctx.author.voice.channel
        player = self.get_player(ctx)
        if player.voice and player.voice.is_connected():
            await player.voice.move_to(channel)
            return await ctx.send(embed=self.success_embed('Moved', f'Moved to **{channel.name}**'))
        player.voice = await channel.connect()
        await ctx.send(embed=self.success_embed('Joined', f'Joined **{channel.name}**'))

    @commands.command(name='leave')
    async def leave(self, ctx):
        player = self.get_player(ctx)
        if player.voice:
            await player.voice.disconnect()
            player.voice = None
            await ctx.send(embed=self.success_embed('Disconnected', 'Left the voice channel.'))
        else:
            await ctx.send(embed=self.error_embed('Bot is not in a voice channel.'))

    @commands.command(name='play')
    async def play(self, ctx, *, query: str):
        player = self.get_player(ctx)
        ok = await self.ensure_voice(ctx, player)
        if not ok:
            return
        queries = spotify_to_queries(query)
        await ctx.send(embed=self.success_embed('Queued', f'Queued {len(queries)} item(s).'))
        await player.add_tracks(queries)
        # send now-playing when queue contains the item and if nothing is playing it will trigger in player loop
        # we will also try to show the next item as now playing right away if nothing is playing.
        if player.current is None:
            # give the player loop a moment to pick it up
            await asyncio.sleep(1)
            if player.current:
                await self.send_now_playing(ctx, player.current, ctx.author)

    async def send_now_playing(self, ctx, track, requester):
        # track may be a search string or a YTDL data dict or object; try to get useful info.
        try:
            # if source data already prepared:
            if isinstance(track, str):
                # attempt to extract metadata quickly
                data = ytdl_proc.extract_info(track, download=False)
                if 'entries' in data:
                    data = data['entries'][0]
            else:
                data = getattr(track, 'data', track)
        except Exception:
            data = None
        title = None
        url = None
        thumb = None
        if data:
            title = data.get('title') or data.get('webpage_title') or str(track)
            url = data.get('webpage_url') or data.get('url')
            thumb = data.get('thumbnail')
        if not title:
            title = str(track)
        embed = discord.Embed(title=f'Now Playing — {title}', url=url or discord.Embed.Empty, color=self.COLOR)
        if thumb:
            embed.set_thumbnail(url=thumb)
        embed.add_field(name='Requested by', value=getattr(requester, 'display_name', str(requester)), inline=True)
        await ctx.send(embed=embed)

    @commands.command(name='skip')
    async def skip(self, ctx):
        player = self.get_player(ctx)
        if player.voice and player.voice.is_playing():
            player.voice.stop()
            await ctx.send(embed=self.success_embed('Skipped', 'Skipped the current track.'))
        else:
            await ctx.send(embed=self.error_embed('Nothing is playing.'))

    @commands.command(name='pause')
    async def pause(self, ctx):
        player = self.get_player(ctx)
        if player.voice and player.voice.is_playing():
            player.voice.pause()
            await ctx.send(embed=self.success_embed('Paused', 'Playback paused.'))
        else:
            await ctx.send(embed=self.error_embed('Nothing is playing.'))

    @commands.command(name='resume')
    async def resume(self, ctx):
        player = self.get_player(ctx)
        if player.voice and player.voice.is_paused():
            player.voice.resume()
            await ctx.send(embed=self.success_embed('Resumed', 'Playback resumed.'))
        else:
            await ctx.send(embed=self.error_embed('Nothing is paused.'))

    @commands.command(name='stop')
    async def stop(self, ctx):
        player = self.get_player(ctx)
        player.stop()
        await ctx.send(embed=self.success_embed('Stopped', 'Stopped and cleared the queue.'))

    @commands.command(name='np')
    async def now_playing(self, ctx):
        player = self.get_player(ctx)
        if player.current:
            # try to display properly
            try:
                data = getattr(player.current, 'data', player.current)
                title = data.get('title') if isinstance(data, dict) else str(player.current)
            except Exception:
                title = str(player.current)
            await ctx.send(embed=self.success_embed('Now Playing', title))
        else:
            await ctx.send(embed=self.error_embed('Nothing is currently playing.'))

    @commands.command(name='queue')
    async def show_queue(self, ctx):
        player = self.get_player(ctx)
        q = list(player.queue._queue)
        if not q:
            return await ctx.send(embed=self.success_embed('Queue', 'Queue is empty.'))
        out = '\n'.join(f'{i+1}. {item}' for i,item in enumerate(q[:20]))
        await ctx.send(embed=self.success_embed('Queue', out))

    @commands.command(name='help')
    async def help(self, ctx):
        embed = discord.Embed(title='🎶 Meta Music — Help Panel', description='Prefix: `+` or mention the bot (e.g. @Meta Music play)\n\u200b', color=self.COLOR)
        embed.add_field(name='+join', value='Join your voice channel', inline=False)
        embed.add_field(name='+leave', value='Leave voice channel', inline=False)
        embed.add_field(name='+play <query|url|spotify_url>', value='Play or queue a track/playlist/spotify. Auto-joins your VC if needed.', inline=False)
        embed.add_field(name='+skip', value='Skip current track', inline=False)
        embed.add_field(name='+pause / +resume', value='Pause/resume playback', inline=False)
        embed.add_field(name='+stop', value='Stop and clear queue', inline=False)
        embed.add_field(name='+np', value='Show now playing', inline=False)
        embed.add_field(name='+queue', value='Show queue', inline=False)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
