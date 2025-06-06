import sqlite3
from datetime import datetime


class Database:
    def __init__(self, db_file="ctf_events.db"):
        self.db_file = db_file
        self.init_db()

    def init_db(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        # Check if database migration is needed
        c.execute("PRAGMA table_info(ctf_events)")
        columns = [column[1] for column in c.fetchall()]

        # Create CTF events table
        c.execute("""
            CREATE TABLE IF NOT EXISTS ctf_events (
                event_id TEXT,
                guild_id TEXT,
                name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                event_type TEXT,
                weight REAL,
                location TEXT,
                official_url TEXT,
                ctftime_url TEXT,
                invite_link TEXT,
                added_time TEXT NOT NULL,
                added_by TEXT,
                PRIMARY KEY (event_id, guild_id)
            )
        """)

        # Create guild_settings table
        c.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id TEXT PRIMARY KEY,
                notification_channel_id TEXT,
                ctftime_team_id TEXT
            )
        """)

        # Check if guild_settings table has ctftime_team_id column
        c.execute("PRAGMA table_info(guild_settings)")
        guild_settings_columns = [column[1] for column in c.fetchall()]
        if "ctftime_team_id" not in guild_settings_columns:
            try:
                c.execute("ALTER TABLE guild_settings ADD COLUMN ctftime_team_id TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                # Column might already exist, ignore error
                pass

        # If table exists but doesn't have invite_link column, add it
        if "invite_link" not in columns:
            try:
                c.execute("ALTER TABLE ctf_events ADD COLUMN invite_link TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                # Column might already exist, ignore error
                pass

        # If table exists but doesn't have added_by column, add it
        if "added_by" not in columns:
            try:
                c.execute("ALTER TABLE ctf_events ADD COLUMN added_by TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                # Column might already exist, ignore error
                pass

        # Create event participants table
        c.execute("""
            CREATE TABLE IF NOT EXISTS event_participants (
                event_id TEXT,
                guild_id TEXT,
                user_id TEXT,
                join_time TEXT NOT NULL,
                PRIMARY KEY (event_id, guild_id, user_id),
                FOREIGN KEY (event_id, guild_id) REFERENCES ctf_events (event_id, guild_id)
            )
        """)

        # Create reminder_settings table
        c.execute("""
            CREATE TABLE IF NOT EXISTS reminder_settings (
                event_id TEXT,
                guild_id TEXT,
                user_id TEXT,
                before_start TEXT,
                before_end TEXT,
                PRIMARY KEY (event_id, guild_id, user_id),
                FOREIGN KEY (event_id, guild_id) REFERENCES ctf_events (event_id, guild_id)
            )
        """)

        # Create user timezones table
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_timezones (
                user_id TEXT,
                guild_id TEXT,
                timezone TEXT NOT NULL,
                updated_time TEXT NOT NULL,
                PRIMARY KEY (user_id, guild_id)
            )
        """)

        conn.commit()
        conn.close()

    def add_event(
        self,
        event_id: str,
        guild_id: str,
        name: str,
        start_time: str,
        end_time: str,
        event_type: str,
        weight: float,
        location: str,
        official_url: str,
        ctftime_url: str,
        added_by: str,
    ) -> bool:
        """Add a new CTF event"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                """
                INSERT INTO ctf_events (
                    event_id, guild_id, name, start_time, end_time,
                    event_type, weight, location, official_url, ctftime_url,
                    invite_link, added_time, added_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    guild_id,
                    name,
                    start_time,
                    end_time,
                    event_type,
                    weight,
                    location,
                    official_url,
                    ctftime_url,
                    "",  # Empty invite link
                    datetime.now().isoformat(),  # Current time as added time
                    added_by,  # Adder's ID
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error adding event: {e}")
            return False
        finally:
            conn.close()

    def join_event(self, event_id: str, guild_id: str, user_id: str) -> bool:
        """Join an event"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            # Check if event exists
            c.execute(
                "SELECT 1 FROM ctf_events WHERE event_id = ? AND guild_id = ?",
                (event_id, guild_id),
            )
            if not c.fetchone():
                return False

            # Check if user already joined
            c.execute(
                "SELECT 1 FROM event_participants WHERE event_id = ? AND guild_id = ? AND user_id = ?",
                (event_id, guild_id, user_id),
            )
            if c.fetchone():
                return True  # User already joined, return success

            # Add user participation record
            c.execute(
                """
                INSERT INTO event_participants 
                (event_id, guild_id, user_id, join_time)
                VALUES (?, ?, ?, ?)
                """,
                (event_id, guild_id, user_id, datetime.now().isoformat()),
            )

            conn.commit()
            return True
        except Exception as e:
            print(f"Error joining event: {e}")
            return False
        finally:
            conn.close()

    def leave_event(self, event_id: str, guild_id: str, user_id: str) -> bool:
        """Leave an event"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                """
                DELETE FROM event_participants 
                WHERE event_id = ? AND guild_id = ? AND user_id = ?
                """,
                (event_id, guild_id, user_id),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error leaving event: {e}")
            return False
        finally:
            conn.close()

    def get_event_participants(self, event_id: str, guild_id: str) -> list:
        """Get all participants of an event"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute(
            """
            SELECT user_id, join_time 
            FROM event_participants 
            WHERE event_id = ? AND guild_id = ?
            ORDER BY join_time
        """,
            (event_id, guild_id),
        )

        participants = c.fetchall()
        conn.close()

        return [{"user_id": p[0], "join_time": p[1]} for p in participants]

    def get_user_events(self, guild_id: str, user_id: str) -> list:
        """Get all events a user is participating in"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute(
            """
            SELECT e.* 
            FROM ctf_events e
            JOIN event_participants p ON e.event_id = p.event_id AND e.guild_id = p.guild_id
            WHERE p.guild_id = ? AND p.user_id = ?
            ORDER BY e.start_time
        """,
            (guild_id, user_id),
        )

        events = c.fetchall()
        conn.close()

        return [
            {
                "event_id": event[0],
                "guild_id": event[1],
                "name": event[2],
                "start_time": event[3],
                "end_time": event[4],
                "event_type": event[5],
                "weight": event[6],
                "location": event[7],
                "official_url": event[8],
                "ctftime_url": event[9],
                "invite_link": event[10],
                "added_time": event[11],
                "added_by": event[12] if len(event) >= 13 else None,
            }
            for event in events
        ]

    def get_event(self, event_id: str, guild_id: str):
        """Get event by ID"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                "SELECT * FROM ctf_events WHERE event_id = ? AND guild_id = ?",
                (event_id, guild_id),
            )
            event = c.fetchone()

            if event:
                # Check number of returned fields
                return {
                    "event_id": event[0],
                    "guild_id": event[1],
                    "name": event[2],
                    "start_time": event[3],
                    "end_time": event[4],
                    "event_type": event[5],
                    "weight": event[6],
                    "location": event[7],
                    "official_url": event[8],
                    "ctftime_url": event[9],
                    "invite_link": event[10] if len(event) >= 12 else "",
                    "added_time": event[11] if len(event) >= 12 else event[10],
                    "added_by": event[12] if len(event) >= 13 else None,
                }
            return None
        except Exception as e:
            print(f"Error getting event: {e}")
            return None
        finally:
            conn.close()

    def get_all_events(self, guild_id: str):
        """Get all events for a guild"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                "SELECT * FROM ctf_events WHERE guild_id = ? ORDER BY start_time",
                (guild_id,),
            )
            events = c.fetchall()

            return [
                {
                    "event_id": event[0],
                    "guild_id": event[1],
                    "name": event[2],
                    "start_time": event[3],
                    "end_time": event[4],
                    "event_type": event[5],
                    "weight": event[6],
                    "location": event[7],
                    "official_url": event[8],
                    "ctftime_url": event[9],
                    "invite_link": event[10] if len(event) >= 12 else "",
                    "added_time": event[11] if len(event) >= 12 else event[10],
                    "added_by": event[12] if len(event) >= 13 else None,
                }
                for event in events
            ]
        except Exception as e:
            print(f"Error getting all events: {e}")
            return []
        finally:
            conn.close()

    def delete_event(self, event_id: str, guild_id: str):
        """Delete event by ID"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                "DELETE FROM ctf_events WHERE event_id = ? AND guild_id = ?",
                (event_id, guild_id),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting event: {e}")
            return False
        finally:
            conn.close()

    def set_user_timezone(self, user_id: str, guild_id: str, timezone: str) -> bool:
        """Set user timezone setting"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                """
                INSERT OR REPLACE INTO user_timezones 
                (user_id, guild_id, timezone, updated_time)
                VALUES (?, ?, ?, ?)
            """,
                (user_id, guild_id, timezone, datetime.now().isoformat()),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error setting user timezone: {e}")
            return False
        finally:
            conn.close()

    def get_user_timezone(self, user_id: str, guild_id: str) -> str:
        """Get user timezone setting"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute(
            "SELECT timezone FROM user_timezones WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id),
        )
        result = c.fetchone()

        conn.close()

        return result[0] if result else "UTC"

    def set_event_invite_link(
        self, event_id: str, guild_id: str, invite_link: str
    ) -> bool:
        """Set invite link for an event"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            # Ensure invite_link is not None
            invite_link = invite_link or ""

            c.execute(
                """
                UPDATE ctf_events 
                SET invite_link = ? 
                WHERE event_id = ? AND guild_id = ?
                """,
                (invite_link, event_id, guild_id),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error setting invite link: {e}")
            return False
        finally:
            conn.close()

    def is_user_joined(self, event_id: str, guild_id: str, user_id: str) -> bool:
        """Check if user has already joined an event"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                """
                SELECT 1 FROM event_participants 
                WHERE event_id = ? AND guild_id = ? AND user_id = ?
                """,
                (event_id, guild_id, user_id),
            )
            return bool(c.fetchone())
        except Exception as e:
            print(f"Error checking user join status: {e}")
            return False
        finally:
            conn.close()

    def set_notification_channel(self, guild_id: str, channel_id: str) -> bool:
        """Set notification channel for a guild"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                """
                INSERT OR REPLACE INTO guild_settings (guild_id, notification_channel_id)
                VALUES (?, ?)
                """,
                (guild_id, channel_id),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error setting notification channel: {e}")
            return False
        finally:
            conn.close()

    def get_notification_channel(self, guild_id: str) -> str:
        """Get notification channel ID for a guild"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                "SELECT notification_channel_id FROM guild_settings WHERE guild_id = ?",
                (guild_id,),
            )
            result = c.fetchone()
            return result[0] if result else None
        except Exception as e:
            print(f"Error getting notification channel: {e}")
            return None
        finally:
            conn.close()

    def set_ctftime_team_id(self, guild_id: str, team_id: str) -> bool:
        """Set CTFtime team ID for a guild"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                """
                UPDATE guild_settings 
                SET ctftime_team_id = ? 
                WHERE guild_id = ?
                """,
                (team_id, guild_id),
            )
            if c.rowcount == 0:
                # If no row was updated, insert a new one
                c.execute(
                    """
                    INSERT INTO guild_settings (guild_id, ctftime_team_id)
                    VALUES (?, ?)
                    """,
                    (guild_id, team_id),
                )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error setting CTFtime team ID: {e}")
            return False
        finally:
            conn.close()

    def get_ctftime_team_id(self, guild_id: str) -> str:
        """Get CTFtime team ID for a guild"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                "SELECT ctftime_team_id FROM guild_settings WHERE guild_id = ?",
                (guild_id,),
            )
            result = c.fetchone()
            return result[0] if result else None
        except Exception as e:
            print(f"Error getting CTFtime team ID: {e}")
            return None
        finally:
            conn.close()

    def set_reminder_settings(
        self,
        event_id: str,
        guild_id: str,
        user_id: str,
        before_start: str,
        before_end: str,
    ) -> bool:
        """Set reminder settings for a user in an event"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                """
                INSERT OR REPLACE INTO reminder_settings (event_id, guild_id, user_id, before_start, before_end)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, guild_id, user_id, before_start, before_end),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error setting reminder settings: {e}")
            return False
        finally:
            conn.close()

    def get_reminder_settings(
        self, event_id: str, guild_id: str, user_id: str
    ) -> tuple:
        """Get reminder settings for a user in an event"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                """
                SELECT before_start, before_end FROM reminder_settings 
                WHERE event_id = ? AND guild_id = ? AND user_id = ?
                """,
                (event_id, guild_id, user_id),
            )
            result = c.fetchone()
            return result if result else (None, None)
        except Exception as e:
            print(f"Error getting reminder settings: {e}")
            return None, None
        finally:
            conn.close()

    def get_all_reminder_settings(self) -> list:
        """Get all reminder settings"""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        try:
            c.execute(
                """
                SELECT rs.*, ce.start_time, ce.end_time, ce.name
                FROM reminder_settings rs
                JOIN ctf_events ce ON rs.event_id = ce.event_id AND rs.guild_id = ce.guild_id
                """
            )
            return c.fetchall()
        except Exception as e:
            print(f"Error getting all reminder settings: {e}")
            return []
        finally:
            conn.close()
