"""
CTF event reminder management commands.
"""

from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks

from database import Database


class Reminder(commands.Cog):
    """CTF event reminder management commands"""

    def __init__(self, bot):
        self.bot = bot
        self.db = Database()
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    @commands.command()
    async def reminderset(self, ctx, event_id: str):
        """Set reminder settings for a CTF event
        Usage:
        !reminderset <event_id> - Set reminder settings for specified CTF event
        """
        # Check if event exists
        event = self.db.get_event(event_id, str(ctx.guild.id))
        if not event:
            await ctx.send("❌ Event not found")
            return

        # Create embed with event info
        embed = discord.Embed(
            title="⏰ Reminder Settings",
            description=f"**Event:** {event['name']}\n**ID:** `{event_id}`",
            color=discord.Color.blue(),
        )

        # Add current settings
        settings = self.db.get_reminder_settings(event_id, str(ctx.guild.id))
        if settings:
            current_settings = (
                f"**Before Start:**\n"
                f"{'✅' if settings['remind_24h_before'] else '❌'} 24 hours\n"
                f"{'✅' if settings['remind_12h_before'] else '❌'} 12 hours\n"
                f"{'✅' if settings['remind_1h_before'] else '❌'} 1 hour\n\n"
                f"**Before End:**\n"
                f"{'✅' if settings['remind_1h_before_end'] else '❌'} 1 hour\n"
                f"{'✅' if settings['remind_30m_before_end'] else '❌'} 30 minutes\n"
                f"{'✅' if settings['remind_10m_before_end'] else '❌'} 10 minutes"
            )
        else:
            current_settings = "No settings configured"

        embed.add_field(name="Current Settings", value=current_settings, inline=False)

        # Create buttons
        class ReminderView(discord.ui.View):
            def __init__(self, db):
                super().__init__(timeout=300)  # 5 minutes timeout
                self.db = db

            @discord.ui.button(
                label="24h before start", style=discord.ButtonStyle.primary
            )
            async def remind_24h(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                self.db.toggle_reminder_setting(
                    event_id, str(interaction.guild.id), "remind_24h_before"
                )
                await self.update_message(interaction)

            @discord.ui.button(
                label="12h before start", style=discord.ButtonStyle.primary
            )
            async def remind_12h(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                self.db.toggle_reminder_setting(
                    event_id, str(interaction.guild.id), "remind_12h_before"
                )
                await self.update_message(interaction)

            @discord.ui.button(
                label="1h before start", style=discord.ButtonStyle.primary
            )
            async def remind_1h(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                self.db.toggle_reminder_setting(
                    event_id, str(interaction.guild.id), "remind_1h_before"
                )
                await self.update_message(interaction)

            @discord.ui.button(label="1h before end", style=discord.ButtonStyle.danger)
            async def remind_1h_end(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                self.db.toggle_reminder_setting(
                    event_id, str(interaction.guild.id), "remind_1h_before_end"
                )
                await self.update_message(interaction)

            @discord.ui.button(label="30m before end", style=discord.ButtonStyle.danger)
            async def remind_30m_end(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                self.db.toggle_reminder_setting(
                    event_id, str(interaction.guild.id), "remind_30m_before_end"
                )
                await self.update_message(interaction)

            @discord.ui.button(label="10m before end", style=discord.ButtonStyle.danger)
            async def remind_10m_end(
                self, interaction: discord.Interaction, button: discord.ui.Button
            ):
                self.db.toggle_reminder_setting(
                    event_id, str(interaction.guild.id), "remind_10m_before_end"
                )
                await self.update_message(interaction)

            async def update_message(self, interaction: discord.Interaction):
                settings = self.db.get_reminder_settings(
                    event_id, str(interaction.guild.id)
                )
                new_settings = (
                    f"**Before Start:**\n"
                    f"{'✅' if settings['remind_24h_before'] else '❌'} 24 hours\n"
                    f"{'✅' if settings['remind_12h_before'] else '❌'} 12 hours\n"
                    f"{'✅' if settings['remind_1h_before'] else '❌'} 1 hour\n\n"
                    f"**Before End:**\n"
                    f"{'✅' if settings['remind_1h_before_end'] else '❌'} 1 hour\n"
                    f"{'✅' if settings['remind_30m_before_end'] else '❌'} 30 minutes\n"
                    f"{'✅' if settings['remind_10m_before_end'] else '❌'} 10 minutes"
                )
                embed.set_field_at(
                    0, name="Current Settings", value=new_settings, inline=False
                )
                await interaction.response.edit_message(embed=embed)

        view = ReminderView(self.db)
        await ctx.send(embed=embed, view=view)

    @tasks.loop(minutes=1)
    async def check_reminders(self):
        """Check and send reminders for upcoming events"""
        try:
            # Get all events
            for guild in self.bot.guilds:
                events = self.db.get_all_events(str(guild.id))
                if not events:
                    continue

                # Get notification channel
                channel_id = self.db.get_notification_channel(str(guild.id))
                if not channel_id:
                    continue

                channel = guild.get_channel(int(channel_id))
                if not channel:
                    continue

                # Check each event
                for event in events:
                    settings = self.db.get_reminder_settings(
                        event["event_id"], str(guild.id)
                    )
                    if not settings:
                        continue

                    start_time = datetime.fromisoformat(event["start_time"])
                    end_time = datetime.fromisoformat(event["end_time"])
                    now = datetime.now(start_time.tzinfo)

                    # Check start time reminders
                    if settings["remind_24h_before"]:
                        self.check_and_send_reminder(
                            channel,
                            event,
                            start_time - timedelta(hours=24),
                            now,
                            "24 hours until start",
                            True,
                        )

                    if settings["remind_12h_before"]:
                        self.check_and_send_reminder(
                            channel,
                            event,
                            start_time - timedelta(hours=12),
                            now,
                            "12 hours until start",
                            True,
                        )

                    if settings["remind_1h_before"]:
                        self.check_and_send_reminder(
                            channel,
                            event,
                            start_time - timedelta(hours=1),
                            now,
                            "1 hour until start",
                            True,
                        )

                    # Check end time reminders
                    if settings["remind_1h_before_end"]:
                        self.check_and_send_reminder(
                            channel,
                            event,
                            end_time - timedelta(hours=1),
                            now,
                            "1 hour until end",
                            False,
                        )

                    if settings["remind_30m_before_end"]:
                        self.check_and_send_reminder(
                            channel,
                            event,
                            end_time - timedelta(minutes=30),
                            now,
                            "30 minutes until end",
                            False,
                        )

                    if settings["remind_10m_before_end"]:
                        self.check_and_send_reminder(
                            channel,
                            event,
                            end_time - timedelta(minutes=10),
                            now,
                            "10 minutes until end",
                            False,
                        )

        except Exception as e:
            print(f"Error checking reminders: {str(e)}")

    async def check_and_send_reminder(
        self, channel, event, target_time, now, message, is_start
    ):
        """Check if it's time to send a reminder and send it if needed"""
        # Check if within 1 minute of target time
        time_diff = abs((target_time - now).total_seconds())
        if time_diff <= 60:  # Within 1 minute
            # Get role mention
            role = discord.utils.get(channel.guild.roles, name=f"CTF-{event['name']}")
            role_mention = role.mention if role else "@everyone"

            # Create embed
            embed = discord.Embed(
                title="⏰ CTF Event Reminder",
                description=f"**{event['name']}**\n{message}",
                color=discord.Color.gold(),
            )

            # Add time information
            if is_start:
                embed.add_field(
                    name="Start Time", value=event["start_time"], inline=False
                )
            else:
                embed.add_field(name="End Time", value=event["end_time"], inline=False)

            # Add links
            if event["official_url"]:
                embed.add_field(
                    name="Official Link", value=event["official_url"], inline=False
                )
            if event["ctftime_url"]:
                embed.add_field(
                    name="CTFtime Link", value=event["ctftime_url"], inline=False
                )

            await channel.send(content=role_mention, embed=embed)

    @check_reminders.before_loop
    async def before_check_reminders(self):
        """Wait until the bot is ready before starting the task"""
        await self.bot.wait_until_ready()


async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(Reminder(bot))
