"""
CTF competition management commands.
"""

from datetime import datetime

import discord
import pytz
from discord.ext import commands, tasks

from ctftime_api import get_event, get_team_events
from database import Database


class CTFButtons(discord.ui.View):
    def __init__(self, event_id: str, event_name: str):
        super().__init__(timeout=None)  # Buttons will not timeout
        self.event_id = event_id
        self.event_name = event_name
        self.db = Database()  # Initialize database connection

    @discord.ui.button(label="Join CTF", style=discord.ButtonStyle.green, emoji="✅")
    async def join_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        try:
            # Check if user already joined
            if self.db.is_user_joined(
                self.event_id, str(interaction.guild_id), str(interaction.user.id)
            ):
                await interaction.response.send_message(
                    f"❌ You have already joined {self.event_name}!", ephemeral=True
                )
                return

            # Join competition
            if self.db.join_event(
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
                event = self.db.get_event(self.event_id, str(interaction.guild_id))
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
            if not self.db.is_user_joined(
                self.event_id, str(interaction.guild_id), str(interaction.user.id)
            ):
                await interaction.response.send_message(
                    f"❌ You haven't joined {self.event_name}!", ephemeral=True
                )
                return

            # Leave competition
            if self.db.leave_event(
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


class CTF(commands.Cog):
    """CTF competition management commands"""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.check_team_events.start()
        self.check_ended_events.start()

    def cog_unload(self):
        self.check_team_events.cancel()
        self.check_ended_events.cancel()

    @commands.command()
    async def addctf(self, ctx, event_id: str):
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
            if self.db.get_event(event_id, str(ctx.guild.id)):
                await loading_msg.edit(
                    content="❌ This competition has already been added"
                )
                return

            # Add competition to database
            if self.db.add_event(
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
                embed.add_field(
                    name="⏰ Time Information", value=time_info, inline=False
                )

                # Add competition details
                details = (
                    f"**Type:** {event['format']}\n**Weight:** {event['weight']}\n"
                )
                if event["location"]:
                    details += f"**Location:** {event['location']}\n"
                embed.add_field(
                    name="📋 Competition Details", value=details, inline=False
                )

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
                channel_id = self.db.get_notification_channel(str(ctx.guild.id))
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
                                # await loading_msg.delete()
                                print("delete loading msg")
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

    @commands.command()
    async def delctf(self, ctx, event_id: str):
        """Delete specified CTF competition
        Usage:
        !delctf <ctftime_event_id> - Delete specified CTF competition
        """
        event = self.db.get_event(event_id, str(ctx.guild.id))
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
        channel_id = self.db.get_notification_channel(str(ctx.guild.id))
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

        if self.db.delete_event(event_id, str(ctx.guild.id)):
            embed = discord.Embed(
                title="🗑️ CTF Competition Deleted", color=discord.Color.red()
            )
            embed.add_field(name="Competition Name", value=event["name"], inline=False)
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Error deleting competition")

    @commands.command()
    async def listctf(self, ctx):
        """List all added CTF competitions"""
        events = self.db.get_all_events(str(ctx.guild.id))

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
            user_start_time = self.convert_to_user_timezone(
                start_time, str(ctx.author.id), str(ctx.guild.id)
            )
            user_end_time = self.convert_to_user_timezone(
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

    @commands.command()
    async def joinctf(self, ctx, event_id: str):
        """Join CTF competition
        Usage:
        !joinctf <ctftime_event_id> - Join specified CTF competition
        """
        try:
            # Check if competition exists
            event = self.db.get_event(event_id, str(ctx.guild.id))
            if not event:
                await ctx.send(
                    "❌ Competition not found, please use !addctf to add it first"
                )
                return

            # Check if user already joined
            if self.db.is_user_joined(event_id, str(ctx.guild.id), str(ctx.author.id)):
                embed = discord.Embed(
                    title="ℹ️ Already Joined",
                    description=f"You have already joined this competition: {event['name']}",
                    color=discord.Color.blue(),
                )
                await ctx.send(embed=embed)
                return

            # Join competition
            if self.db.join_event(event_id, str(ctx.guild.id), str(ctx.author.id)):
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
                    title="✅ Successfully Joined Competition",
                    color=discord.Color.green(),
                )
                embed.add_field(
                    name="Competition Name", value=event["name"], inline=False
                )
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
                        embed.add_field(
                            name="Invite Link", value=invite_link, inline=False
                        )
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

    @commands.command()
    async def leavectf(self, ctx, event_id: str):
        """Leave CTF competition
        Usage:
        !leavectf <ctftime_event_id> - Leave specified CTF competition
        """
        try:
            # Check if competition exists
            event = self.db.get_event(event_id, str(ctx.guild.id))
            if not event:
                await ctx.send("❌ Competition not found")
                return

            # Leave competition
            if self.db.leave_event(event_id, str(ctx.guild.id), str(ctx.author.id)):
                embed = discord.Embed(
                    title="✅ Successfully Left Competition", color=discord.Color.blue()
                )
                embed.add_field(
                    name="Competition Name", value=event["name"], inline=False
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Error leaving competition")
        except Exception as e:
            await ctx.send(f"❌ Error occurred: {str(e)}")

    @commands.command()
    # @commands.has_permissions(administrator=True)
    async def invitectf(self, ctx, event_id: str, invite_link: str = None):
        """Set or view competition invite link"""
        event = self.db.get_event(event_id, str(ctx.guild.id))
        if not event:
            await ctx.send(
                "❌ Competition not found, please add it first using !addctf"
            )
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
                    await ctx.send(
                        "❌ Cannot send DM, please check your privacy settings"
                    )
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
            if self.db.set_event_invite_link(event_id, str(ctx.guild.id), invite_link):
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
                    await ctx.send(
                        "❌ Cannot send DM, please check your privacy settings"
                    )
            else:
                try:
                    await ctx.author.send("❌ Failed to set invite link")
                except discord.Forbidden:
                    await ctx.send(
                        "❌ Cannot send DM, please check your privacy settings"
                    )

    @commands.command()
    async def myctf(self, ctx):
        """View all CTF competitions you're participating in"""
        try:
            events = self.db.get_user_events(str(ctx.guild.id), str(ctx.author.id))

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
                user_start_time = self.convert_to_user_timezone(
                    start_time, str(ctx.author.id), str(ctx.guild.id)
                )
                user_end_time = self.convert_to_user_timezone(
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

                main_embed.add_field(
                    name=f"🏆 {event['name']}", value=value, inline=False
                )

            await ctx.send(embed=main_embed)

        except Exception as e:
            await ctx.send(f"❌ Error occurred: {str(e)}")

    @commands.command()
    async def participants(self, ctx, event_id: str):
        """View competition participants
        Usage:
        !participants <ctftime_event_id> - Show list of participants for the specified competition
        """
        try:
            # Check if competition exists
            event = self.db.get_event(event_id, str(ctx.guild.id))
            if not event:
                await ctx.send(
                    "❌ Competition not found, please use !addctf to add it first"
                )
                return

            # Get participants list
            participants = self.db.get_event_participants(event_id, str(ctx.guild.id))

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
                    user_join_time = self.convert_to_user_timezone(
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
            user_start_time = self.convert_to_user_timezone(
                start_time, str(ctx.author.id), str(ctx.guild.id)
            )
            user_end_time = self.convert_to_user_timezone(
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

    @tasks.loop(hours=1)
    async def check_team_events(self):
        """Check team's planned CTF events and add them automatically"""
        try:
            for guild in self.bot.guilds:
                team_id = self.db.get_ctftime_team_id(str(guild.id))
                if not team_id:
                    continue

                # Get team's planned events
                planned_events = get_team_events(team_id)
                if not planned_events:
                    continue

                # Get notification channel
                channel_id = self.db.get_notification_channel(str(guild.id))
                if not channel_id:
                    continue

                channel = guild.get_channel(int(channel_id))
                if not channel:
                    continue

                # Check each planned event
                for event in planned_events:
                    # Check if event already exists
                    if self.db.get_event(event["id"], str(guild.id)):
                        continue

                    # Get event details
                    event_details = await get_event(event["id"])
                    if not event_details:
                        continue

                    # Add event to database
                    if self.db.add_event(
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

                        # Create view with buttons
                        view = CTFButtons(
                            event_id=event["id"], event_name=event["title"]
                        )

                        await channel.send(embed=embed,view=view)

        except Exception as e:
            print(f"Error checking team events: {str(e)}")

    @check_team_events.before_loop
    async def before_check_team_events(self):
        """Wait until the bot is ready before starting the task"""
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)  # Check every hour
    async def check_ended_events(self):
        """Check for ended events and clean up roles"""
        try:
            # Get all guilds
            for guild in self.bot.guilds:
                # Get all events for this guild
                events = self.db.get_all_events(str(guild.id))

                for event in events:
                    # Check if event has ended
                    end_time = datetime.fromisoformat(event["end_time"])
                    if datetime.now(end_time.tzinfo) > end_time:
                        # Find and delete corresponding role
                        role_name = f"CTF-{event['name']}"
                        role = discord.utils.get(guild.roles, name=role_name)

                        if role:
                            try:
                                await role.delete(
                                    reason=f"Automatically deleting role for ended CTF competition {event['name']}"
                                )
                                print(
                                    f"✅ Automatically deleted role {role_name} for ended competition in guild {guild.id}"
                                )
                            except discord.Forbidden:
                                print(
                                    f"❌ No permission to delete role in guild {guild.id}"
                                )
                            except Exception as e:
                                print(f"❌ Error deleting role: {e}")

                        # Delete the event from database
                        self.db.delete_event(event["event_id"], str(guild.id))

        except Exception as e:
            print(f"Error in check_ended_events: {e}")

    @check_ended_events.before_loop
    async def before_check_ended_events(self):
        """Wait until the bot is ready before starting the task"""
        await self.bot.wait_until_ready()

    def convert_to_user_timezone(
        self, dt: datetime, user_id: str, guild_id: str
    ) -> datetime:
        """Convert UTC time to user's timezone"""
        try:
            user_tz = self.db.get_user_timezone(user_id, guild_id)
            tz = pytz.timezone(user_tz)
            return dt.astimezone(tz)
        except Exception:
            return dt


async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(CTF(bot))
