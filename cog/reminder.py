import uuid

from utils.imports import *

DB_PATH = "Data/reminders.db"
MAX_RETRIES = 5


def parse_time(s: str):
    try:
        unit = s[-1]
        value = int(s[:-1])
        if unit == "s": return timedelta(seconds=value)
        if unit == "m": return timedelta(minutes=value)
        if unit == "h": return timedelta(hours=value)
        if unit == "d": return timedelta(days=value)
    except:
        return None


class ReminderSelect(discord.ui.Select):
    def __init__(self, cog, user_id, reminders):
        self.cog = cog
        self.user_id = user_id
        self.reminder_map = {display_num: (db_id, msg) for display_num, db_id, msg, run_at in reminders}

        options = [
            discord.SelectOption(
                label=f"#{display_num}",
                description=(msg[:80] if msg else ""),
                value=str(display_num)
            )
            for display_num, db_id, msg, run_at in reminders[:25]
        ]

        super().__init__(placeholder="Select reminder", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not your reminders!", ephemeral=True)

        display_num = int(self.values[0])
        db_id, msg = self.reminder_map[display_num]

        view = ConfirmView(self.cog, self.user_id, db_id, display_num)
        await interaction.response.send_message(
            f"Cancel reminder `#{display_num}`?",
            view=view,
            ephemeral=True
        )


class ConfirmView(discord.ui.View):
    def __init__(self, cog, user_id, db_id, display_num):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
        self.db_id = db_id
        self.display_num = display_num

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok = self.cog.cancel_reminder(self.user_id, self.db_id)
        if ok:
            await interaction.response.edit_message(content=f"✅ Reminder #{self.display_num} cancelled", view=None)
        else:
            await interaction.response.edit_message(content="❌ Failed", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Cancelled", view=None)


class Reminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.worker_task = None
        self._init_db()
        self.bot.loop.create_task(self._auto_start_worker())

    async def _auto_start_worker(self):
        await self.bot.wait_until_ready()
        if not self.worker_task or self.worker_task.done():
            self.worker_task = asyncio.create_task(self.worker_loop())
            print("Worker loop started automatically")

    async def cog_load(self):
        if not self.worker_task or self.worker_task.done():
            self.worker_task = asyncio.create_task(self.worker_loop())
            print("Worker loop started via cog_load")

    def cog_unload(self):
        if self.worker_task:
            self.worker_task.cancel()
            print("Worker loop stopped")

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                channel_id INTEGER,
                message TEXT,
                run_at INTEGER,
                created_at INTEGER,
                status TEXT DEFAULT 'pending',
                retries INTEGER DEFAULT 0,
                lock_token TEXT,
                last_error TEXT
            )
            """)
            conn.commit()

    reminder = discord.SlashCommandGroup("reminder", "Remind system")

    @reminder.command(name="create", description="Create a reminder")
    async def create(
            self,
            ctx: discord.ApplicationContext,
            duration: discord.Option(str, description="Time until reminder (e.g., 10s, 5m, 2h, 1d)"),
            message: discord.Option(str, description="The reminder message")
    ):
        delta = parse_time(duration)
        if not delta:
            return await ctx.respond("Use 10s / 5m / 2h / 1d format.", ephemeral=True)

        if delta.total_seconds() < 5:
            return await ctx.respond("Min. 5s.", ephemeral=True)

        now = int(time.time())
        run_at = now + int(delta.total_seconds())

        with sqlite3.connect(DB_PATH) as conn:
            count = conn.execute("""
                SELECT COUNT(*) FROM reminders 
                WHERE user_id=? AND status='pending'
            """, (ctx.author.id,)).fetchone()[0]

            display_number = count + 1

            conn.execute("""
                INSERT INTO reminders
                (user_id, channel_id, message, run_at, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (ctx.author.id, ctx.channel.id, message, run_at, now))

            conn.commit()

        await ctx.respond(f"✅ Reminder `#{display_number}` → <t:{run_at}:f>")


    @reminder.command(name="list")
    async def list(self, ctx: discord.ApplicationContext):
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("""
                SELECT id, message, run_at
                FROM reminders
                WHERE user_id=? AND status='pending'
                ORDER BY run_at
            """, (ctx.author.id,)).fetchall()

        if not rows:
            return await ctx.respond("No reminders", ephemeral=True)

        reminders_with_numbers = []
        for i, (db_id, msg, run_at) in enumerate(rows[:25], 1):
            reminders_with_numbers.append((i, db_id, msg, run_at))

        text = "\n".join([
            f"`#{display_num}` → <t:{run_at}:f> (<t:{run_at}:R>) | {msg}"
            for display_num, db_id, msg, run_at in reminders_with_numbers
        ])

        view = discord.ui.View()
        view.add_item(ReminderSelect(self, ctx.author.id, reminders_with_numbers))

        await ctx.respond(text, view=view, ephemeral=True)


    def cancel_reminder(self, user_id, rid):
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute("""
                DELETE FROM reminders
                WHERE id=? AND user_id=? AND status='pending'
            """, (rid, user_id))
            conn.commit()
            return cur.rowcount > 0

    async def worker_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            try:
                now = int(time.time())

                with sqlite3.connect(DB_PATH) as conn:
                    pending_count = conn.execute("""
                        SELECT COUNT(*) FROM reminders 
                        WHERE status='pending' AND run_at <= ?
                    """, (now,)).fetchone()[0]

                    if pending_count > 0:
                        print(f"Found: {pending_count} pending reminders at {now}")

                        sample = conn.execute("""
                            SELECT id, run_at, message 
                            FROM reminders 
                            WHERE status='pending' AND run_at <= ?
                            LIMIT 5
                        """, (now,)).fetchall()
                        for r in sample:
                            print(f"   - Reminder #{r[0]}: due at {r[1]} (now: {now}, diff: {now - r[1]}s)")

                rows = conn.execute("""
                    SELECT id, user_id, channel_id, message, retries
                    FROM reminders
                    WHERE status='pending' AND run_at <= ?
                    LIMIT 50
                """, (now,)).fetchall()

                if rows:
                    print(f"⏳ ・ Processing {len(rows)} reminders...")

                for rid, uid, cid, msg, retries in rows:
                    print(f"⏰ ・ Attempting to send reminder #{rid}...")
                    lock_token = str(uuid.uuid4())

                    with sqlite3.connect(DB_PATH) as conn:
                        cur = conn.execute("""
                            UPDATE reminders
                            SET status='processing', lock_token=?
                            WHERE id=? AND status='pending'
                        """, (lock_token, rid))
                        conn.commit()

                        if cur.rowcount == 0:
                            print(f"🚀 ・ Reminder #{rid} was already processed by another worker")
                            continue

                    try:
                        channel = self.bot.get_channel(cid)
                        if not channel:
                            try:
                                channel = await self.bot.fetch_channel(cid)
                                print(f"✅ ・ Fetched channel {channel.name}")
                            except discord.NotFound:
                                raise Exception(f"🚨 ・ Channel {cid} not found")
                            except discord.Forbidden:
                                raise Exception(f"🚨 ・ No permission for channel {cid}")

                        try:
                            user = await self.bot.fetch_user(uid)
                            print(f"✅ ・ Found user {user.name}")
                        except discord.NotFound:
                            raise Exception(f"🚨 ・ User {uid} not found")

                        try:
                            await channel.send(f"⏰ ・ {user.mention} Reminder: `{msg}`")
                            print(f"✅ ・ Successfully sent reminder #{rid} to {channel.name}")
                        except discord.Forbidden:
                            raise Exception(f"🚨 ・ No send permission in channel {channel.name}")

                        with sqlite3.connect(DB_PATH) as conn:
                            conn.execute("""
                                DELETE FROM reminders
                                WHERE id=? AND lock_token=?
                            """, (rid, lock_token))
                            conn.commit()
                        print(f"🎯 ・ Reminder #{rid} was deleted (successfully sent)")

                    except Exception as e:
                        retries += 1
                        print(f"Error with reminder #{rid}: {e}")

                        if retries >= MAX_RETRIES:
                            with sqlite3.connect(DB_PATH) as conn:
                                conn.execute("""
                                    DELETE FROM reminders
                                    WHERE id=? AND lock_token=?
                                """, (rid, lock_token))
                                conn.commit()
                            print(f"🚨 ・ Reminder #{rid} deleted after {MAX_RETRIES} attempts")
                        else:
                            delay = min(60 * (2 ** retries), 3600)
                            new_run = int(time.time()) + delay

                            with sqlite3.connect(DB_PATH) as conn:
                                conn.execute("""
                                    UPDATE reminders
                                    SET status='pending',
                                        retries=?,
                                        run_at=?,
                                        last_error=?
                                    WHERE id=? AND lock_token=?
                                """, (retries, new_run, str(e), rid, lock_token))
                                conn.commit()
                            print(f"🚨 ・ Reminder #{rid} will be retried in {delay}s (attempt {retries}/{MAX_RETRIES})")

                await asyncio.sleep(5)

            except Exception as e:
                print(f"Worker loop error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(30)


def setup(bot):
    bot.add_cog(Reminder(bot))
