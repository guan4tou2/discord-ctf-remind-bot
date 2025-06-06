"""
Bot settings management commands.
"""

import discord
from discord.ext import commands
import pytz
from datetime import datetime
from database import Database


class Settings(commands.Cog):
    """Bot settings management commands"""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setnotify(self, ctx, channel: discord.TextChannel = None):
        """Set notification channel for CTF events
        Usage:
        !setnotify - View current notification channel
        !setnotify #channel - Set notification channel
        """
        if channel is None:
            # View current channel
            channel_id = self.db.get_notification_channel(str(ctx.guild.id))
            if channel_id:
                try:
                    channel = ctx.guild.get_channel(int(channel_id))
                    if channel:
                        await ctx.send(
                            f"📢 Current notification channel: {channel.mention}"
                        )
                    else:
                        await ctx.send(
                            "❌ Notification channel not found, please set a new one"
                        )
                except Exception:
                    await ctx.send("❌ Error getting notification channel")
            else:
                await ctx.send(
                    "❌ No notification channel set, please use `!setnotify #channel` to set one"
                )
            return

        # Set new channel
        if self.db.set_notification_channel(str(ctx.guild.id), str(channel.id)):
            await ctx.send(f"✅ Notification channel set to {channel.mention}")
        else:
            await ctx.send("❌ Error setting notification channel")

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def setctftime(self, ctx, team_id: str = None):
        """Set or view CTFtime team ID
        Usage:
        !setctftime - View current CTFtime team ID
        !setctftime <team_id> - Set CTFtime team ID and import planned events
        """
        if team_id is None:
            # View current team ID
            current_team_id = self.db.get_ctftime_team_id(str(ctx.guild.id))
            if current_team_id:
                embed = discord.Embed(
                    title="CTFtime Team ID",
                    description=f"Current team ID: `{current_team_id}`",
                    color=discord.Color.blue(),
                )
                embed.add_field(
                    name="Team URL",
                    value=f"https://ctftime.org/team/{current_team_id}",
                    inline=False,
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ No CTFtime team ID set")
            return

        # Set new team ID
        if self.db.set_ctftime_team_id(str(ctx.guild.id), team_id):
            embed = discord.Embed(
                title="✅ CTFtime Team ID Set",
                description=f"Team ID: `{team_id}`",
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Team URL",
                value=f"https://ctftime.org/team/{team_id}",
                inline=False,
            )
            await ctx.send(embed=embed)
            # Get notification channel
            channel_id = self.db.get_notification_channel(str(ctx.guild.id))
            if not channel_id:
                await ctx.send(
                    "⚠️ No notification channel set. Please use `!setnotify #channel` to set one."
                )
                return
            channel = ctx.guild.get_channel(int(channel_id))
            if not channel:
                await ctx.send(
                    "⚠️ Notification channel not found. Please set a new one using `!setnotify #channel`."
                )
                return
            # Send loading message
            loading_msg = await channel.send("⏳ Importing planned events from CTFtime...")

            try:
                # Get team's planned events
                planned_events = get_team_events(team_id)
                if not planned_events:
                    await loading_msg.edit(
                        content="❌ No planned events found or failed to fetch events."
                    )
                    return

                # Import each planned event
                imported_count = 0
                skipped_count = 0
                error_count = 0

                for event in planned_events:
                    # Check if event already exists
                    if self.db.get_event(event["id"], str(ctx.guild.id)):
                        skipped_count += 1
                        continue

                    # Get event details
                    event_details = await get_event(event["id"])
                    if not event_details:
                        error_count += 1
                        continue

                    # Add event to database
                    if self.db.add_event(
                        event["id"],
                        str(ctx.guild.id),
                        event_details["title"],
                        event_details["start"],
                        event_details["finish"],
                        event_details["format"],
                        event_details["weight"],
                        event_details["location"],
                        event_details["url"],
                        event_details["ctftime_url"],
                        str(ctx.author.id),  # Use command user's ID as adder
                    ):
                        # Create role
                        try:
                            role = await ctx.guild.create_role(
                                name=f"CTF-{event_details['title']}",
                                color=discord.Color.blue(),
                                reason=f"Creating role for CTF competition {event_details['title']}",
                            )
                        except discord.Forbidden:
                            print(f"No permission to create role in guild {ctx.guild.id}")
                        except Exception as e:
                            print(f"Error creating role: {e}")

                        # Send notification
                        embed = discord.Embed(
                            title="🎯 New CTF Competition Added",
                            description=f"**Competition Name:**\n{event_details['title']}\n\n**ID:** `{event['id']}`",
                            color=discord.Color.blue(),
                        )

                        # Add time information
                        start_time = datetime.fromisoformat(event_details["start"])
                        end_time = datetime.fromisoformat(event_details["finish"])
                        time_info = (
                            f"**Start Time:**\n{start_time.strftime('%Y-%m-%d %H:%M')} UTC\n\n"
                            f"**End Time:**\n{end_time.strftime('%Y-%m-%d %H:%M')} UTC"
                        )
                        embed.add_field(
                            name="⏰ Time Information", value=time_info, inline=False
                        )

                        # Add competition details
                        details = f"**Type:** {event_details['format']}\n**Weight:** {event_details['weight']}\n"
                        if event_details["location"]:
                            details += f"**Location:** {event_details['location']}\n"
                        embed.add_field(
                            name="📋 Competition Details", value=details, inline=False
                        )
                        # Add links
                        links = (
                            f"**Official Link:**\n[Click to Visit]({event_details['url']})\n\n"
                            f"**CTFtime Link:**\n[Click to Visit]({event_details['ctftime_url']})"
                        )
                        embed.add_field(name="🔗 Links", value=links, inline=False)

                        embed.set_footer(text=f"event_id:{event['id']}")
                        await channel.send(embed=embed)
                        imported_count += 1
                    else:
                        error_count += 1

                # Send summary
                summary = (
                    f"✅ Import completed!\n\n"
                    f"📊 Summary:\n"
                    f"• Imported: {imported_count} events\n"
                    f"• Skipped (already exist): {skipped_count} events\n"
                    f"• Failed: {error_count} events"
                )
                await loading_msg.edit(content=summary)

            except Exception as e:
                await loading_msg.edit(content=f"❌ Error importing events: {str(e)}")
        else:
            await ctx.send("❌ Error setting CTFtime team ID")

    @commands.command()
    async def timezone(self, ctx, timezone_str: str = None):
        """Set or view timezone
        Usage:
        !timezone - View current timezone setting
        !timezone list - Show timezone selection menu
        !timezone <timezone> - Set timezone (e.g., Asia/Taipei)
        """
        try:
            if timezone_str is None:
                # Show current timezone setting
                current_tz = self.db.get_user_timezone(
                    str(ctx.author.id), str(ctx.guild.id)
                )
                embed = discord.Embed(
                    title="⏰ Current Timezone Setting", color=discord.Color.blue()
                )
                embed.add_field(name="Timezone", value=current_tz, inline=False)
                # Show current time
                tz = pytz.timezone(current_tz)
                current_time = datetime.now(tz)
                embed.add_field(
                    name="Current Time",
                    value=current_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                    inline=False,
                )
                embed.set_footer(text="Use <!timezone list> to change timezone")
                await ctx.send(embed=embed)
                return

            if timezone_str.lower() == "list":
                # Create timezone selection menu
                common_timezones = {
                    "Asia": [
                        "Asia/Taipei",  # Taipei
                        "Asia/Shanghai",  # Shanghai
                        "Asia/Hong_Kong",  # Hong Kong
                        "Asia/Tokyo",  # Tokyo
                        "Asia/Seoul",  # Seoul
                        "Asia/Singapore",  # Singapore
                    ],
                    "Europe": [
                        "Europe/London",  # London
                        "Europe/Paris",  # Paris
                        "Europe/Berlin",  # Berlin
                        "Europe/Moscow",  # Moscow
                    ],
                    "America": [
                        "America/New_York",  # New York
                        "America/Los_Angeles",  # Los Angeles
                        "America/Chicago",  # Chicago
                        "America/Toronto",  # Toronto
                    ],
                    "Oceania": [
                        "Australia/Sydney",  # Sydney
                        "Australia/Melbourne",  # Melbourne
                        "Pacific/Auckland",  # Auckland
                    ],
                }

                # Create embed
                embed = discord.Embed(
                    title="🌍 Select Your Timezone",
                    description="Please select your timezone from the menu below.",
                    color=discord.Color.blue(),
                )

                # Add timezone groups to embed
                # for region, zones in common_timezones.items():
                #     value = "\n".join([f"`{zone}`" for zone in zones])
                #     embed.add_field(name=region, value=value, inline=False)

                # Create select menu
                select = discord.ui.Select(
                    placeholder="Choose your timezone...",
                    min_values=1,
                    max_values=1,
                )

                # Add options to select menu
                for region, zones in common_timezones.items():
                    for zone in zones:
                        # Get current time in this timezone
                        tz = pytz.timezone(zone)
                        current_time = datetime.now(tz)
                        time_str = current_time.strftime("%H:%M")

                        # Create option label with current time
                        label = f"{zone.split('/')[-1].replace('_', ' ')} ({time_str})"
                        select.add_option(
                            label=label, value=zone, description=f"Current time: {time_str}"
                        )

                # Create view with select menu
                view = discord.ui.View()
                view.add_item(select)

                # Add callback for select menu
                async def select_callback(interaction: discord.Interaction):
                    if interaction.user.id != ctx.author.id:
                        await interaction.response.send_message(
                            "❌ This menu is not for you!", ephemeral=True
                        )
                        return

                    selected_timezone = select.values[0]
                    if self.db.set_user_timezone(
                        str(ctx.author.id), str(ctx.guild.id), selected_timezone
                    ):
                        # Get current time in new timezone
                        tz = pytz.timezone(selected_timezone)
                        current_time = datetime.now(tz)

                        embed = discord.Embed(
                            title="✅ Timezone Updated",
                            color=discord.Color.green(),
                        )
                        embed.add_field(
                            name="New Timezone", value=selected_timezone, inline=False
                        )
                        embed.add_field(
                            name="Current Time",
                            value=current_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                            inline=False,
                        )
                        await interaction.response.edit_message(embed=embed, view=None)
                    else:
                        await interaction.response.send_message(
                            "❌ Error setting timezone", ephemeral=True
                        )

                select.callback = select_callback

                # Send message with select menu
                await ctx.send(embed=embed, view=view)
                return

            # If timezone is provided directly (legacy support)
            try:
                tz = pytz.timezone(timezone_str)
                # Test if timezone is valid
                datetime.now(tz)
            except pytz.exceptions.UnknownTimeZoneError:
                await ctx.send(
                    "❌ Invalid timezone! Please use `!timezone list` to select a timezone"
                )
                return

            # Set timezone
            if self.db.set_user_timezone(str(ctx.author.id), str(ctx.guild.id), timezone_str):
                embed = discord.Embed(
                    title="✅ Timezone Updated", color=discord.Color.green()
                )
                embed.add_field(name="New Timezone", value=timezone_str, inline=False)
                # Show current time in new timezone
                current_time = datetime.now(tz)
                embed.add_field(
                    name="Current Time",
                    value=current_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                    inline=False,
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Error setting timezone")
        except Exception as e:
            await ctx.send(f"❌ Error occurred: {str(e)}")


async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(Settings(bot))
