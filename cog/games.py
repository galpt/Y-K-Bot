import asyncio
import discord
from discord.ext import commands
import sqlite3
import random


DB_PATH = "Data/games.db"
CHOICES = ["Scissors", "Rock", "Paper"]
RANK_EMOJIS = ["🥇", "🥈", "🥉", "🎖️", "⭐"]



class GamesDatabase():
    def __init__(self, db_name: str = DB_PATH):
        self.conn = sqlite3.connect(db_name)
        self._init_db()

    def _init_db(self):
        conn = self.conn.cursor()
        conn.execute('''CREATE TABLE IF NOT EXISTS Rock_Paper_Scissors (
            user_id INTEGER PRIMARY KEY,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            draws INTEGER DEFAULT 0
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS TicTacToe (
            user_id INTEGER PRIMARY KEY,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            draws INTEGER DEFAULT 0
        )''')
        self.conn.commit()

def update_stats(user_id: int, result: str, game: str = "rps", bot_user_id: int = None):
    if user_id is None or user_id == bot_user_id:
        return
    table = "Rock_Paper_Scissors" if game.lower() == "rps" else "TicTacToe"
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(f"INSERT OR IGNORE INTO {table} (user_id) VALUES (?)", (user_id,))
        if result == "win":
            cur.execute(f"UPDATE {table} SET wins = wins + 1 WHERE user_id=?", (user_id,))
        elif result == "loss":
            cur.execute(f"UPDATE {table} SET losses = losses + 1 WHERE user_id=?", (user_id,))
        else:
            cur.execute(f"UPDATE {table} SET draws = draws + 1 WHERE user_id=?", (user_id,))
        conn.commit()

def determine_result(p1_choice: str, p2_choice: str) -> str:
    if p1_choice == p2_choice:
        return "draw"
    wins = {"Scissors": "Paper", "Rock": "Scissors", "Paper": "Rock"}
    return "win" if wins[p1_choice] == p2_choice else "loss"

class RPSPlayView(discord.ui.View):
    def __init__(self, p1: discord.User, p2: discord.User, bot_user: discord.User):
        super().__init__(timeout=120)
        self.p1 = p1
        self.p2 = p2
        self.bot_user = bot_user
        self.choices = {}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in [self.p1.id, self.p2.id]:
            await interaction.response.send_message("❌ This is not your game!", ephemeral=True)
            return False

        if self.is_finished():
            await interaction.response.send_message(
                "This game is already over.", ephemeral=True
            )
            return False

        return True

    @discord.ui.button(label="✂️  Scissors", style=discord.ButtonStyle.secondary)
    async def scissors_btn(self, button, interaction):
        await self.handle_choice(interaction, "Scissors")

    @discord.ui.button(label="🪨  Rock", style=discord.ButtonStyle.secondary)
    async def rock_btn(self, button, interaction):
        await self.handle_choice(interaction, "Rock")

    @discord.ui.button(label="📃  Paper", style=discord.ButtonStyle.secondary)
    async def paper_btn(self, button, interaction):
        await self.handle_choice(interaction, "Paper")

    async def handle_choice(self, interaction: discord.Interaction, choice: str):
        uid = interaction.user.id

        if uid in self.choices:
            await interaction.response.send_message("You have already chosen!", ephemeral=True)
            return

        self.choices[uid] = choice

        if self.p2 == self.bot_user or self.p1 == self.bot_user:
            human = self.p1 if self.p1 != self.bot_user else self.p2
            bot_choice = random.choice(CHOICES)
            result = determine_result(choice, bot_choice)
            winner_text = {
                "win": f"{human.mention} wins! 🎉",
                "loss": f"{self.bot_user.mention} wins! 🤖",
                "draw": "Draw! 😐"
            }[result]

            for child in self.children:
                child.disabled = True
            await interaction.response.defer()
            await interaction.edit_original_response(
                content=(f"**Result:** {winner_text}\n"
                         f"- {human.mention} chooses **{choice}**\n"
                         f"- Bot chooses **{bot_choice}**"),
                view=self
            )
            self.stop()
            return

        if len(self.choices) == 2:
            p1_choice = self.choices[self.p1.id]
            p2_choice = self.choices[self.p2.id]
            p1_result = determine_result(p1_choice, p2_choice)
            p2_result = "draw" if p1_result == "draw" else ("loss" if p1_result == "win" else "win")

            update_stats(self.p1.id, p1_result)
            update_stats(self.p2.id, p2_result)

            winner_text = {
                "win": f"{self.p1.mention} wins! 🎉",
                "loss": f"{self.p2.mention} wins! 🎉",
                "draw": "Draw! 😐"
            }[p1_result]

            for child in self.children:
                child.disabled = True
            await interaction.response.defer()
            await interaction.edit_original_response(
                content=(f"**{winner_text}**\n"
                         f"- {self.p1.mention} chooses **{p1_choice}**\n"
                         f"- {self.p2.mention} chooses **{p2_choice}**"),
                view=self
            )
            self.stop()
        else:
            await interaction.response.send_message("Choice saved, waiting for opponent...", ephemeral=True)

class TicTacToeView(discord.ui.View):
    def __init__(self, p1, p2, bot_user, size=3, win_length=3):
        super().__init__(timeout=120)
        self.p1 = p1
        self.p2 = p2
        self.bot_user = bot_user
        self.size = size
        self.win_length = win_length
        self.board = [" "] * (size * size)
        self.current = p1
        self.winner = None
        self.message = None
        self.is_bot_game = (p1 == bot_user or p2 == bot_user)

        for i in range(size * size):
            self.add_item(self.Cell(i, row=i // size))

    async def on_timeout(self):
        if self.message:
            for child in self.children:
                child.disabled = True
            embed = self.create_embed(
                title="⏰ Time ran out!",
                description=f"Last player to move: {self.current.mention}"
            )
            await self.message.edit(content=None, embed=embed, view=self)
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user not in [self.p1, self.p2]:
            await interaction.response.send_message(
                "❌ You are not part of this game!", ephemeral=True
            )
            return False
        return True

    class Cell(discord.ui.Button):
        def __init__(self, idx, row):
            super().__init__(label="\u200b", style=discord.ButtonStyle.secondary, row=row)
            self.idx = idx

        async def callback(self, interaction: discord.Interaction):
            view: TicTacToeView = self.view
            bot_user_id = view.bot_user.id
            if interaction.user != view.current:
                await interaction.response.send_message("⏳ Not your turn!", ephemeral=True)
                return
            if view.board[self.idx] != " ":
                await interaction.response.send_message("❌ Cell already taken!", ephemeral=True)
                return

            mark = "❌" if view.current == view.p1 else "◯️"
            view.board[self.idx] = mark
            self.label = mark
            self.style = discord.ButtonStyle.primary if mark == "❌" else discord.ButtonStyle.danger
            self.disabled = True

            if view.check_winner(mark):
                view.winner = view.current
                for child in view.children:
                    child.disabled = True

                embed = discord.Embed(
                    title="🎉 Game Over!",
                    description=f"{view.winner.mention} wins!",
                    color=discord.Color.green()
                )
                await interaction.response.edit_message(content=None, embed=embed, view=view)
                if view.p1 != view.bot_user and view.p2 != view.bot_user:
                    loser = view.p2 if view.winner == view.p1 else view.p1
                    update_stats(view.winner.id, "win", game="ttt", bot_user_id=view.bot_user.id)
                    update_stats(loser.id, "loss", game="ttt", bot_user_id=view.bot_user.id)

                view.stop()
                return

            if all(s != " " for s in view.board):
                for child in view.children:
                    child.disabled = True
                embed = discord.Embed(
                    title="😐 Draw!",
                    description="The board is full!",
                    color=discord.Color.gold()
                )
                await interaction.response.edit_message(content=None, embed=embed, view=view)
                if view.p1 != view.bot_user and view.p2 != view.bot_user:
                    update_stats(view.p1.id, "draw", game="ttt", bot_user_id=view.bot_user.id)
                    update_stats(view.p2.id, "draw", game="ttt", bot_user_id=view.bot_user.id)
                view.stop()
                return

            view.current = view.p2 if view.current == view.p1 else view.p1
            embed = discord.Embed(
                title=f"TicTacToe {view.size}x{view.size}",
                description=f"Your turn: {view.current.mention}",
                color=discord.Color.blurple()
            )
            embed.add_field(
                name="Players",
                value=f"❌ {view.p1.mention}\n◯️ {view.p2.mention}",
                inline=False
            )
            await interaction.response.edit_message(content=None, embed=embed, view=view)

            if view.current == view.bot_user:
                await view.bot_move()

    async def bot_move(self):
        await asyncio.sleep(1)
        empty = [i for i, v in enumerate(self.board) if v == " "]
        if not empty:
            return

        bot_mark = "❌" if self.current == self.p1 else "◯️"
        player_mark = "◯️" if bot_mark == "❌" else "❌"

        def check_immediate_win():
            for idx in empty:
                self.board[idx] = bot_mark
                if self.check_winner(bot_mark):
                    self.board[idx] = " "
                    return idx
                self.board[idx] = " "
            return None

        def check_block_player():
            for idx in empty:
                self.board[idx] = player_mark
                if self.check_winner(player_mark):
                    self.board[idx] = " "
                    return idx
                self.board[idx] = " "
            return None

        def check_fork_opportunities():
            fork_candidates = []
            for idx in empty:
                self.board[idx] = bot_mark
                threats = 0
                for test_idx in empty:
                    if test_idx == idx:
                        continue
                    self.board[test_idx] = bot_mark
                    if self.check_winner(bot_mark):
                        threats += 1
                    self.board[test_idx] = " "
                if threats >= 1:
                    fork_candidates.append((threats, idx))
                self.board[idx] = " "
            return max(fork_candidates)[1] if fork_candidates else None

        def check_middle_zone_threats():
            if self.size != 5:
                return None

            middle_zone = [6, 7, 8, 11, 12, 13, 16, 17, 18]
            danger_spots = []
            for idx in [i for i in empty if i in middle_zone]:
                self.board[idx] = player_mark
                for dx, dy in [(0, 1), (1, 0), (1, 1), (1, -1)]:
                    x, y = idx // 5, idx % 5
                    line = []
                    for step in range(-2, 3):
                        nx, ny = x + dx * step, y + dy * step
                        if 0 <= nx < 5 and 0 <= ny < 5:
                            line.append(self.board[nx * 5 + ny])
                    if line.count(player_mark) >= 2 and " " in line:
                        danger_spots.append(idx)
                        break
                self.board[idx] = " "
            return random.choice(danger_spots) if danger_spots else None

        def check_corner_strategy():
            corners = [0, 4, 20, 24] if self.size == 5 else [0, 2, 6, 8]
            available = [c for c in corners if c in empty]
            return random.choice(available) if available else None

        def check_edge_strategy():
            if self.size == 5:
                edges = [1, 2, 3, 5, 9, 10, 14, 15, 19, 21, 22, 23]
            else:
                edges = [1, 3, 5, 7]
            available = [e for e in edges if e in empty]
            return random.choice(available) if available else None

        def random_move():
            return random.choice(empty)

        strategies = [
            check_immediate_win,
            check_block_player,
            check_fork_opportunities,
            check_middle_zone_threats,
            check_corner_strategy,
            check_edge_strategy,
            random_move
        ]

        move = None
        for strategy in strategies:
            move = strategy()
            if move is not None:
                break

        btn = self.children[move]
        btn.label = bot_mark
        btn.style = discord.ButtonStyle.primary if bot_mark == "❌" else discord.ButtonStyle.danger
        btn.disabled = True
        self.board[move] = bot_mark

        if self.check_winner(bot_mark):
            self.winner = self.current
            for child in self.children:
                child.disabled = True

            embed = discord.Embed(
                title="🎉 Game Over!",
                description=f"{self.winner.mention} wins!",
                color=discord.Color.green()
            )
            await self.message.edit(embed=embed, view=self)

            if self.p1 != self.bot_user and self.p2 != self.bot_user:
                loser = self.p2 if self.winner == self.p1 else self.p1
                update_stats(self.winner.id, "win", "ttt", self.bot_user.id)
                update_stats(loser.id, "loss", "ttt", self.bot_user.id)

            self.stop()

        elif all(cell != " " for cell in self.board):
            for child in self.children:
                child.disabled = True

            embed = discord.Embed(
                title="😐 Draw!",
                description="The board is full!",
                color=discord.Color.gold()
            )
            await self.message.edit(embed=embed, view=self)

            if self.p1 != self.bot_user and self.p2 != self.bot_user:
                update_stats(self.p1.id, "draw", "ttt", self.bot_user.id)
                update_stats(self.p2.id, "draw", "ttt", self.bot_user.id)

            self.stop()

        else:
            self.current = self.p2 if self.current == self.p1 else self.p1
            embed = discord.Embed(
                title=f"TicTacToe {self.size}x{self.size}",
                description=f"Your turn: {self.current.mention}",
                color=discord.Color.blurple()
            )
            embed.add_field(
                name="Players",
                value=f"❌ {self.p1.mention}\n◯️ {self.p2.mention}",
                inline=False
            )

            await self.message.edit(embed=embed, view=self)

    def check_winner(self, mark):
        n = self.size
        k = self.win_length
        board = self.board

        for i in range(n * n):
            if board[i] != mark:
                continue

            x, y = i // n, i % n

            for dx, dy in [(0, 1), (1, 0), (1, 1), (1, -1)]:
                count = 1
                for step in range(1, k):
                    nx, ny = x + dx * step, y + dy * step
                    ni = nx * n + ny

                    if 0 <= nx < n and 0 <= ny < n and board[ni] == mark:
                        count += 1
                    else:
                        break

                if count == k:
                    return True
        return False

    def create_embed(self, title: str, description: str) -> discord.Embed:
        color = discord.Color.blurple()
        if "win" in title.lower():
            color = discord.Color.green()
        elif "draw" in title.lower():
            color = discord.Color.gold()
        elif "time" in title.lower():
            color = discord.Color.red()

        embed = discord.Embed(
            title=title,
            description=f"{description}\n\n",
            color=color
        )
        return embed

class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot_user = bot.user
        self.db = GamesDatabase()

    games = discord.SlashCommandGroup("games", "Games and minigames")

    @games.command(name="rps", description="Play Rock-Paper-Scissors against bot or player")
    async def rps(self, ctx: discord.ApplicationContext, opponent: discord.User = None):
        opponent = opponent or self.bot.user

        if opponent == ctx.author:
            await ctx.respond("You cannot play against yourself.", ephemeral=True)
            return

        if opponent == self.bot.user:
            view = RPSPlayView(ctx.author, self.bot.user, self.bot.user)
            await ctx.respond(">>> Choose your option against the bot:", view=view)
            return

        invite_view = RPSInviteView(ctx.author, opponent)
        msg = await ctx.respond(
            f"{ctx.author.mention} challenges {opponent.mention} to **Rock-Paper-Scissors**!",
            view=invite_view
        )
        invite_view.message = await msg.original_response()

        await invite_view.wait()

        if invite_view.accepted is not True:
            if invite_view.accepted is False:
                await invite_view.message.edit(content=f"❌ {opponent.mention} declined.", view=None)
            return

        play_view = RPSPlayView(ctx.author, opponent, self.bot.user)

        await msg.edit(content=f"{opponent.mention} accepted!\n>>> {ctx.author.mention} starts, choose your option:", view=play_view)

    @games.command(name="tictactoe", description="Play TicTacToe in 3x3 or 5x5")
    async def tictactoe(
            self,
            ctx: discord.ApplicationContext,
            opponent: discord.User = None,
            mode: discord.Option(str, "Game mode", choices=["3x3", "5x5"]) = "3x3"
    ):
        opponent = opponent or self.bot.user
        size = 3 if mode == "3x3" else 5
        win_length = 3 if mode == "3x3" else 4

        if opponent == ctx.author:
            await ctx.respond("❌ You cannot play against yourself.", ephemeral=True)
            return

        if opponent.bot and opponent != self.bot.user:
            await ctx.respond("❌ You can only play against real players or your own bot.", ephemeral=True)
            return

        if opponent == self.bot.user:
            start_embed = discord.Embed(
                title=f"TicTacToe {size}x{size}",
                description=f"Your turn: {ctx.author.mention}",
                color=discord.Color.blurple()
            )
            start_embed.add_field(
                name="Players",
                value=f"❌ {ctx.author.mention}\n◯️ {opponent.mention}",
                inline=False
            )

            game_view = TicTacToeView(ctx.author, opponent, bot_user=self.bot.user, size=size, win_length=win_length)
            await ctx.respond(embed=start_embed, view=game_view)
            game_view.message = await ctx.interaction.original_response()
            return

        confirm_view = TTTMatchView(ctx.author, opponent)
        embed = discord.Embed(
            title="TicTacToe",
            description=f"{opponent.mention}, {ctx.author.mention} challenges you! Do you accept?",
            color=discord.Color.blurple()
        )
        await ctx.respond(content=f"{opponent.mention}", embed=embed, view=confirm_view)
        await confirm_view.wait()

        if confirm_view.value is None or confirm_view.value is False:
            return

        start_embed = discord.Embed(
            title="TicTacToe {size}x{size}",
            description=f"Your turn: {ctx.author.mention}",
            color=discord.Color.blurple()
        )
        start_embed.add_field(name="Players:", value=f"❌ {ctx.author.mention}\n◯️ {opponent.mention}", inline=False)

        game_message = await ctx.interaction.original_response()
        game_view = TicTacToeView(ctx.author, opponent, self.bot.user, size=size, win_length=win_length)
        game_view.message = game_message

        await game_message.edit(content=None, embed=start_embed, view=game_view)

    @games.command(name="stats", description="Show your RPS or TTT statistics")
    @discord.option("game", choices=["Rock-Paper-Scissors", "TicTacToe"], description="Choose the game", required=True)
    @discord.option("user", description="User whose stats are displayed", required=False)
    async def stats(self, ctx: discord.ApplicationContext, game: str, user: discord.User = None):
        target = user or ctx.author

        game_mapping = {
            "Rock-Paper-Scissors": "Rock_Paper_Scissors",
            "TicTacToe": "TicTacToe"
        }
        table = game_mapping.get(game)
        if not table:
            return await ctx.respond(f"Unknown game: {game}", ephemeral=True)

        try:
            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.cursor()
                cur.execute(f"SELECT wins, losses, draws FROM {table} WHERE user_id=?", (target.id,))
                row = cur.fetchone()
        except sqlite3.Error as e:
            await ctx.respond(f"DB error: {e}", ephemeral=True)

        if not row:
            return await ctx.respond(
                f"No {game} stats found for {target.mention} | {target.display_name} ({target.id}).",
                ephemeral=True)

        wins, losses, draws = row
        total = wins + losses + draws
        winrate = (wins / total * 100) if total else 0
        lossrate = (losses / total * 100) if total else 0
        drawrate = (draws / total * 100) if total else 0

        def make_bar(rate):
            filled = int(rate // 10)
            return "█" * filled + "░" * (10 - filled)

        if game == "Rock-Paper-Scissors":
            if winrate >= 70:
                rank_label = "🏆 Pro"
            elif winrate >= 50:
                rank_label = "⭐ Advanced"
            elif winrate >= 30:
                rank_label = "📈 Learning"
            else:
                rank_label = "🥱 Beginner"
        else:
            rank_label = "TicTacToe Player"

        embed = discord.Embed(
            title=f"📊 {game} - Statistics – {target.display_name}",
            description=f"Rank: **{rank_label}**",
            color=discord.Color.blurple()
        )

        embed.add_field(name="🏆 Wins", value=f"{wins}", inline=True)
        embed.add_field(name="💀 Losses", value=f"{losses}", inline=True)
        embed.add_field(name="🤝 Draws", value=f"{draws}", inline=True)
        embed.add_field(name="🎮 Total games", value=f"{total}", inline=False)
        embed.add_field(name="Winrate", value=f"{winrate:.1f}%\n{make_bar(winrate)}", inline=False)
        embed.add_field(name="Lossrate", value=f"{lossrate:.1f}%\n{make_bar(lossrate)}", inline=False)
        embed.add_field(name="Drawrate", value=f"{drawrate:.1f}%\n{make_bar(drawrate)}", inline=False)
        embed.set_footer(text=f"{game} • Statistics")

        return await ctx.respond(embed=embed)

def setup(bot):
    bot.add_cog(Games(bot))

class RPSInviteView(discord.ui.View):
    def __init__(self, challenger: discord.User, opponent: discord.User):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.accepted = None

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.green)
    async def accept(self, button, interaction: discord.Interaction):
        if interaction.user != self.opponent:
            await interaction.response.send_message("❌ Only the challenged person can accept!", ephemeral=True)
            return
        self.accepted = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.red)
    async def decline(self, button, interaction: discord.Interaction):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("❌ Only the challenged person can decline!", ephemeral=True)
            return
        self.accepted = False
        self.stop()
        await interaction.response.defer()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        embed = discord.Embed(
            title="⏰ Challenge expired!",
            description=f"{self.opponent.mention} did not respond.",
            color=discord.Color.red()
        )
        if self.message:
            await self.message.edit(content=None, embed=embed, view=self)
        self.stop()

class TTTMatchView(discord.ui.View):
    def __init__(self, author: discord.User, opponent: discord.User):
        super().__init__(timeout=60)
        self.value = None
        self.author = author
        self.opponent = opponent

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def confirm(self, button, interaction: discord.Interaction):
        if interaction.user != self.opponent:
            await interaction.response.send_message("❌ Only the challenged person can accept!", ephemeral=True)
            return
        self.value = True
        await interaction.response.send_message("✅ You have accepted the challenge!", ephemeral=True)
        self.stop()

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def deny(self, button, interaction: discord.Interaction):
        if interaction.user != self.opponent:
            await interaction.response.send_message("❌ Only the challenged person can decline!", ephemeral=True)
            return
        self.value = False
        for child in self.children:
            child.disabled = True

        embed = discord.Embed(
            color=discord.Color.blurple(),
            title=f"{interaction.user.display_name} declined"
        )

        await interaction.response.edit_message(content=None, embed=embed, view=self)
        self.stop()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        embed = discord.Embed(
            title="⏰ Challenge expired!",
            description=f"{self.opponent.mention} did not respond.",
            color=discord.Color.red()
        )
        if hasattr(self, 'message') and self.message:
            await self.message.edit(content=None, embed=embed, view=self)
        self.stop()
