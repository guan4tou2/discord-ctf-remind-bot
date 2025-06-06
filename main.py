import base64
import os
from datetime import datetime, timedelta

import discord
import pytz
import requests
from discord.ext import commands, tasks
from dotenv import load_dotenv

from ctftime_api import get_event, get_team_events
from database import Database

# 加载环境变量
load_dotenv()

# 设置 bot 的意图
intents = discord.Intents.default()
intents.message_content = True

# 创建 bot 实例
bot = commands.Bot(command_prefix="!", intents=intents)

# 初始化数据库
db = Database()


@bot.command()
async def timezone(ctx, timezone_str: str = None):
    """Set or view timezone
    Usage:
    !timezone - View current timezone setting
    !timezone list - Show timezone selection menu
    """
    try:
        if timezone_str is None:
            # Show current timezone setting
            current_tz = db.get_user_timezone(str(ctx.author.id), str(ctx.guild.id))
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
            embed.set_footer(text="Use !timezone list to change timezone")
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
                if db.set_user_timezone(
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
        if db.set_user_timezone(str(ctx.author.id), str(ctx.guild.id), timezone_str):
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


def convert_to_user_timezone(dt: datetime, user_id: str, guild_id: str) -> datetime:
    """Convert UTC time to user's timezone"""
    try:
        user_tz = db.get_user_timezone(user_id, guild_id)
        tz = pytz.timezone(user_tz)
        return dt.astimezone(tz)
    except Exception:
        return dt


@tasks.loop(minutes=1)  # Check every minute
async def check_ctf_events():
    """Check CTF competition times and send reminders"""
    try:
        for guild in bot.guilds:
            events = db.get_all_events(str(guild.id))
            now = datetime.now(pytz.UTC)

            for event in events:
                start_time = datetime.fromisoformat(event["start_time"])
                end_time = datetime.fromisoformat(event["end_time"])

                # 跳過已結束的比賽
                if now > end_time:
                    continue

                # 取得該比賽的所有參與者
                participants = db.get_event_participants(
                    event["event_id"], str(guild.id)
                )

                for participant in participants:
                    user_id = participant["user_id"]

                    # 取得使用者的提醒設定
                    before_start, before_end = db.get_reminder_settings(
                        event["event_id"], str(guild.id), user_id
                    )
                    if not before_start and not before_end:
                        # 使用預設值
                        before_start = "24h_before,1h_before"
                        before_end = "1h_before_end,10m_before_end"

                    # 轉換時間到使用者時區
                    user_start_time = convert_to_user_timezone(
                        start_time, user_id, str(guild.id)
                    )
                    user_end_time = convert_to_user_timezone(
                        end_time, user_id, str(guild.id)
                    )

                    # 檢查開始時間提醒
                    if before_start:
                        for remind_time in before_start.split(","):
                            if remind_time == "24h_before":
                                time_diff = user_start_time - now
                                if (
                                    timedelta(hours=23, minutes=55)
                                    <= time_diff
                                    <= timedelta(hours=24, minutes=5)
                                ):
                                    await send_reminder(
                                        guild,
                                        user_id,
                                        event,
                                        "24 hours before",
                                        user_start_time,
                                        user_end_time,
                                    )
                            elif remind_time == "12h_before":
                                time_diff = user_start_time - now
                                if (
                                    timedelta(hours=11, minutes=55)
                                    <= time_diff
                                    <= timedelta(hours=12, minutes=5)
                                ):
                                    await send_reminder(
                                        guild,
                                        user_id,
                                        event,
                                        "12 hours before",
                                        user_start_time,
                                        user_end_time,
                                    )
                            elif remind_time == "1h_before":
                                time_diff = user_start_time - now
                                if (
                                    timedelta(minutes=55)
                                    <= time_diff
                                    <= timedelta(hours=1, minutes=5)
                                ):
                                    await send_reminder(
                                        guild,
                                        user_id,
                                        event,
                                        "1 hour before",
                                        user_start_time,
                                        user_end_time,
                                    )

                    # 檢查結束時間提醒
                    if (
                        before_end and now > user_start_time
                    ):  # 只在比賽開始後檢查結束時間提醒
                        for remind_time in before_end.split(","):
                            if remind_time == "1h_before_end":
                                time_diff = user_end_time - now
                                if (
                                    timedelta(minutes=55)
                                    <= time_diff
                                    <= timedelta(hours=1, minutes=5)
                                ):
                                    await send_reminder(
                                        guild,
                                        user_id,
                                        event,
                                        "1 hour before",
                                        user_start_time,
                                        user_end_time,
                                        is_end=True,
                                    )
                            elif remind_time == "30m_before_end":
                                time_diff = user_end_time - now
                                if (
                                    timedelta(minutes=25)
                                    <= time_diff
                                    <= timedelta(minutes=35)
                                ):
                                    await send_reminder(
                                        guild,
                                        user_id,
                                        event,
                                        "30 minutes before",
                                        user_start_time,
                                        user_end_time,
                                        is_end=True,
                                    )
                            elif remind_time == "10m_before_end":
                                time_diff = user_end_time - now
                                if (
                                    timedelta(minutes=8)
                                    <= time_diff
                                    <= timedelta(minutes=12)
                                ):
                                    await send_reminder(
                                        guild,
                                        user_id,
                                        event,
                                        "10 minutes before",
                                        user_start_time,
                                        user_end_time,
                                        is_end=True,
                                    )

    except Exception as e:
        print(f"Error checking CTF competitions: {str(e)}")


async def send_reminder(
    guild, user_id, event, time_str, start_time, end_time, is_end=False
):
    """Send reminder message"""
    try:
        member = await guild.fetch_member(int(user_id))
        if not member:
            return

        embed = discord.Embed(
            title="🏁 Competition Ending Soon"
            if is_end
            else "🎯 Competition Starting Soon",
            description=f"Competition: {event['name']}\n\n{time_str} until competition {'ends' if is_end else 'starts'}",
            color=discord.Color.red() if is_end else discord.Color.green(),
        )

        time_info = (
            f"**Start Time:**\n{start_time.strftime('%Y-%m-%d %H:%M')} ({start_time.tzinfo})\n\n"
            f"**End Time:**\n{end_time.strftime('%Y-%m-%d %H:%M')} ({end_time.tzinfo})"
        )
        embed.add_field(name="⏰ Time Information", value=time_info, inline=False)

        if event["official_url"]:
            embed.add_field(
                name="🔗 Competition Link", value=event["official_url"], inline=False
            )

        try:
            await member.send(embed=embed)
        except discord.Forbidden:
            # If cannot send DM, try to remind in notification channel
            channel_id = db.get_notification_channel(str(guild.id))
            if channel_id:
                channel = guild.get_channel(int(channel_id))
                if channel:
                    await channel.send(f"{member.mention}", embed=embed)
    except Exception as e:
        print(f"Error sending reminder: {e}")


@bot.command()
@commands.has_permissions(administrator=True)
async def setctftime(ctx, team_id: str = None):
    """Set or view CTFtime team ID
    Usage:
    !setctftime - View current CTFtime team ID
    !setctftime <team_id> - Set CTFtime team ID and import planned events
    """
    if team_id is None:
        # View current team ID
        current_team_id = db.get_ctftime_team_id(str(ctx.guild.id))
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
    if db.set_ctftime_team_id(str(ctx.guild.id), team_id):
        embed = discord.Embed(
            title="✅ CTFtime Team ID Set",
            description=f"Team ID: `{team_id}`",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Team URL", value=f"https://ctftime.org/team/{team_id}", inline=False
        )
        await ctx.send(embed=embed)

        # Get notification channel
        channel_id = db.get_notification_channel(str(ctx.guild.id))
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
                if db.get_event(event["id"], str(ctx.guild.id)):
                    skipped_count += 1
                    continue

                # Get event details
                event_details = await get_event(event["id"])
                if not event_details:
                    error_count += 1
                    continue

                # Add event to database
                if db.add_event(
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


@tasks.loop(hours=1)  # Check every hour
async def check_team_events():
    """Check team's planned CTF events and add them automatically"""
    try:
        for guild in bot.guilds:
            team_id = db.get_ctftime_team_id(str(guild.id))
            if not team_id:
                continue

            # Get team's planned events
            planned_events = get_team_events(team_id)
            if not planned_events:
                continue

            # Get notification channel
            channel_id = db.get_notification_channel(str(guild.id))
            if not channel_id:
                continue

            channel = guild.get_channel(int(channel_id))
            if not channel:
                continue

            # Check each planned event
            for event in planned_events:
                # Check if event already exists
                if db.get_event(event["id"], str(guild.id)):
                    continue

                # Get event details
                event_details = await get_event(event["id"])
                if not event_details:
                    continue

                # Add event to database
                if db.add_event(
                    event["id"],
                    str(guild.id),
                    event_details["title"],
                    event_details["start"],
                    event_details["finish"],
                    event_details["format"],
                    event_details["weight"],
                    event_details["location"],
                    event_details["url"],
                    event_details["ctftime_url"],
                    None,  # No adder for automatic imports
                ):
                    # Create role
                    try:
                        role = await guild.create_role(
                            name=f"CTF-{event_details['title']}",
                            color=discord.Color.blue(),
                            reason=f"Creating role for CTF competition {event_details['title']}",
                        )
                    except discord.Forbidden:
                        print(f"No permission to create role in guild {guild.id}")
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

    except Exception as e:
        print(f"Error checking team events: {str(e)}")


@bot.event
async def on_ready():
    print(f"{bot.user} has successfully started!")
    # Start scheduled check tasks
    if not check_ctf_events.is_running():
        check_ctf_events.start()
    if not check_team_events.is_running():
        check_team_events.start()


@bot.command()
async def ping(ctx):
    """Test bot's response speed"""
    # Create embed
    embed = discord.Embed(title="🏓 Pong!", color=discord.Color.green())

    # Calculate response time
    latency = round(bot.latency * 1000)  # Convert latency to milliseconds

    # Add fields
    embed.add_field(name="Response Time", value=f"{latency}ms", inline=True)
    embed.add_field(
        name="API Latency",
        value=f"{round(latency * 0.56)}ms",  # Estimate API latency
        inline=True,
    )

    # Set timestamp
    embed.timestamp = discord.utils.utcnow()

    await ctx.send(embed=embed)


@bot.command()
async def base64_cmd(ctx, mode: str = None, *, text: str = None):
    """Base64 encode/decode
    Usage:
    !base64 encode <text> - Convert text to base64
    !base64 decode <base64_text> - Convert base64 to text
    """
    if mode is None or text is None:
        await ctx.send(
            "❌ Missing arguments! Please use:\n`!base64 encode <text>` or `!base64 decode <text>`"
        )
        return

    try:
        if mode.lower() == "encode":
            # Encode
            result = base64.b64encode(text.encode("utf-8")).decode("utf-8")
            title = "Base64 Encoding"
            color = discord.Color.blue()
            input_name = "Original Text"
            output_name = "Encoded Result"
        elif mode.lower() == "decode":
            # Decode
            result = base64.b64decode(text.encode("utf-8")).decode("utf-8")
            title = "Base64 Decoding"
            color = discord.Color.green()
            input_name = "Encoded Text"
            output_name = "Decoded Result"
        else:
            await ctx.send("❌ Invalid mode! Please use `encode` or `decode`")
            return

        embed = discord.Embed(title=title, color=color)
        embed.add_field(name=input_name, value=f"```{text}```", inline=False)
        embed.add_field(name=output_name, value=f"```{result}```", inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"❌ Error occurred: {str(e)}")


@bot.command()
@commands.has_permissions(administrator=True)
async def setnotify(ctx, channel: discord.TextChannel = None):
    """Set notification channel for CTF events
    Usage:
    !setnotify - View current notification channel
    !setnotify #channel - Set notification channel
    """
    if channel is None:
        # View current channel
        channel_id = db.get_notification_channel(str(ctx.guild.id))
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
    if db.set_notification_channel(str(ctx.guild.id), str(channel.id)):
        await ctx.send(f"✅ Notification channel set to {channel.mention}")
    else:
        await ctx.send("❌ Error setting notification channel")


class CTFButtons(discord.ui.View):
    def __init__(self, event_id: str, event_name: str):
        super().__init__(timeout=None)  # Buttons will not timeout
        self.event_id = event_id
        self.event_name = event_name

    @discord.ui.button(label="Join CTF", style=discord.ButtonStyle.green, emoji="✅")
    async def join_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            # Check if user already joined
            if db.is_user_joined(
                self.event_id, str(interaction.guild_id), str(interaction.user.id)
            ):
                await interaction.response.send_message(
                    f"❌ You have already joined {self.event_name}!", ephemeral=True
                )
                return

            # Join competition
            if db.join_event(
                self.event_id, str(interaction.guild_id), str(interaction.user.id)
            ):
                # Find corresponding role
                role_name = f"CTF-{self.event_name}"
                role = discord.utils.get(interaction.guild.roles, name=role_name)

                if role:
                    try:
                        await interaction.user.add_roles(role)
                        success_msg = f"✅ Role added: {role.mention}"
                    except discord.Forbidden:
                        success_msg = "⚠️ Could not add role (missing permissions)"
                    except Exception as e:
                        success_msg = f"⚠️ Error adding role: {str(e)}"
                else:
                    success_msg = "⚠️ Role not found"

                # Get event details for DM
                event = db.get_event(self.event_id, str(interaction.guild_id))
                if event and event.get("invite_link"):
                    try:
                        # Send invite link via DM
                        embed = discord.Embed(
                            title="🔗 CTF Competition Invite Link",
                            description=f"Competition: {self.event_name}",
                            color=discord.Color.blue(),
                        )
                        embed.add_field(
                            name="Invite Link", value=event["invite_link"], inline=False
                        )
                        embed.add_field(
                            name="Note",
                            value="Please keep this link private and do not share it with non-participants.",
                            inline=False,
                        )
                        await interaction.user.send(embed=embed)
                        success_msg += "\n✉️ Invite link has been sent via DM"
                    except discord.Forbidden:
                        success_msg += "\n⚠️ Could not send invite link (DMs are closed)"

                await interaction.response.send_message(
                    f"✅ Successfully joined {self.event_name}\n{success_msg}",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "❌ Error joining competition", ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error occurred: {str(e)}", ephemeral=True
            )

    @discord.ui.button(label="Leave CTF", style=discord.ButtonStyle.red, emoji="🚪")
    async def leave_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            # Check if user has joined
            if not db.is_user_joined(
                self.event_id, str(interaction.guild_id), str(interaction.user.id)
            ):
                await interaction.response.send_message(
                    f"❌ You haven't joined {self.event_name}!", ephemeral=True
                )
                return

            # Leave competition
            if db.leave_event(
                self.event_id, str(interaction.guild_id), str(interaction.user.id)
            ):
                # Remove role
                role_name = f"CTF-{self.event_name}"
                role = discord.utils.get(interaction.guild.roles, name=role_name)

                if role and role in interaction.user.roles:
                    try:
                        await interaction.user.remove_roles(role)
                        success_msg = f"✅ Role removed: {role.mention}"
                    except discord.Forbidden:
                        success_msg = "⚠️ Could not remove role (missing permissions)"
                    except Exception as e:
                        success_msg = f"⚠️ Error removing role: {str(e)}"
                else:
                    success_msg = ""

                await interaction.response.send_message(
                    f"✅ Successfully left {self.event_name}\n{success_msg}",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "❌ Error leaving competition", ephemeral=True
                )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error occurred: {str(e)}", ephemeral=True
            )


@bot.command()
async def addctf(ctx, event_id: str):
    """Add CTF competition to reminder list
    Usage:
    !addctf <ctftime_event_id> - Add specified CTF competition to reminder list
    """
    loading_msg = await ctx.send("⏳ Getting competition information...")

    try:
        # Get competition info
        event = await get_event(event_id)
        if not event:
            await loading_msg.edit(
                content="❌ Unable to get competition info, please check the event ID"
            )
            return

        # Check if competition already exists
        if db.get_event(event_id, str(ctx.guild.id)):
            await loading_msg.edit(content="❌ This competition has already been added")
            return

        # Add competition to database
        if db.add_event(
            event_id,
            str(ctx.guild.id),
            event["title"],
            event["start"],
            event["finish"],
            event["format"],
            event["weight"],
            event["location"],
            event["url"],
            event["ctftime_url"],
            str(ctx.author.id),  # Adder's ID
        ):
            # Create role
            try:
                role = await ctx.guild.create_role(
                    name=f"CTF-{event['title']}",
                    color=discord.Color.blue(),
                    reason=f"Creating role for CTF competition {event['title']}",
                )
            except discord.Forbidden:
                await ctx.send("❌ No permission to create roles")
            except Exception as e:
                await ctx.send(f"❌ Error creating role: {str(e)}")

            # Create embed with buttons
            embed = discord.Embed(
                title="🎯 New CTF Competition Added",
                description=f"**Competition Name:**\n{event['title']}\n\n**ID:** `{event_id}`",
                color=discord.Color.blue(),
            )

            # Add time information
            start_time = datetime.fromisoformat(event["start"])
            end_time = datetime.fromisoformat(event["finish"])
            time_info = (
                f"**Start Time:**\n{start_time.strftime('%Y-%m-%d %H:%M')} UTC\n\n"
                f"**End Time:**\n{end_time.strftime('%Y-%m-%d %H:%M')} UTC"
            )
            embed.add_field(name="⏰ Time Information", value=time_info, inline=False)

            # Add competition details
            details = f"**Type:** {event['format']}\n**Weight:** {event['weight']}\n"
            if event["location"]:
                details += f"**Location:** {event['location']}\n"
            embed.add_field(name="📋 Competition Details", value=details, inline=False)

            # Add links
            links = (
                f"**Official Link:**\n[Click to Visit]({event['url']})\n\n"
                f"**CTFtime Link:**\n[Click to Visit]({event['ctftime_url']})"
            )
            embed.add_field(name="🔗 Links", value=links, inline=False)

            # Add hidden event ID for message identification
            embed.set_footer(text=f"event_id:{event_id}")

            # Create view with buttons
            view = CTFButtons(event_id=event_id, event_name=event["title"])

            # Get notification channel
            channel_id = db.get_notification_channel(str(ctx.guild.id))

            if channel_id:
                try:
                    channel = ctx.guild.get_channel(int(channel_id))
                    if channel:
                        # Send detailed embed to notification channel
                        await channel.send(
                            embed=embed,
                            view=CTFButtons(
                                event_id=event_id, event_name=event["title"]
                            ),
                        )

                        # If command was used in notification channel, don't send another message
                        if str(ctx.channel.id) == channel_id:
                            await loading_msg.delete()
                        else:
                            # Send simple success message in original channel
                            await loading_msg.edit(
                                content=f"✅ Successfully added {event['title']}! Check {channel.mention} for details."
                            )
                    else:
                        # If notification channel not found, send detailed embed in current channel
                        await loading_msg.edit(content=None, embed=embed, view=view)
                        await ctx.send(
                            "⚠️ Notification channel not found. Please set a new one using `!setnotify #channel`."
                        )
                except Exception as e:
                    # If error sending to notification channel, send detailed embed in current channel
                    await loading_msg.edit(content=None, embed=embed, view=view)
                    print(f"Error sending to notification channel: {e}")
            else:
                # If no notification channel set, send detailed embed in current channel
                await loading_msg.edit(content=None, embed=embed, view=view)
                await ctx.send(
                    "⚠️ No notification channel set. Please use `!setnotify #channel` to set one."
                )
        else:
            await loading_msg.edit(content="❌ Failed to add competition")

    except Exception as e:
        error_message = str(e)
        if "UNIQUE constraint failed" in error_message:
            await loading_msg.edit(
                content=f"❌ This CTF competition (ID: {event_id}) already exists in this server!"
            )
        else:
            await loading_msg.edit(
                content=f"❌ Error adding competition: {error_message}"
            )


@bot.command()
async def delctf(ctx, event_id: str):
    """Delete specified CTF competition
    Usage:
    !delctf <ctftime_event_id> - Delete specified CTF competition
    """
    event = db.get_event(event_id, str(ctx.guild.id))
    if not event:
        await ctx.send("❌ Competition not found")
        return

    # Find and delete corresponding role
    role_name = f"CTF-{event['name']}"
    role = discord.utils.get(ctx.guild.roles, name=role_name)

    if role:
        try:
            await role.delete(
                reason=f"Deleting role for CTF competition {event['name']}"
            )
            await ctx.send(f"✅ Role deleted: {role_name}")
        except discord.Forbidden:
            await ctx.send("❌ No permission to delete roles")
        except Exception as e:
            await ctx.send(f"❌ Error deleting role: {str(e)}")

    # Delete notification message if exists
    channel_id = db.get_notification_channel(str(ctx.guild.id))
    if channel_id:
        try:
            channel = ctx.guild.get_channel(int(channel_id))
            if channel:
                # Search for the notification message with matching event ID
                async for message in channel.history(limit=None):
                    if (
                        message.embeds
                        and message.embeds[0].footer.text == f"event_id:{event_id}"
                    ):
                        await message.delete()
                        break
        except Exception as e:
            print(f"Error deleting notification message: {e}")

    if db.delete_event(event_id, str(ctx.guild.id)):
        embed = discord.Embed(
            title="🗑️ CTF Competition Deleted", color=discord.Color.red()
        )
        embed.add_field(name="Competition Name", value=event["name"], inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ Error deleting competition")


@bot.command()
async def listctf(ctx):
    """List all added CTF competitions"""
    events = db.get_all_events(str(ctx.guild.id))

    if not events:
        await ctx.send("📝 No CTF competitions added yet")
        return

    # Sort by start time
    events.sort(key=lambda x: x["start_time"])

    # Create main embed
    main_embed = discord.Embed(
        title="📋 CTF Competition List",
        description=f"Total: {len(events)} competitions",
        color=discord.Color.blue(),
    )

    # Add competition info
    for i, event in enumerate(events, 1):
        start_time = datetime.fromisoformat(event["start_time"])
        end_time = datetime.fromisoformat(event["end_time"])

        # Convert to user's timezone
        user_start_time = convert_to_user_timezone(
            start_time, str(ctx.author.id), str(ctx.guild.id)
        )
        user_end_time = convert_to_user_timezone(
            end_time, str(ctx.author.id), str(ctx.guild.id)
        )

        # Calculate remaining time (ensure timezone consistency)
        now = datetime.now(user_start_time.tzinfo)
        time_left = user_start_time - now

        # Set status and color
        if now > user_end_time:
            status = "Ended"
            color = "🔴"
        elif now > user_start_time:
            status = "In Progress"
            color = "🟢"
        else:
            days = time_left.days
            if days > 7:
                status = f"{days} days left"
                color = "⚪"
            elif days > 0:
                status = f"{days} days left"
                color = "🟡"
            else:
                hours = time_left.seconds // 3600
                status = f"{hours} hours left"
                color = "🟠"

        # Get adder info
        adder = None
        if event.get("added_by"):
            try:
                adder = await ctx.guild.fetch_member(event["added_by"])
            except discord.NotFound:
                # Member not found (left the server)
                adder = None
            except discord.HTTPException:
                # Failed to fetch member
                adder = None
            except Exception as e:
                print(f"Error fetching member: {e}")
                adder = None

        # Create competition info field
        value = (
            f"**ID:** `{event['event_id']}`\n\n"
            f"**Start Time:**\n{user_start_time.strftime('%Y-%m-%d %H:%M')} ({user_start_time.tzinfo})\n\n"
            f"**End Time:**\n{user_end_time.strftime('%Y-%m-%d %H:%M')} ({user_end_time.tzinfo})\n\n"
            f"**Type:** {event['event_type']}\n"
            f"**Weight:** {event['weight']}\n"
            f"**Location:** {event['location']}\n"
            f"**Status:** {color} {status}\n"
            f"**Added by:** {adder.mention if adder else 'Unknown'}"
        )

        # Add links
        if event["official_url"]:
            value += f"\n\n**Official Link:**\n{event['official_url']}"
        if event["ctftime_url"]:
            value += f"\n\n**CTFtime:**\n{event['ctftime_url']}"

        # Add separator
        if i < len(events):
            value += "\n\n" + "─" * 30

        main_embed.add_field(name=f"🏆 {event['name']}", value=value, inline=False)

    # Add footer
    main_embed.set_footer(
        text="Use !addctf <id> to add competition | Use !delctf <id> to delete competition"
    )

    await ctx.send(embed=main_embed)


@bot.command()
@commands.has_permissions(administrator=True)
async def invitectf(ctx, event_id: str, invite_link: str = None):
    """Set or view competition invite link"""
    event = db.get_event(event_id, str(ctx.guild.id))
    if not event:
        await ctx.send("❌ Competition not found, please add it first using !addctf")
        return

    if invite_link is None:
        # View current invite link
        if event["invite_link"]:
            try:
                # Only send DM if there's an invite link
                embed = discord.Embed(
                    title="🔗 Competition Invite Link",
                    description=f"Competition: {event['name']}",
                    color=discord.Color.blue(),
                )
                embed.add_field(
                    name="Invite Link",
                    value=event["invite_link"],
                    inline=False,
                )
                await ctx.author.send(embed=embed)

                # Send message in original channel
                channel_embed = discord.Embed(
                    title="🔗 Competition Invite Link",
                    description=f"Competition: {event['name']}\nInvite link has been sent via DM.",
                    color=discord.Color.blue(),
                )
                await ctx.send(embed=channel_embed)
            except discord.Forbidden:
                await ctx.send("❌ Cannot send DM, please check your privacy settings")
        else:
            # If no invite link, just show message in channel
            embed = discord.Embed(
                title="🔗 Competition Invite Link",
                description=f"Competition: {event['name']}\nNo invite link has been set yet.",
                color=discord.Color.blue(),
            )
            await ctx.send(embed=embed)
    else:
        # Delete original command message when setting new link
        try:
            await ctx.message.delete(delay=0)  # Delete message immediately
        except discord.Forbidden:
            print("Cannot delete message: Bot lacks message deletion permission")
        except discord.HTTPException as e:
            print(f"Error deleting message: {e}")
        except Exception as e:
            print(f"Unknown error deleting message: {e}")

        # Set new invite link
        if db.set_event_invite_link(event_id, str(ctx.guild.id), invite_link):
            try:
                # Send DM to admin
                embed = discord.Embed(
                    title="✅ Invite Link Set"
                    if not event["invite_link"]
                    else "✅ Invite Link Updated",
                    description=f"Competition: {event['name']}",
                    color=discord.Color.green(),
                )
                embed.add_field(name="Invite Link", value=invite_link, inline=False)
                await ctx.author.send(embed=embed)

                # Send update message in original channel (without link)
                channel_embed = discord.Embed(
                    title="✅ Invite Link Set"
                    if not event["invite_link"]
                    else "✅ Invite Link Updated",
                    description=f"Competition: {event['name']}\nInvite link has been sent via DM to adder and participants.",
                    color=discord.Color.green(),
                )
                await ctx.send(embed=channel_embed)

                # Notify all members with the competition role
                role_name = f"CTF-{event['name']}"
                role = discord.utils.get(ctx.guild.roles, name=role_name)
                if role:
                    # Create notification message
                    notify_embed = discord.Embed(
                        title="🔔 Competition Invite Link Set"
                        if not event["invite_link"]
                        else "🔔 Competition Invite Link Updated",
                        description=f"Competition: {event['name']}",
                        color=discord.Color.blue(),
                    )
                    notify_embed.add_field(
                        name="Invite Link",
                        value=invite_link,
                        inline=False,
                    )
                    notify_embed.add_field(
                        name="Note",
                        value="Please keep this link private and do not share it with non-participants.",
                        inline=False,
                    )

                    # Send notifications
                    for member in role.members:
                        try:
                            await member.send(embed=notify_embed)
                        except discord.Forbidden:
                            continue  # Skip if cannot send DM to member
            except discord.Forbidden:
                await ctx.send("❌ Cannot send DM, please check your privacy settings")
        else:
            try:
                await ctx.author.send("❌ Failed to set invite link")
            except discord.Forbidden:
                await ctx.send("❌ Cannot send DM, please check your privacy settings")


@bot.command()
async def joinctf(ctx, event_id: str):
    """Join CTF competition
    Usage:
    !joinctf <ctftime_event_id> - Join specified CTF competition
    """
    try:
        # Check if competition exists
        event = db.get_event(event_id, str(ctx.guild.id))
        if not event:
            await ctx.send(
                "❌ Competition not found, please use !addctf to add it first"
            )
            return

        # Check if user already joined
        if db.is_user_joined(event_id, str(ctx.guild.id), str(ctx.author.id)):
            embed = discord.Embed(
                title="ℹ️ Already Joined",
                description=f"You have already joined this competition: {event['name']}",
                color=discord.Color.blue(),
            )
            await ctx.send(embed=embed)
            return

        # Join competition
        if db.join_event(event_id, str(ctx.guild.id), str(ctx.author.id)):
            # Find corresponding role
            role_name = f"CTF-{event['name']}"
            role = discord.utils.get(ctx.guild.roles, name=role_name)

            if role:
                try:
                    await ctx.author.add_roles(role)
                    await ctx.send(f"✅ Role added: {role.name}")
                except discord.Forbidden:
                    await ctx.send("❌ No permission to add roles")
                except Exception as e:
                    await ctx.send(f"❌ Error adding role: {str(e)}")
            else:
                await ctx.send("⚠️ Corresponding role not found")

            # Send public message
            embed = discord.Embed(
                title="✅ Successfully Joined Competition", color=discord.Color.green()
            )
            embed.add_field(name="Competition Name", value=event["name"], inline=False)
            embed.add_field(
                name="Start Time",
                value=datetime.fromisoformat(event["start_time"]).strftime(
                    "%Y-%m-%d %H:%M"
                ),
                inline=True,
            )
            embed.add_field(
                name="End Time",
                value=datetime.fromisoformat(event["end_time"]).strftime(
                    "%Y-%m-%d %H:%M"
                ),
                inline=True,
            )
            await ctx.send(embed=embed)

            # If there's an invite link, send it via DM
            invite_link = event.get("invite_link", "")
            if invite_link:
                try:
                    # Send a test message first
                    await ctx.author.send("Sending competition invite link...")

                    embed = discord.Embed(
                        title="🔗 CTF Competition Invite Link",
                        description=f"Competition: {event['name']}",
                        color=discord.Color.blue(),
                    )
                    embed.add_field(name="Invite Link", value=invite_link, inline=False)
                    embed.add_field(
                        name="Note",
                        value="Please keep this link private and do not share it with non-participants.",
                        inline=False,
                    )
                    await ctx.author.send(embed=embed)
                    await ctx.send("✅ Invite link has been sent via DM")
                except discord.Forbidden:
                    await ctx.send(
                        "⚠️ Cannot send DM, please ensure you have enabled DM permissions with the bot"
                    )
                except Exception as e:
                    await ctx.send(f"⚠️ Error sending invite link: {str(e)}")
            else:
                # Get adder info
                adder = None
                print(event)
                if event.get("added_by"):
                    try:
                        adder = await ctx.guild.fetch_member(event["added_by"])
                    except discord.NotFound:
                        # Member not found (left the server)
                        adder = None
                    except discord.HTTPException:
                        # Failed to fetch member
                        adder = None
                    except Exception as e:
                        print(f"Error fetching member: {e}")
                        adder = None
                await ctx.send(
                    f"ℹ️ This competition has no invite link set yet, please contact an adder **{adder.name if adder else 'Unknown'}**"
                )
        else:
            await ctx.send("❌ Error joining competition")
    except Exception as e:
        await ctx.send(f"❌ Error occurred: {str(e)}")


@bot.command()
async def leavectf(ctx, event_id: str):
    """Leave CTF competition
    Usage:
    !leavectf <ctftime_event_id> - Leave specified CTF competition
    """
    try:
        # Check if competition exists
        event = db.get_event(event_id, str(ctx.guild.id))
        if not event:
            await ctx.send("❌ Competition not found")
            return

        # Leave competition
        if db.leave_event(event_id, str(ctx.guild.id), str(ctx.author.id)):
            embed = discord.Embed(
                title="✅ Successfully Left Competition", color=discord.Color.blue()
            )
            embed.add_field(name="Competition Name", value=event["name"], inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Error leaving competition")
    except Exception as e:
        await ctx.send(f"❌ Error occurred: {str(e)}")


@bot.command()
async def myctf(ctx):
    """View all CTF competitions you're participating in"""
    try:
        events = db.get_user_events(str(ctx.guild.id), str(ctx.author.id))

        if not events:
            await ctx.send("📝 You haven't joined any CTF competitions yet")
            return

        # Create main embed
        main_embed = discord.Embed(
            title=f"📋 {ctx.author.name}'s CTF Competition List",
            description=f"Total: {len(events)} competitions",
            color=discord.Color.blue(),
        )

        # Add competition info
        for i, event in enumerate(events, 1):
            start_time = datetime.fromisoformat(event["start_time"])
            end_time = datetime.fromisoformat(event["end_time"])

            # Convert to user's timezone
            user_start_time = convert_to_user_timezone(
                start_time, str(ctx.author.id), str(ctx.guild.id)
            )
            user_end_time = convert_to_user_timezone(
                end_time, str(ctx.author.id), str(ctx.guild.id)
            )

            # Calculate remaining time (ensure timezone consistency)
            now = datetime.now(user_start_time.tzinfo)
            time_left = user_start_time - now

            # Set status and color
            if now > user_end_time:
                status = "Ended"
                color = "🔴"
            elif now > user_start_time:
                status = "In Progress"
                color = "🟢"
            else:
                days = time_left.days
                if days > 7:
                    status = f"{days} days left"
                    color = "⚪"
                elif days > 0:
                    status = f"{days} days left"
                    color = "🟡"
                else:
                    hours = time_left.seconds // 3600
                    status = f"{hours} hours left"
                    color = "🟠"

            # Create competition info field
            value = (
                f"**ID:** `{event['event_id']}`\n\n"
                f"**Start Time:**\n{user_start_time.strftime('%Y-%m-%d %H:%M')} ({user_start_time.tzinfo})\n\n"
                f"**End Time:**\n{user_end_time.strftime('%Y-%m-%d %H:%M')} ({user_end_time.tzinfo})\n\n"
                f"**Type:** {event['event_type']}\n"
                f"**Weight:** {event['weight']}\n"
                f"**Location:** {event['location']}\n"
                f"**Status:** {color} {status}"
            )

            # Add links
            if event["official_url"]:
                value += f"\n\n**Official Link:**\n{event['official_url']}"
            if event["ctftime_url"]:
                value += f"\n\n**CTFtime:**\n{event['ctftime_url']}"

            # Add separator
            if i < len(events):
                value += "\n\n" + "─" * 30

            main_embed.add_field(name=f"🏆 {event['name']}", value=value, inline=False)

        await ctx.send(embed=main_embed)

    except Exception as e:
        await ctx.send(f"❌ Error occurred: {str(e)}")


async def get_ctf_event(event_id: str):
    """Get competition information from CTFtime API"""
    event_url = f"https://ctftime.org/api/v1/events/{event_id}/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    # Increase retry count and timeout
    for attempt in range(3):  # Maximum 3 retries
        try:
            response = requests.get(
                event_url, headers=headers, timeout=30
            )  # Increase timeout to 30 seconds
            response.raise_for_status()
            return response.json()
        except requests.Timeout:
            if attempt == 2:  # Last attempt
                raise Exception(
                    "Connection to CTFtime timed out, please try again later"
                )
            continue
        except requests.RequestException:
            if attempt == 2:  # Last attempt
                raise Exception("Unable to connect to CTFtime, please try again later")
            continue
    return None


@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param.name}")
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send("❌ Invalid argument provided")
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command")
        return
    if isinstance(error, commands.CommandInvokeError):
        await ctx.send(f"❌ An error occurred: {str(error.original)}")
        return
    await ctx.send(f"❌ An error occurred: {str(error)}")


@bot.command()
async def participants(ctx, event_id: str):
    """View competition participants
    Usage:
    !participants <ctftime_event_id> - Show list of participants for the specified competition
    """
    try:
        # Check if competition exists
        event = db.get_event(event_id, str(ctx.guild.id))
        if not event:
            await ctx.send(
                "❌ Competition not found, please use !addctf to add it first"
            )
            return

        # Get participants list
        participants = db.get_event_participants(event_id, str(ctx.guild.id))

        if not participants:
            await ctx.send(f"📝 No one has joined {event['name']} yet")
            return

        # Create embed
        embed = discord.Embed(
            title=f"👥 {event['name']} Participants",
            description=f"Total: {len(participants)} participants",
            color=discord.Color.blue(),
        )

        # Add participants info
        participants_list = []
        for i, participant in enumerate(participants, 1):
            try:
                member = await ctx.guild.fetch_member(participant["user_id"])
                join_time = datetime.fromisoformat(participant["join_time"])
                # Convert to user timezone
                user_join_time = convert_to_user_timezone(
                    join_time, participant["user_id"], str(ctx.guild.id)
                )
                participants_list.append(
                    f"{i}. {member.mention} (Joined: {user_join_time.strftime('%Y-%m-%d %H:%M')})"
                )
            except discord.NotFound:
                participants_list.append(
                    f"{i}. Unknown User (ID: {participant['user_id']})"
                )
            except Exception as e:
                print(f"Error fetching member: {e}")
                participants_list.append(
                    f"{i}. Unknown User (ID: {participant['user_id']})"
                )

        # Split participants list into fields (20 participants per field)
        chunk_size = 20
        for i in range(0, len(participants_list), chunk_size):
            chunk = participants_list[i : i + chunk_size]
            field_name = f"Participants List ({i + 1}-{min(i + chunk_size, len(participants_list))})"
            embed.add_field(name=field_name, value="\n".join(chunk), inline=False)

        # Add competition info
        start_time = datetime.fromisoformat(event["start_time"])
        end_time = datetime.fromisoformat(event["end_time"])

        # Convert to user timezone
        user_start_time = convert_to_user_timezone(
            start_time, str(ctx.author.id), str(ctx.guild.id)
        )
        user_end_time = convert_to_user_timezone(
            end_time, str(ctx.author.id), str(ctx.guild.id)
        )

        time_info = (
            f"**Start Time:**\n{user_start_time.strftime('%Y-%m-%d %H:%M')} ({user_start_time.tzinfo})\n\n"
            f"**End Time:**\n{user_end_time.strftime('%Y-%m-%d %H:%M')} ({user_end_time.tzinfo})"
        )
        embed.add_field(name="⏰ Competition Time", value=time_info, inline=False)

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Error occurred: {str(e)}")


class ReminderSelect(discord.ui.View):
    def __init__(self, event_id: str, event_name: str):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.event_id = event_id
        self.event_name = event_name
        self.selected_start = []
        self.selected_end = []

    @discord.ui.select(
        placeholder="Select reminder times before competition starts",
        min_values=0,
        max_values=3,
        options=[
            discord.SelectOption(label="24 hours before", value="24h_before"),
            discord.SelectOption(label="12 hours before", value="12h_before"),
            discord.SelectOption(label="1 hour before", value="1h_before"),
        ],
    )
    async def start_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        self.selected_start = select.values
        await interaction.response.defer()

    @discord.ui.select(
        placeholder="Select reminder times before competition ends",
        min_values=0,
        max_values=3,
        options=[
            discord.SelectOption(label="1 hour before", value="1h_before_end"),
            discord.SelectOption(label="30 minutes before", value="30m_before_end"),
            discord.SelectOption(label="10 minutes before", value="10m_before_end"),
        ],
    )
    async def end_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        self.selected_end = select.values
        await interaction.response.defer()

    @discord.ui.button(label="Confirm Settings", style=discord.ButtonStyle.green)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        # Use default values if none selected
        if not self.selected_start and not self.selected_end:
            self.selected_start = ["24h_before", "1h_before"]
            self.selected_end = ["1h_before_end", "10m_before_end"]

        # Save settings
        if db.set_reminder_settings(
            self.event_id,
            str(interaction.guild_id),
            str(interaction.user.id),
            ",".join(self.selected_start) if self.selected_start else "",
            ",".join(self.selected_end) if self.selected_end else "",
        ):
            embed = discord.Embed(
                title="✅ Reminder Settings Updated",
                description=f"Competition: {self.event_name}",
                color=discord.Color.green(),
            )

            if self.selected_start:
                start_times = []
                for time in self.selected_start:
                    if time == "24h_before":
                        start_times.append("24 hours before")
                    elif time == "12h_before":
                        start_times.append("12 hours before")
                    elif time == "1h_before":
                        start_times.append("1 hour before")
                embed.add_field(
                    name="Start Time Reminders",
                    value="\n".join(start_times),
                    inline=False,
                )

            if self.selected_end:
                end_times = []
                for time in self.selected_end:
                    if time == "1h_before_end":
                        end_times.append("1 hour before")
                    elif time == "30m_before_end":
                        end_times.append("30 minutes before")
                    elif time == "10m_before_end":
                        end_times.append("10 minutes before")
                embed.add_field(
                    name="End Time Reminders", value="\n".join(end_times), inline=False
                )

            # Send confirmation message
            await interaction.response.send_message(embed=embed, ephemeral=False)

            # Delete original message
            try:
                await interaction.message.delete()
            except discord.NotFound:
                pass  # Message already deleted
            except discord.Forbidden:
                print("No permission to delete message")
            except Exception as e:
                print(f"Error deleting message: {e}")
        else:
            await interaction.response.send_message(
                "❌ Failed to set reminder times", ephemeral=True
            )


@bot.command()
async def setremind(ctx, event_id: str = None):
    """Set reminder times for a competition
    Usage:
    !setremind <event_id> - Set reminder times for the specified competition
    """
    if not event_id:
        await ctx.send("❌ Please provide an event ID")
        return

    event = db.get_event(event_id, str(ctx.guild.id))
    if not event:
        await ctx.send("❌ Competition not found")
        return

    # Check if user has joined the competition
    if not db.is_user_joined(event_id, str(ctx.guild.id), str(ctx.author.id)):
        await ctx.send("❌ You haven't joined this competition")
        return

    view = ReminderSelect(event_id=event_id, event_name=event["name"])
    embed = discord.Embed(
        title="⏰ Set Competition Reminders",
        description=f"Competition: {event['name']}\n\nSelect when you want to receive reminders before the competition starts and ends.\nDefault values if none selected:\nStart: 24 hours and 1 hour before\nEnd: 1 hour and 10 minutes before",
        color=discord.Color.blue(),
    )
    await ctx.send(embed=embed, view=view)


# Run the bot
bot.run(os.getenv("DISCORD_TOKEN"))
