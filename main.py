import base64
import os
from datetime import datetime, timedelta

import discord
import pytz
import requests
from discord.ext import commands, tasks
from dotenv import load_dotenv

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
    !timezone list - Show common timezone list
    !timezone <timezone> - Set timezone, e.g.: !timezone Asia/Taipei
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
            embed.set_footer(
                text="Use !timezone list to view available timezones | Use !timezone <timezone> to change timezone"
            )
            await ctx.send(embed=embed)
            return

        if timezone_str.lower() == "list":
            # Show common timezone list
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

            embed = discord.Embed(
                title="🌍 Common Timezone List",
                description="Below are common timezone settings, you can use `!timezone <timezone>` to set.",
                color=discord.Color.blue(),
            )

            for region, zones in common_timezones.items():
                value = "\n".join([f"`{zone}`" for zone in zones])
                embed.add_field(name=region, value=value, inline=False)

            embed.set_footer(text="Use !timezone <timezone> to set timezone")
            await ctx.send(embed=embed)
            return

        # Validate timezone
        try:
            tz = pytz.timezone(timezone_str)
            # Test if timezone is valid
            datetime.now(tz)
        except pytz.exceptions.UnknownTimeZoneError:
            await ctx.send(
                "❌ Invalid timezone! Please use `!timezone list` to view available timezones"
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


@tasks.loop(minutes=60)  # Check every 60 minutes
async def check_ctf_events():
    """Check CTF competition times and send reminders"""
    try:
        for guild in bot.guilds:
            events = db.get_all_events(str(guild.id))
            # Use UTC time
            now = datetime.now(pytz.UTC)

            for event in events:
                start_time = datetime.fromisoformat(event["start_time"])
                end_time = datetime.fromisoformat(event["end_time"])

                # Skip if competition has ended
                if now > end_time:
                    continue

                # Get role
                role_name = f"CTF-{event['name']}"
                role = discord.utils.get(guild.roles, name=role_name)
                if not role:
                    continue

                # Calculate time difference
                time_diff = start_time - now

                # Check if it's reminder time
                if (
                    timedelta(hours=23) <= time_diff <= timedelta(hours=24)
                ):  # One day before start
                    # Find system notification channel
                    system_channel = guild.system_channel
                    if system_channel:
                        embed = discord.Embed(
                            title="⏰ CTF Competition Starting Soon",
                            description=f"{role.mention} Competition starts tomorrow!",
                            color=discord.Color.orange(),
                        )
                        embed.add_field(
                            name="Competition Name", value=event["name"], inline=False
                        )

                        # Get all participants' timezones
                        participants = db.get_event_participants(
                            event["event_id"], str(guild.id)
                        )
                        for participant in participants:
                            user_id = participant["user_id"]
                            local_start = convert_to_user_timezone(
                                start_time, user_id, str(guild.id)
                            )
                            local_end = convert_to_user_timezone(
                                end_time, user_id, str(guild.id)
                            )

                            embed.add_field(
                                name=f"Start Time ({local_start.tzinfo})",
                                value=local_start.strftime("%Y-%m-%d %H:%M"),
                                inline=True,
                            )
                            embed.add_field(
                                name=f"End Time ({local_end.tzinfo})",
                                value=local_end.strftime("%Y-%m-%d %H:%M"),
                                inline=True,
                            )

                        if event["official_url"]:
                            embed.add_field(
                                name="Official Link",
                                value=event["official_url"],
                                inline=False,
                            )
                        await system_channel.send(embed=embed)

                elif (
                    timedelta(minutes=0) <= time_diff <= timedelta(minutes=5)
                ):  # At start time
                    # Find system notification channel
                    system_channel = guild.system_channel
                    if system_channel:
                        embed = discord.Embed(
                            title="🚀 CTF Competition Started",
                            description=f"{role.mention} Competition has started!",
                            color=discord.Color.green(),
                        )
                        embed.add_field(
                            name="Competition Name", value=event["name"], inline=False
                        )

                        # Get all participants' timezones
                        participants = db.get_event_participants(
                            event["event_id"], str(guild.id)
                        )
                        for participant in participants:
                            user_id = participant["user_id"]
                            local_end = convert_to_user_timezone(
                                end_time, user_id, str(guild.id)
                            )

                            embed.add_field(
                                name=f"End Time ({local_end.tzinfo})",
                                value=local_end.strftime("%Y-%m-%d %H:%M"),
                                inline=True,
                            )

                        if event["official_url"]:
                            embed.add_field(
                                name="Official Link",
                                value=event["official_url"],
                                inline=False,
                            )
                        await system_channel.send(embed=embed)

    except Exception as e:
        print(f"Error checking CTF competitions: {str(e)}")


@bot.event
async def on_ready():
    print(f"{bot.user} has successfully started!")
    # Start scheduled check task (if not already running)
    if not check_ctf_events.is_running():
        check_ctf_events.start()


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
async def addctf(ctx, event_id: str):
    """Add CTF competition to reminder list
    Usage:
    !addctf <ctftime_event_id> - Add specified CTF competition to reminder list
    """
    try:
        # Check if already added
        existing_event = db.get_event(event_id, str(ctx.guild.id))
        if existing_event:
            await ctx.send("❌ This competition has already been added!")
            return

        # Get competition info from CTFtime API
        event_url = f"https://ctftime.org/api/v1/events/{event_id}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # Increase retry count and timeout
        for attempt in range(3):  # Max 3 retries
            try:
                response = requests.get(
                    event_url, headers=headers, timeout=30
                )  # Increase timeout to 30 seconds
                response.raise_for_status()
                event = response.json()
                break
            except requests.Timeout:
                if attempt == 2:  # Last attempt
                    await ctx.send(
                        "❌ Connection to CTFtime timed out, please try again later"
                    )
                    return
                continue
            except requests.RequestException as e:
                if attempt == 2:  # Last attempt
                    await ctx.send(f"❌ Error getting CTFtime API info: {str(e)}")
                    return
                continue

        # Parse time
        start_time = datetime.fromisoformat(event.get("start").replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(event.get("finish").replace("Z", "+00:00"))

        # Prepare database data
        event_data = {
            "event_id": event_id,
            "name": event.get("title", "Unknown"),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "event_type": event.get("format", "Unknown"),
            "weight": float(event.get("weight", 0)),
            "location": event.get("location", "Online"),
            "official_url": event.get("url", ""),
            "ctftime_url": event.get("ctftime_url", ""),
        }

        # Save to database
        if not db.add_event(event_data, str(ctx.guild.id)):
            await ctx.send("❌ Error saving competition info")
            return

        # Create role
        try:
            role = await ctx.guild.create_role(
                name=f"CTF-{event_data['name']}",
                color=discord.Color.blue(),
                reason=f"Creating role for CTF competition {event_data['name']}",
            )
            await ctx.send(f"✅ Role created: {role.mention}")
        except discord.Forbidden:
            await ctx.send("❌ No permission to create roles")
        except Exception as e:
            await ctx.send(f"❌ Error creating role: {str(e)}")

        # Create embed
        embed = discord.Embed(
            title="🎯 CTF Competition Added", color=discord.Color.blue()
        )

        # Add competition info
        embed.add_field(name="Competition Name", value=event_data["name"], inline=False)
        embed.add_field(
            name="Start Time", value=start_time.strftime("%Y-%m-%d %H:%M"), inline=True
        )
        embed.add_field(
            name="End Time", value=end_time.strftime("%Y-%m-%d %H:%M"), inline=True
        )
        embed.add_field(name="Type", value=event_data["event_type"], inline=True)
        embed.add_field(name="Weight", value=str(event_data["weight"]), inline=True)
        embed.add_field(name="Location", value=event_data["location"], inline=True)

        # Add links
        if event_data["official_url"]:
            embed.add_field(
                name="Official Link", value=event_data["official_url"], inline=False
            )
        if event_data["ctftime_url"]:
            embed.add_field(
                name="CTFtime Link", value=event_data["ctftime_url"], inline=False
            )

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Error occurred: {str(e)}")


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

        # Calculate remaining time (ensure timezone consistency)
        now = datetime.now(start_time.tzinfo)
        time_left = start_time - now

        # Set status and color
        if now > end_time:
            status = "Ended"
            color = "🔴"
        elif now > start_time:
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
            f"**ID:** `{event['event_id']}`\n"
            f"**Start Time:** {start_time.strftime('%Y-%m-%d %H:%M')}\n"
            f"**End Time:** {end_time.strftime('%Y-%m-%d %H:%M')}\n"
            f"**Type:** {event['event_type']}\n"
            f"**Weight:** {event['weight']}\n"
            f"**Location:** {event['location']}\n"
            f"**Status:** {color} {status}"
        )

        # Add links
        if event["official_url"]:
            value += f"\n**Official Link:** {event['official_url']}"
        if event["ctftime_url"]:
            value += f"\n**CTFtime:** {event['ctftime_url']}"

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

    if db.delete_event(event_id, str(ctx.guild.id)):
        embed = discord.Embed(
            title="🗑️ CTF Competition Deleted", color=discord.Color.red()
        )
        embed.add_field(name="Competition Name", value=event["name"], inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ Error deleting competition")


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

        # Join competition
        if db.join_event(event_id, str(ctx.guild.id), str(ctx.author.id)):
            # Find corresponding role
            role_name = f"CTF-{event['name']}"
            role = discord.utils.get(ctx.guild.roles, name=role_name)

            if role:
                try:
                    await ctx.author.add_roles(role)
                    await ctx.send(f"✅ Role added: {role.mention}")
                except discord.Forbidden:
                    await ctx.send("❌ No permission to add roles")
                except Exception as e:
                    await ctx.send(f"❌ Error adding role: {str(e)}")
            else:
                await ctx.send("⚠️ Corresponding role not found")

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

            # Calculate remaining time (ensure timezone consistency)
            now = datetime.now(start_time.tzinfo)
            time_left = start_time - now

            # Set status and color
            if now > end_time:
                status = "Ended"
                color = "🔴"
            elif now > start_time:
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
                f"**ID:** `{event['event_id']}`\n"
                f"**Start Time:** {start_time.strftime('%Y-%m-%d %H:%M')}\n"
                f"**End Time:** {end_time.strftime('%Y-%m-%d %H:%M')}\n"
                f"**Type:** {event['event_type']}\n"
                f"**Weight:** {event['weight']}\n"
                f"**Location:** {event['location']}\n"
                f"**Status:** {color} {status}"
            )

            # Add links
            if event["official_url"]:
                value += f"\n**Official Link:** {event['official_url']}"
            if event["ctftime_url"]:
                value += f"\n**CTFtime:** {event['ctftime_url']}"

            # Add separator
            if i < len(events):
                value += "\n\n" + "─" * 30

            main_embed.add_field(name=f"🏆 {event['name']}", value=value, inline=False)

        await ctx.send(embed=main_embed)

    except Exception as e:
        await ctx.send(f"❌ Error occurred: {str(e)}")


# 运行 bot
bot.run(os.getenv("DISCORD_TOKEN"))
