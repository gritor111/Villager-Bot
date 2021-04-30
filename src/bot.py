from concurrent.futures import ThreadPoolExecutor
from discord.ext import commands
import asyncio
import aiohttp
import discord
import random
# import uvloop
import arrow
import json
import sys
import os

# ensure villager bot modules are accessible
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# ensure the current working directory is correct
os.chdir(os.path.dirname(__file__))

import speedups

speedups.install()

from util.setup import villager_bot_intents, setup_logging, setup_database, load_text
from util.misc import get_lang, get_prefix, check_global
from util.statcord import ShitCordClient
from util.cj import ClassyDict

# send function/method for easy sending of embed messages with small amounts of text
async def send(_bot, location, message, respond=False, ping=False):
    embed = discord.Embed(color=_bot.d.cc, description=message)

    try:
        if respond and hasattr(location, "reply"):
            try:
                await location.reply(embed=embed, mention_author=ping)
                return True
            except discord.errors.HTTPException:
                pass

        await location.send(embed=embed)

        return True
    except discord.Forbidden:
        return False


# update the role of a member in the support server
async def update_support_member_role(_bot, member):
    support_guild = _bot.get_guild(_bot.d.support_server_id)
    role_map_values = list(_bot.d.role_mappings.values())
    db = _bot.get_cog("Database")
    roles = []

    for role in member.roles:
        if role.id not in role_map_values and role.id != _bot.d.support_server_id:
            roles.append(role)

        await asyncio.sleep(0)

    pickaxe_role = _bot.d.role_mappings.get(await db.fetch_pickaxe(member.id))
    if pickaxe_role is not None:
        roles.append(support_guild.get_role(pickaxe_role))

    if await db.fetch_item(member.id, "Bane Of Pillagers Amulet") is not None:
        roles.append(support_guild.get_role(_bot.d.role_mappings.get("BOP")))

    if roles != member.roles:
        try:
            await member.edit(roles=roles)
        except Exception:
            pass


def update_fishing_prices(_bot):
    for fish in _bot.d.fishing.fish.values():
        fish.current = random.randint(*fish.value)


def mutate_botd(_bot):
    d = _bot.d

    d.cc = discord.Color.green()  # embed color

    # update fishing data
    _bot.update_fishing_prices()
    fishes = d.fishing.fish_ids = list(d.fishing.fish.keys())
    d.fishing.fish_weights = [(len(fishes) - fish_data.rarity) ** d.fishing.exponent for fish_data in d.fishing.fish.values()]

    d.mining.pickaxes = list(d.mining.yields_pickaxes)[::-1]  # get list of pickaxe types from best to worst

    d.fun_langs.unenchant = {v: k for k, v in d.fun_langs.enchant.items()}  # reverse dict to create unenchantment lang


def run(shard_id: int, shard_count: int):
    # setup uvloop
    # uvloop.install()

    # set up basic logging
    logger = setup_logging(shard_id)

    logger.info("loading private keys...")
    with open("data/keys.json", "r") as k:  # load bot keys
        keys = ClassyDict(json.load(k))

    bot = commands.Bot(  # setup bot
        command_prefix=get_prefix,
        case_insensitive=True,
        intents=villager_bot_intents(),
        help_command=None,
        shard_id=shard_id,
        shard_count=shard_count,
    )

    bot.logger = logger
    bot.aiohttp = aiohttp.ClientSession(loop=bot.loop)

    bot.send = send.__get__(bot)
    bot.get_lang = lambda ctx: get_lang(bot, ctx)
    bot.update_support_member_role = update_support_member_role.__get__(bot)
    bot.update_fishing_prices = update_fishing_prices.__get__(bot)
    bot.mutate_botd = mutate_botd.__get__(bot)

    logger.info("setting up connection to database and db pool...")
    asyncio.get_event_loop().run_until_complete(setup_database(bot, keys))

    logger.info("loading villager bot text...")
    bot.langs = load_text()

    logger.info("loading villager bot constant data...")
    with open("data/data.json", "r", encoding="utf8") as d:
        bot.d = ClassyDict(
            json.load(d)
        )  # cj automatically turns json into sets of nested classes and attributes for easy access

    bot.k = keys
    bot.k.fernet = bot.k.fernet.encode("utf-8")

    bot.v = ClassyDict()

    bot.v.start_time = arrow.utcnow()

    bot.v.votes_topgg = 0
    bot.v.cmd_count = 0
    bot.v.msg_count = 0

    bot.v.miners = {}  # {user_id: commands}
    bot.v.honey_buckets = None  # list of cooldowns for honey command (econ cog)
    bot.v.pillagers = {}  # {user_id: pillages}
    bot.v.pillages = {}  # {user_id: times_pillaged}
    bot.v.chuggers = {}  # {user_id: [potion, potion]}
    bot.v.cmd_lb = {}  # {user_id: command_count}

    bot.v.pause_econ = {}  # {uid: starttime}
    bot.v.spawn_queue = {}  # {ctx: starttime}

    bot.v.rcon_cache = {}  # {uid: rcon_client}

    bot.v.disabled_cmds = {}  # {gid: [disabled cmds]}

    bot.v.ban_cache = set()  # {uid, uid,..}
    bot.v.prefix_cache = {}  # {gid: 'prefix'}
    bot.v.lang_cache = {}  # {gid: 'lang'}

    bot.v.additional_mcservers = []
    bot.v.mcserver_list = []

    bot.owner_locked = False

    bot.statcord = ShitCordClient(bot, keys.statcord)

    bot.cog_list = [  # list of cogs which are to be loaded in the bot
        "cogs.core.database",
        "cogs.core.events",
        "cogs.core.loops",
        "cogs.cmds.useful",
        "cogs.cmds.owner",
        "cogs.cmds.mc",
        "cogs.cmds.mod",
        "cogs.cmds.fun",
        "cogs.cmds.econ",
        "cogs.cmds.config",
        "cogs.other.mobs",
        "cogs.other.webhooks",
    ]

    for cog in bot.cog_list:  # load every cog in bot.cog_list
        logger.info(f"loading extension: {cog}")
        bot.load_extension(cog)

    bot.mutate_botd()

    @bot.check  # everythingggg goes through here
    def global_check(ctx):
        ctx.l = bot.get_lang(ctx)
        return check_global(bot, ctx)

    with ThreadPoolExecutor() as bot.tpool:
        bot.run(keys.discord)  # run the bot, this is a blocking call

    asyncio.run(bot.aiohttp.close())
