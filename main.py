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
    loading_msg = await ctx.send("⏳ Getting competition information...")

    try:
        # Get competition info
        event = await get_ctf_event(event_id)
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
            # Get user timezone
            user_timezone = db.get_user_timezone(str(ctx.author.id), str(ctx.guild.id))
            # Create role
            try:
                role = await ctx.guild.create_role(
                    name=f"CTF-{event['title']}",
                    color=discord.Color.blue(),
                    reason=f"Creating role for CTF competition {event['title']}",
                )
                await ctx.send(f"✅ Role created: {role.mention}")
            except discord.Forbidden:
                await ctx.send("❌ No permission to create roles")
            except Exception as e:
                await ctx.send(f"❌ Error creating role: {str(e)}")
            if not user_timezone:
                user_timezone = "UTC"

            # Convert time to user timezone
            start_time = convert_to_user_timezone(
                datetime.fromisoformat(event["start"]), user_timezone, str(ctx.guild.id)
            )
            end_time = convert_to_user_timezone(
                datetime.fromisoformat(event["finish"]),
                user_timezone,
                str(ctx.guild.id),
            )

            # Create embed
            embed = discord.Embed(
                title="🎯 CTF Competition Added",
                description=f"**Competition Name:**\n{event['title']}\n\n**ID:** `{event_id}`",
                color=discord.Color.blue(),
            )

            # Add time information
            time_info = (
                f"**Start Time:**\n{start_time.strftime('%Y-%m-%d %H:%M')} ({start_time.tzinfo})\n\n"
                f"**End Time:**\n{end_time.strftime('%Y-%m-%d %H:%M')} ({end_time.tzinfo})"
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
                f"**CTFTime Link:**\n[Click to Visit]({event['ctftime_url']})"
            )
            embed.add_field(name="🔗 Links", value=links, inline=False)

            # Add footer
            embed.set_footer(text="Use !joinctf <id> to join this competition")

            # Update loading message to success message
            await loading_msg.edit(content=None, embed=embed)
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


# Run the bot
bot.run(os.getenv("DISCORD_TOKEN"))
