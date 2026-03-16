import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import datetime

load_dotenv()


bot = commands.Bot(
    intents=discord.Intents.all(),
    debug_guilds=[int(guild) for guild in os.getenv("GUILDS", "").split(",") if guild.strip()],
    sync_commands=True,
    owner_ids=[int(user) for user in os.getenv("OWNER", "").split(",") if user.strip()],
    command_prefix="!",
    help_command=None
)


@bot.event
async def on_ready():
    guilds = len(bot.guilds)
    users = sum(
        1 for g in bot.guilds
        for m in g.members
        if not m.bot
    )
    bots = sum(
        1 for g in bot.guilds
        for m in g.members
        if m.bot
    )
    ping = round(bot.latency * 1000)
    slash_commands = len(bot.application_commands)
    prefix_commands = len(bot.commands)

    infos = [
        f"Framework      : Pycord {discord.__version__}",
        f"Ping           : {ping} ms",
        f"Guilds         : {guilds}",
        f"Users          : {users:,}",
        f"Bots           : {bots:,}",
        f"Slash Commands : {slash_commands}",
        f"Prefix Commands: {prefix_commands}",
    ]

    width = max(len(i) for i in infos)
    print(f"╔{'═' * (width + 2)}╗")
    for line in infos:
        print(f"║ {line:<{width}} ║")

    print(f"╚{'═' * (width + 2)}╝\n")
    activity = discord.Game(name=f"{users:,} users")
    await bot.change_presence(
        status=discord.Status.online,
        activity=activity
    )
    print("\nBot successfully started\n")

# -------------------------------------------------

@bot.slash_command(description="Force to load or reload all Slash commands")
@commands.is_owner()
@commands.cooldown(1, 10, commands.BucketType.user)
async def sync(ctx):
    await bot.sync_commands(force=True)
    print(f"{datetime.datetime.now()}: Synced from {ctx.author} ({ctx.author.id})")
    await ctx.respond("Slash-Commands are now synced, wait for a couple seconds before trying again!", ephemeral=True)

# -------------------------------------------------


if __name__ == "__main__":
    for filename in os.listdir("cog"):
        if filename.endswith(".py"):
            cog = f"cog.{filename[:-3]}"
            try:
                bot.load_extension(cog)
                print(f"[+] Loaded: {cog}")
            except Exception as e:
                print(f"[!] Error {cog}: {e}")

    bot.run(os.getenv("TOKEN"))
