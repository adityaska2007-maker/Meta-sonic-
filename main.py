import os
import logging
from dotenv import load_dotenv
import discord
from discord.ext import commands

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
PREFIX = os.getenv('PREFIX', '+')

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('meta-music')

def get_prefix(bot, message):
    return commands.when_mentioned_or(PREFIX)(bot, message)

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)

@bot.event
async def on_ready():
    try:
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=f"+help | Meta Music"))
    except Exception:
        pass
    logger.info(f"Meta Music is online! Logged in as {bot.user} (ID: {bot.user.id})")

async def setup_hook():
    try:
        await bot.load_extension('cogs.music')
        logger.info("Loaded cogs.music successfully")
    except Exception as e:
        logger.exception("Failed to load cogs.music: %s", e)

bot.setup_hook = setup_hook

if __name__ == '__main__':
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN not set in environment (.env)")
    bot.run(TOKEN)
  
