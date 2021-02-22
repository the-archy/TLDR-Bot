import discord
import re
import asyncio
import config
import time

from bot import TLDR
from bson import ObjectId
from typing import Optional
from modules import embed_maker, database
from discord.ext import commands

db = database.Connection()


class Command(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str = ''):
        return ctx.bot.get_command(argument, ctx.author)


class Role(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str = ''):
        if not ctx.guild:
            return argument

        # check if role is in a leveling route before fetching discord role
        branch, role = get_branch_role(ctx.guild.id, argument)
        if not branch or not role:
            return argument

        # make sure the role actually exists on the guild
        await get_leveling_role(ctx.guild, argument)

        return role


class Branch(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str = ''):
        branch_switch = {'p': 'parliamentary', 'h': 'honours'}
        return branch_switch.get(argument[0], 'parliamentary')


class ParseArgs(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str = ''):
        regex = r' ?-(\w+) ' if not ctx.command.parse_args else rf' ?-({"|".join(ctx.command.parse_args)})'
        filtered_args = list(filter(lambda a: bool(a), re.split(regex, argument)))
        results = {}

        if ctx.command.parse_args and filtered_args[0] not in ctx.command.parse_args:
            results['pre'] = filtered_args.pop(0)

        for arg, data in zip(filtered_args[::2], filtered_args[1::2]):
            if arg not in results:
                results[arg] = [data.strip()]
            else:
                results[arg].append(data.strip())

        return results


def id_match(identifier, extra):
    id_regex = re.compile(r'([0-9]{15,21})$')
    additional_regex = re.compile(extra)

    # check if role_identifier is id
    return id_regex.match(identifier) or additional_regex.match(identifier)


def get_custom_emote(ctx, emote):
    match = id_match(emote, r'<a?:[a-zA-Z0-9\_]+:([0-9]+)>$')
    result = None

    if match is None:
        # Try to get the emoji by name. Try local guild first.
        if ctx.guild:
            result = discord.utils.get(ctx.guild.emojis, name=emote)

        if result is None:
            result = discord.utils.get(ctx.bot.emojis, name=emote)
    else:
        emoji_id = int(match.group(1))

        # Try to look up emoji by id.
        if ctx.guild:
            result = discord.utils.get(ctx.guild.emojis, id=emoji_id)

        if result is None:
            result = discord.utils.get(ctx.bot.emojis, id=emoji_id)

    return result


def get_user_boost_multiplier(member):
    multiplier = 0

    leveling_user = db.get_leveling_user(member.guild.id, member.id)
    if 'boosts' not in leveling_user:
        return multiplier

    user_boosts = leveling_user['boosts']
    for boost_type, boost_data in user_boosts.items():
        expires = boost_data['expires']
        if round(time.time()) > expires:
            db.leveling_users.update_one(
                {'guild_id': member.guild.id, 'user_id': member.id},
                {'$unset': {f'boosts.{boost_type}': 1}}
            )
            continue

        multiplier += boost_data['multiplier']

    return multiplier


async def get_guild_role(guild: discord.Guild, role_identifier: str):
    match = id_match(role_identifier, r'<@&([0-9]+)>$')
    if match:
        role = guild.get_role(int(match.group(1)))
    else:
        role = discord.utils.find(lambda rl: rl.name == role_identifier, guild.roles)

    return role


async def get_leveling_role(guild: discord.Guild, role_identifier: str, member: discord.Member = None) -> discord.Role:
    # check if role_identifier is id
    role = await get_guild_role(guild, role_identifier)
    if role is None:
        role = await guild.create_role(name=role_identifier)

    if member and role not in member.roles:
        await member.add_roles(role)

    return role


def get_branch_role(guild_id: int, role_name: str) -> tuple:
    leveling_data = db.get_leveling_data(guild_id, {'leveling_routes': 1})
    leveling_routes = leveling_data['leveling_routes']

    all_roles = leveling_routes['parliamentary'] + leveling_routes['honours']

    role = next((role for role in all_roles if role['name'].lower() == role_name.lower()), None)

    if role in leveling_routes['parliamentary']:
        branch = 'parliamentary'
    else:
        branch = 'honours'

    return branch, role


def get_user_clearance(member: discord.Member) -> list:
    permissions = member.guild_permissions
    clearance = ['User']

    if permissions.manage_messages:
        clearance.append('Mod')

    if permissions.administrator:
        clearance.append('Admin')

    if member.id in config.DEV_IDS:
        clearance.append('Dev')

    return clearance


async def get_member(ctx: commands.Context, source) -> Optional[discord.Member]:
    # just in case source is empty
    if not source:
        return await embed_maker.error(ctx, 'Input is empty')

    if type(source) == int:
        source = str(source)

    # check if source is member mention
    if ctx.message.mentions:
        return ctx.message.mentions[0]

    # Check if source is member id
    if source.isdigit() and len(source) > 9:
        member = ctx.guild.get_member(int(source))

        # if member isn't found by get, maybe they aren't in the cache, fetch them by making an api call
        if not member:
            try:
                member = await ctx.guild.fetch_member(int(source))
                if member is None:
                    return await embed_maker.error(ctx, f'Member not found by id: `{source}`')
            except discord.Forbidden:
                return await embed_maker.error(ctx, 'Bot does not have access to the guild')
            except discord.HTTPException:
                return await embed_maker.error(ctx, f'Member not found by id: `{source}`')

        if member:
            return member

    # Check if source is member's name
    if len(source) < 3:
        return await embed_maker.error(ctx, 'User name input needs to be at least 3 characters long')

    # checks first for a direct name match
    members = list(
        filter(
            lambda m: m.name.lower() == source.lower() or m.display_name.lower() == source.lower(),
            ctx.guild.members
        )
    )

    # if can't find direct name match, check for a match with regex
    if not members:
        regex = re.compile(fr'({source.lower()})')
        # checks for regex match
        members = list(
            filter(
                lambda m: re.findall(regex, str(m).lower()) or re.findall(regex, m.display_name.lower()),
                ctx.guild.members
            )
        )

        if not members:
            return await embed_maker.error(ctx, f'No members found by the name `{source}`')

    # too many matches
    if len(members) > 10:
        return await embed_maker.error(ctx, 'Too many username matches')

    # only one match, return member
    if len(members) == 1:
        return members[0]

    # send embed containing member matches and let member choose which one they meant
    description = 'Found multiple users, which one did you mean? `type number of member`\n\n'
    for i, member in enumerate(members):
        description += f'`#{i + 1}` | {member.display_name}#{member.discriminator}'

        # also display members nickname, if member has one
        if member.nick:
            description += f' - [{member.name}#{member.discriminator}]'

        description += '\n'

    # generate embed
    users_embed_message = await embed_maker.message(
        ctx,
        description=description,
        author={'name': 'Members'},
        footer={'text': str(ctx.author), 'icon_url': ctx.author.avatar_url},
        send=True
    )

    # function that validates member input
    def input_check(m):
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id and m.content.isdigit()

    # wait for member input
    try:
        user_message = await ctx.bot.wait_for('message', check=input_check, timeout=20)
        await users_embed_message.delete(delay=5)
        index = user_message.content
        if index.isdigit() and len(members) >= int(index) - 1 >= 0:
            return members[int(index) - 1]
        elif not index.isdigit():
            return await embed_maker.error(ctx, 'Input is not a number')
        elif int(index) - 1 > len(members) or int(index) - 1 < 0:
            return await embed_maker.error(ctx, 'Input number out of range')

    except asyncio.TimeoutError:
        await users_embed_message.delete()
        return await embed_maker.error(ctx, 'Timeout')


class Timers:
    def __init__(self, bot: TLDR):
        self.bot = bot

    async def run_old(self):
        await self.bot.left_check.wait()

        print(f'running old timers')
        timers = db.timers.find({})
        for timer in timers:
            asyncio.create_task(self.run(timer))

    async def run(self, timer):
        now = round(time.time())

        if timer['expires'] > now:
            await asyncio.sleep(timer['expires'] - now)

        self.call_event(timer)

    def call_event(self, timer):
        timer = db.timers.find_one({'_id': ObjectId(timer['_id'])})
        if not timer:
            return

        db.timers.delete_one({'_id': ObjectId(timer['_id'])})
        self.bot.dispatch(f'{timer["event"]}_timer_over', timer)

    def create(self, *, guild_id: int, expires: int, event: str, extras: dict):
        timer_dict = {
            'guild_id': guild_id,
            'expires': expires,
            'event': event,
            'extras': extras
        }

        result = db.timers.insert_one(timer_dict)
        timer_dict['_id'] = str(result.inserted_id)
        asyncio.create_task(self.run(timer_dict))