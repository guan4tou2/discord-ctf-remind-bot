"""
Utility commands for the bot.
"""

import time

import discord
from discord.ext import commands


class Utils(commands.Cog):
    """Utility commands"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def ping(self, ctx):
        """Check bot's latency
        Usage:
        !ping - Show bot's latency
        """
        # Get start time
        start_time = time.time()

        # Send initial message
        message = await ctx.send("🏓 Pinging...")

        # Calculate latencies
        end_time = time.time()
        response_time = round((end_time - start_time) * 1000)  # Convert to ms
        websocket_latency = round(self.bot.latency * 1000)  # Convert to ms

        # Create embed
        embed = discord.Embed(title="🏓 Pong!", color=discord.Color.green())
        embed.add_field(
            name="Bot Latency", value=f"```{response_time}ms```", inline=True
        )
        embed.add_field(
            name="WebSocket Latency", value=f"```{websocket_latency}ms```", inline=True
        )

        # Edit message with embed
        await message.edit(content=None, embed=embed)


async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(Utils(bot))
