"""
CTF event reminder management commands.
"""

import pytz
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks

from database import Database

class ReminderSelect(discord.ui.View):
    def __init__(self, event_id: str, event_name: str):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.event_id = event_id
        self.event_name = event_name
        self.selected_start = []
        self.selected_end = []
        self.db = Database()  # Initialize database connection

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
        if self.db.set_reminder_settings(
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

class Reminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = Database()

    def convert_to_user_timezone(self, dt: datetime, user_id: str, guild_id: str) -> datetime:
        """Convert UTC time to user's timezone"""
        try:
            user_tz = self.db.get_user_timezone(user_id, guild_id)
            tz = pytz.timezone(user_tz)
            return dt.astimezone(tz)
        except Exception:
            return dt
        
    @tasks.loop(minutes=1)  # Check every minute
    async def check_ctf_events(self):
        """Check CTF competition times and send reminders"""
        try:
            for guild in self.bot.guilds:
                events = self.db.get_all_events(str(guild.id))
                now = datetime.now(pytz.UTC)

                for event in events:
                    start_time = datetime.fromisoformat(event["start_time"])
                    end_time = datetime.fromisoformat(event["end_time"])

                    # 跳過已結束的比賽
                    if now > end_time:
                        continue

                    # 取得該比賽的所有參與者
                    participants = self.db.get_event_participants(
                        event["event_id"], str(guild.id)
                    )

                    for participant in participants:
                        user_id = participant["user_id"]

                        # 取得使用者的提醒設定
                        before_start, before_end = self.db.get_reminder_settings(
                            event["event_id"], str(guild.id), user_id
                        )
                        if not before_start and not before_end:
                            # 使用預設值
                            before_start = "24h_before,1h_before"
                            before_end = "1h_before_end,10m_before_end"

                        # 轉換時間到使用者時區
                        user_start_time = self.convert_to_user_timezone(
                            start_time, user_id, str(guild.id)
                        )
                        user_end_time = self.convert_to_user_timezone(
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
                                        await self.send_reminder(
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
                                        await self.send_reminder(
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
                                        await self.send_reminder(
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
                                        await self.send_reminder(
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
                                        await self.send_reminder(
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
                                        await self.send_reminder(
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
            self,guild, user_id, event, time_str, start_time, end_time, is_end=False
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
                channel_id = self.db.get_notification_channel(str(guild.id))
                if channel_id:
                    channel = guild.get_channel(int(channel_id))
                    if channel:
                        await channel.send(f"{member.mention}", embed=embed)
        except Exception as e:
            print(f"Error sending reminder: {e}")

    @commands.command()
    async def setremind(self,ctx, event_id: str = None):
        """Set reminder times for a competition
        Usage:
        !setremind <event_id> - Set reminder times for the specified competition
        """
        if not event_id:
            await ctx.send("❌ Please provide an event ID")
            return

        event = self.db.get_event(event_id, str(ctx.guild.id))
        if not event:
            await ctx.send("❌ Competition not found")
            return

        # Check if user has joined the competition
        if not self.db.is_user_joined(event_id, str(ctx.guild.id), str(ctx.author.id)):
            await ctx.send("❌ You haven't joined this competition")
            return

        view = ReminderSelect(event_id=event_id, event_name=event["name"])
        embed = discord.Embed(
            title="⏰ Set Competition Reminders",
            description=f"Competition: {event['name']}\n\nSelect when you want to receive reminders before the competition starts and ends.\nDefault values if none selected:\nStart: 24 hours and 1 hour before\nEnd: 1 hour and 10 minutes before",
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed, view=view)


async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(Reminder(bot))
