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
                FOREIGN KEY (event_id, guild_id) REFERENCES ctf_events(event_id, guild_id)
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
            # 检查比赛是否存在
            c.execute(
                "SELECT 1 FROM ctf_events WHERE event_id = ? AND guild_id = ?",
                (event_id, guild_id),
            )
            if not c.fetchone():
                return False

            # 添加用户参与记录
            c.execute(
                """
                INSERT OR REPLACE INTO event_participants 
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
        """获取比赛的所有参与者"""
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

    def get_user_events(self, user_id: str, guild_id: str) -> list:
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
                # 检查返回的字段数量
                if len(event) >= 12:  # 包含 invite_link 的新格式
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
                        "invite_link": event[10]
                        if event[10] and len(event[10]) <= 50
                        else "",
                        "added_time": event[11],
                    }
                else:  # 旧格式，没有 invite_link
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
                        "invite_link": "",  # 添加空的邀请链接
                        "added_time": event[10],
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
                    "invite_link": event[10]
                    if len(event) >= 12 and event[10] and len(event[10]) <= 50
                    else "",
                    "added_time": event[11] if len(event) >= 12 else event[10],
                }
                for event in events
            ]
        except Exception as e:
            print(f"Error getting all events: {e}")
            return []
        finally:
            conn.close()

    def delete_event(self, event_id: str, guild_id: str):
        """删除指定 ID 的比赛"""
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
            print(f"删除比赛时出错: {e}")
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
            # 确保 invite_link 不为 None
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
