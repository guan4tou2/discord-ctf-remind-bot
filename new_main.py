"""
Discord bot for CTF competition management and reminders.
"""

import os
import discord
from discord.ext import commands
from dotenv import load_dotenv, find_dotenv

from database import Database

# Load environment variables
load_dotenv(find_dotenv(), override=True)
TOKEN = os.getenv("DISCORD_TOKEN")

# Initialize bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize database
db = Database()


@bot.event
async def on_ready():
    """Called when the bot is ready"""
    print(f"{bot.user} has connected to Discord!")

    # Load cogs
    await load_cogs()

async def load_cogs():
    """Load all cogs"""
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                print(f"Loaded cog: {filename[:-3]}")
            except Exception as e:
                print(f"Failed to load cog {filename[:-3]}: {str(e)}")


@bot.event
async def on_guild_join(guild):
    """Called when the bot joins a new server"""
    # Create database entries for the new server
    db.add_guild(str(guild.id))


@bot.event
async def on_guild_remove(guild):
    """Called when the bot is removed from a server"""
    # Clean up database entries for the server
    db.remove_guild(str(guild.id))


@bot.event
async def on_command_error(ctx, error):
    """Global error handler"""
    if isinstance(error, commands.errors.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command")
    elif isinstance(error, commands.errors.MissingRequiredArgument):
        await ctx.send("❌ Missing required argument. Please check command usage")
    elif isinstance(error, commands.errors.CommandNotFound):
        await ctx.send("❌ Command not found")
    else:
        print(f"Error: {str(error)}")
        await ctx.send(f"❌ An error occurred: {str(error)}")


def main():
    """Main entry point"""
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
