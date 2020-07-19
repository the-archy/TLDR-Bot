import time
import discord
import config
import re
import random
import asyncio
import os
import requests
from cogs.utils import get_member, get_user_clearance
from datetime import datetime
from discord.ext import commands
from modules import database, command, embed_maker, format_time

db = database.Connection()


async def filter_tags(ctx, bot, tags, tag_name):
    regex = re.compile(fr'({tag_name.lower()})')

    filtered_tags = list(filter(lambda t: t.lower() == tag_name.lower(), tags))
    if not filtered_tags:
        regex = re.compile(fr'({tag_name.lower()})')
        filtered_tags = list(filter(lambda t: re.findall(regex, t.lower()), tags))
        if len(filtered_tags) > 10:
            return 'Too many tag matches'

    tag = None
    if len(filtered_tags) > 1:
        embed_colour = config.EMBED_COLOUR
        tag_embed = discord.Embed(colour=embed_colour, timestamp=datetime.now())
        tag_embed.set_author(name=f'Tags')
        tag_embed.set_footer(text=f'{ctx.author}', icon_url=ctx.author.avatar_url)

        description = 'Found multiple tags, which one did you mean? `input digit of tag`\n\n'
        for i, tag in enumerate(filtered_tags):
            description += f'`#{i + 1}` | {tag}\n'

        tag_embed.description = description

        await ctx.send(embed=tag_embed)

        def user_check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        try:
            tag_message = await bot.wait_for('message', check=user_check, timeout=20)
        except asyncio.TimeoutError:
            return 'Tag Timeout'

        index = tag_message.content
        if index.isdigit() and len(filtered_tags) >= int(index) - 1 >= 0:
            tag = filtered_tags[int(index) - 1]
        elif not index.isdigit():
            return 'Input is not a number'
        elif int(index) - 1 > len(filtered_tags) or int(index) - 1 < 0:
            return 'Input number out of range'

    elif len(filtered_tags) == 1:
        tag = filtered_tags[0]
    else:
        return None

    return [tag]


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(help='See time in any location in the world', usage='time [location]', examples=['time london'],
                      clearance='User', cls=command.Command, name='time')
    async def time_in(self, ctx, location=None):
        if location is None:
            return await embed_maker.command_error(ctx)

        response = requests.get(f'https://www.time.is/{location}')
        print(response.content)

    @commands.command(help='see your or other user\'s tags', usage='tags (user)', examples=['tags', 'tags hatty'],
                      clearance='User', cls=command.Command)
    async def tags(self, ctx, user=None):
        if user is None:
            member = ctx.author
        else:
            member = await get_member(ctx, self.bot, user)
            if member is None:
                return await embed_maker.command_error(ctx, '(user)')
            elif isinstance(member, str):
                return await embed_maker.message(ctx, member, colour='red')

        tag_data = db.tags.find_one({'guild_id': ctx.guild.id})
        user_tags = [t for t in tag_data if t != 'guild_id' and t != '_id' and tag_data[t]['owner_id'] == member.id]

        desc = ''
        if not user_tags:
            desc = 'This user has no tags'
        else:
            for i, tag in enumerate(user_tags):
                desc += f'`#{i + 1}`: {tag}\n'

        embed_colour = config.EMBED_COLOUR
        tag_embed = discord.Embed(colour=embed_colour, timestamp=datetime.now(), description=desc)
        tag_embed.set_author(name=f'{str(member)} - Tags')
        tag_embed.set_footer(text=f'{ctx.author}', icon_url=ctx.author.avatar_url)

        return await ctx.send(embed=tag_embed)

    @commands.command(help='Create and use tags for common responses', usage='tag [action/tag] "(tag name)" (response)',
                      examples=['tag create "vc" We don\'t want to have VCs', 'tag vc', 'tag claim vc', 'tag edit "vc" We don\'t have VCs', 'tag delete vc'], clearance='User', cls=command.Command)
    async def tag(self, ctx, action=None, tag=None, *, response=None):
        if action is None:
            return await embed_maker.command_error(ctx)

        tag_data = db.tags.find_one({'guild_id': ctx.guild.id})
        if tag_data is None:
            await self.bot.add_collections(ctx.guild.id, 'tags')
        tags = [t for t in tag_data if t != 'guild_id' and t != '_id']
        if action not in ['create', 'claim', 'edit', 'remove']:
            tag = action
            tag = await filter_tags(ctx, self.bot, tags, tag)
            if tag is None:
                return await embed_maker.message(ctx, 'That tag doesn\'t exist', colour='red')
            elif isinstance(tag, str):
                return await embed_maker.message(ctx, tag, colour='red')
            else:
                tag = tag[0]

            response = tag_data[tag]['response']
            owner_id = tag_data[tag]['owner_id']
            owner = await get_member(ctx, self.bot, str(owner_id))

            if owner is None or isinstance(owner, str):
                response += '\n\n This tag is unclaimed'

            return await ctx.send(response)

        elif action.lower() == 'create':
            if response is None:
                # check for attachment
                if ctx.message.attachments:
                    response = ctx.message.attachments[0].url
                else:
                    return await embed_maker.command_error(ctx, '(response)')
            # max tags by user is 10, check this limit, if user is staff, limit does not apply
            user_tags = [t for t in tag_data if t != 'guild_id' and t != '_id' and tag_data[t]['owner_id'] == ctx.author.id]
            permissions = ctx.channel.permissions_for(ctx.author)
            if len(user_tags) >= 10 and not permissions.manage_messages:
                return await embed_maker.message(ctx, 'You\'ve reached your tag limit, the maximum amount of tags that one user can have is 10.', colour='red')

            if tag in ['guild_id', '_id', 'create', 'edit', 'claim', 'remove']:
                return await embed_maker.message(ctx, 'That tag name is forbidden', colour='red')

            # check if tag already exists
            if tag in tag_data:
                return await embed_maker.message(ctx, 'A tag by that name already exists', colour='red')

            tag_obj = {'response': response, 'owner_id': ctx.author.id}
            db.tags.update_one({'guild_id': ctx.guild.id}, {'$set': {f'{tag}': tag_obj}})
            return await embed_maker.message(ctx, f'Tag {tag} has been successfully created.', colour='green')

        tag = await filter_tags(ctx, self.bot, tags, tag)
        if tag is None:
            return await embed_maker.message(ctx, 'That tag doesn\'t exist', colour='red')
        elif isinstance(tag, str):
            return await embed_maker.message(ctx, tag, colour='red')
        else:
            tag = tag[0]

        owner_id = tag_data[tag]['owner_id']

        if action.lower() == 'claim':
            # check if tag owner is still in server
            owner = await get_member(ctx, self.bot, str(owner_id))
            if isinstance(owner, discord.Member):
                return await embed_maker.message(ctx, 'You can\'t claim a tag if the tag\'s owner is still in the server')
            else:
                db.tags.update_one({'guild_id': ctx.guild.id}, {'$set': {f'{tag}.owner_id': ctx.author.id}})
                return await embed_maker.message(ctx, f'You are the new owner of tag `{tag}`', colour='green')
        elif action.lower() == 'edit':
            if response is None:
                # check for attachment
                if ctx.message.attachments:
                    response = ctx.message.attachments[0].url
                else:
                    return await embed_maker.command_error(ctx, '(response)')

            # check if user is owner of tag
            if owner_id != ctx.author.id:
                return await embed_maker.message(ctx, 'You are not the owner of this tag', colour='red')

            new_tag_obj = {
                'response': response,
                'owner_id': ctx.author.id
            }
            db.tags.update_one({'guild_id': ctx.guild.id}, {'$set': {f'{tag}': new_tag_obj}})
            return await embed_maker.message(ctx, f'Tag `{tag}` has been successfully edited.', colour='green')

        elif action.lower() == 'remove':
            # check if user is owner of tag
            if owner_id != ctx.author.id:
                return await embed_maker.message(ctx, 'You are not the owner of this tag', colour='red')

            db.tags.update_one({'guild_id': ctx.guild.id}, {'$unset': {f'{tag}': ''}})
            return await embed_maker.message(ctx, f'Tag `{tag}` has been successfully removed.', colour='green')

    @commands.command(help='Get bot\'s latency', usage='ping', examples=['ping'], clearance='User', cls=command.Command)
    async def ping(self, ctx):
        message_created_at = ctx.message.created_at
        message = await ctx.send("Pong")
        ping = (datetime.utcnow() - message_created_at) * 1000
        await message.edit(content=f"\U0001f3d3 Pong   |   {int(ping.total_seconds())}ms")

    @commands.command(help='See someones profile picture', usage='pfp (user)',
                      examples=['pfp', 'pfp @Hattyot', 'pfp hattyot'], clearance='User', cls=command.Command)
    async def pfp(self, ctx, member=None):
        member = self.get_member(ctx, member)
        if member is None:
            member = ctx.author

        embed = discord.Embed(description=f'**Profile Picture of {member}**')
        embed.set_image(url=str(member.avatar_url).replace(".webp?size=1024", ".png?size=2048"))

        return await ctx.send(embed=embed)

    @commands.command(help='See info about a user', usage='userinfo (user)', examples=['userinfo', 'userinfo Hattyot'],
                      clearance='User', cls=command.Command)
    async def userinfo(self, ctx, *, user=None):
        if user is None:
            member = ctx.author
        else:
            member = await get_member(ctx, self.bot, user)
            if member is None:
                return await embed_maker.message(ctx, 'User not found', colour='red')
            elif isinstance(member, str):
                return await embed_maker.message(ctx, member, colour='red')

        embed = discord.Embed(colour=config.EMBED_COLOUR, timestamp=datetime.now())
        name = str(member)
        if member.display_name:
            name += f' - {member.display_name}'
        embed.set_author(name=name, icon_url=member.avatar_url)

        embed.add_field(name='ID', value=member.id)
        embed.add_field(name='Avatar', value=f'[link]({member.avatar_url})')
        embed.add_field(name='\u200b', value='\u200b')
        created_at = datetime.now() - member.created_at
        created_at_seconds = created_at.total_seconds()
        embed.add_field(name='Account Created', value=f'{member.created_at.strftime("%b %d %Y %H:%M")}\n{format_time.seconds(created_at_seconds)} Ago')
        joined_at = datetime.now() - member.joined_at
        joined_at_seconds = joined_at.total_seconds()
        embed.add_field(name='Joined Server', value=f'{member.joined_at.strftime("%b %d %Y %H:%M")}\n{format_time.seconds(joined_at_seconds)} Ago')
        embed.add_field(name='\u200b', value='\u200b')
        embed.add_field(name='Status', value=str(member.status), inline=False)

        embed.set_thumbnail(url=member.avatar_url)
        embed.set_footer(text=str(member), icon_url=ctx.guild.icon_url)

        return await ctx.send(embed=embed)

    @commands.command(help='Create or add to a role reaction menu identified by its name.\n You can remove roles from role menu by doing `role_menu -n [name of role menu] -e [emote]`',
                      usage='role_menu -n [name of role menu] -r [role] -e [emote] -m [message after emote]',
                      examples=['role_menu -n opt-in channels -r sports -e :football: -m opt into the tldr-footbal channel'], clearance='Mod', cls=command.Command)
    async def role_menu(self, ctx, *, args=None):
        if args is None:
            return await embed_maker.command_error(ctx)

        args = self.parse_role_menu_args(args)
        role_menu_name = args['n']
        role_name = args['r']
        emote = args['e']
        message = args['m']

        data = db.server_data.find_one({'guild_id': ctx.guild.id})
        if 'role_menus' not in data:
            db.server_data.update_one({'guild_id': ctx.guild.id}, {'$set': {'role_menus': {}}})
            data['role_menus'] = {}

        embed_colour = config.EMBED_COLOUR
        embed = discord.Embed(colour=embed_colour, timestamp=datetime.now())
        embed.set_author(name=f'Role Menu: {role_menu_name}')
        embed.set_footer(icon_url=ctx.guild.icon_url)
        description = 'React to give yourself a role\n'

        if emote and role_menu_name and not role_name and not message:
            role_menu = [rm_id for rm_id in data['role_menus'] if data['role_menus'][rm_id]['name'] == role_menu_name and data['role_menus'][rm_id]['channel_id'] == ctx.channel.id]
            if not role_menu:
                return await embed_maker.message(ctx, f'Couldn\'t find a role menu by the name: {role_menu_name}', colour='red')

            msg_id = role_menu[0]
            role_menu = data['role_menus'][msg_id]
            emote_in_menu = [r for r in role_menu['roles'] if r['emote'] == emote]
            if not emote_in_menu:
                return await embed_maker.message(ctx, f'That role menu does not contain that emote', colour='red')

            db.server_data.update_one({'guild_id': ctx.guild.id}, {'$pull': {f'role_menus.{msg_id}.roles': emote_in_menu[0]}})
            role_menu['roles'].remove(emote_in_menu[0])

            channel_id = role_menu['channel_id']
            channel = ctx.guild.get_channel(int(channel_id))
            message = await channel.fetch_message(msg_id)
            await message.add_reaction(emote)
            roles = role_menu['roles']

            # delete message if last one is removed
            if not roles:
                await message.delete()
                return await ctx.message.delete(delay=2000)

            for r in roles:
                description += f'\n{r["emote"]}: `{r["message"]}`'

            embed.description = description
            await message.edit(embed=embed)

            return await ctx.message.delete(delay=2000)

        if not role_menu_name or not role_name or not emote or not message:
            return await embed_maker.message(ctx, 'One or more of the required values is missing', colour='red')

        role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), ctx.guild.roles)
        if role is None:
            return await embed_maker.message(ctx, 'Invalid Role', colour='red')

        if role.permissions.manage_messages:
            return await embed_maker.message(ctx, 'Role Permissions are too high', colour='red')

        in_database = [rm for rm in data['role_menus'] if data['role_menus'][rm]['name'] == role_menu_name and data['role_menus'][rm]['channel_id'] == ctx.channel.id]

        rl_obj = {
            'emote': emote,
            'role_id': role.id,
            'message': message
        }

        if not in_database:
            new_role_menu_obj = {
                'channel_id': ctx.channel.id,
                'name': role_menu_name,
                'roles': [rl_obj]
            }
            description += f'\n{emote}: `{message}`'
            embed.description = description
            msg = await ctx.send(embed=embed)
            await msg.add_reaction(emote)
            db.server_data.update_one({'guild_id': ctx.guild.id}, {'$set': {f'role_menus.{msg.id}': new_role_menu_obj}})
        else:
            message_id = in_database[0]
            role_menu = data['role_menus'][str(message_id)]
            emote_duplicate = [r['emote'] for r in data['role_menus'][str(message_id)]['roles'] if r['emote'] == emote]
            if emote_duplicate:
                return await embed_maker.message(ctx, 'Duplicate emote', colour='red')

            db.server_data.update_one({'guild_id': ctx.guild.id}, {'$push': {f'role_menus.{message_id}.roles': rl_obj}})
            role_menu['roles'].append(rl_obj)
            channel_id = role_menu['channel_id']
            channel = ctx.guild.get_channel(int(channel_id))
            message = await channel.fetch_message(message_id)
            await message.add_reaction(emote)
            roles = role_menu['roles']
            for r in roles:
                description += f'\n{r["emote"]}: `{r["message"]}`'

            embed.description = description
            await message.edit(embed=embed)

        return await ctx.message.delete(delay=2000)

    @staticmethod
    def parse_role_menu_args(args):
        result = {
            'n': '',
            'r': '',
            'e': '',
            'm': ''
        }
        _args = list(filter(lambda a: bool(a), re.split(r' ?-([n|r|e|m]) ', args)))
        split_args = []
        for i in range(int(len(_args) / 2)):
            split_args.append(f'{_args[i + (i * 1)]} {_args[i + (i + 1)]}')

        for v in split_args:
            tup = tuple(map(str.strip, v.split(' ', 1)))
            if len(tup) <= 1:
                continue
            key, value = tup
            result[key] = value

        return result

    @commands.command(help='See the list of your current reminders', usage='reminders (action) (reminder index)',
                      examples=['reminders', 'reminders remove kill demons'], clearance='User', cls=command.Command)
    async def reminders(self, ctx, action=None, *, index=None):
        timer_data = db.timers.find_one({'guild_id': ctx.guild.id})
        user_reminders = [timer for timer in timer_data['timers'] if timer['event'] == 'reminder' and timer['extras']['member_id'] == ctx.author.id]
        if action is None:
            if not user_reminders:
                msg = 'You currently have no reminders'
            else:
                msg = ''
                for i, r in enumerate(user_reminders):
                    expires = r["expires"] - round(time.time())
                    msg += f'`#{i + 1}` - {r["extras"]["reminder"]} in **{format_time.seconds(expires)}**\n'

            return await embed_maker.message(ctx, msg)
        elif action not in ['remove']:
            return await embed_maker.command_error(ctx, '(action)')
        elif index is None or int(index) <= 0 or int(index) > len(user_reminders):
            return await embed_maker.command_error(ctx, '(reminder index)')
        else:
            timer = user_reminders[int(index) - 1]
            db.timers.update_one({'guild_id': ctx.guild.id}, {'$pull': {'timers': {'id': timer['id']}}})
            return await embed_maker.message(ctx, f'`{timer["extras"]["reminder"]}` has been removed from your list of reminders', colour='red')

    @commands.command(help='Create a reminder', usage='remindme [time] [reminder]',
                      examples=['remindme 24h check state of mental health', 'remindme 30m slay demons', 'remindme 10h 30m 10s stay alive'],
                      clearance='User', cls=command.Command)
    async def remindme(self, ctx, *, reminder=None):
        if reminder is None:
            return await embed_maker.command_error(ctx)

        # check for time
        remind_times = []
        remind_time_str = ''
        for i, r in enumerate(reminder.split(' ')):
            if format_time.parse(r) is not None:
                if remind_times:
                    prev_remind_time = remind_times[i - 1]
                    if prev_remind_time <= format_time.parse(r):
                        break

                remind_times.append(format_time.parse(r))
                reminder = reminder.replace(r, '', 1)
                remind_time_str += f' {r}'
            else:
                break

        if not reminder.replace(remind_time_str, '').strip():
            return await embed_maker.message(ctx, 'You cannot have an empty reminder', colour='red')

        reminder = reminder.strip()
        parsed_time = format_time.parse(remind_time_str.strip())
        if parsed_time is None:
            return await embed_maker.command_error(ctx, '[time]')

        expires = round(time.time()) + parsed_time
        utils_cog = self.bot.get_cog('Utils')
        await utils_cog.create_timer(expires=expires, guild_id=ctx.guild.id, event='reminder', extras={'reminder': reminder, 'member_id': ctx.author.id})

        return await embed_maker.message(ctx, f'Alright, in {format_time.seconds(parsed_time)} I will remind you: {reminder}')

    @commands.Cog.listener()
    async def on_reminder_timer_over(self, timer):
        guild_id = timer['guild_id']
        guild = self.bot.get_guild(int(guild_id))

        member_id = timer['extras']['member_id']
        member = guild.get_member(int(member_id))
        if member is None:
            member = await guild.fetch_member(int(member_id))
            if member is None:
                return

        reminder = timer['extras']['reminder']
        embed_colour = config.EMBED_COLOUR

        embed = discord.Embed(colour=embed_colour, description=f'Reminder: {reminder}', timestamp=datetime.now())
        embed.set_footer(text=f'{member}', icon_url=member.avatar_url)

        return await member.send(embed=embed)

    @commands.command(
        help='create a giveaway, announces y amount of winners (default 1) after x amount of time (default 24h)',
        usage='giveaway -i [item(s) you want to give away] -w [how many winners] -t [time (m/h/d)] -r (restrict giveaway to a certain role)',
        examples=['giveaway -i TLDR pin of choice -w 1 -t 7d', 'giveaway -i 1000xp -w 5 -t 24h -r Party Member'],
        clearance='Mod', cls=command.Command)
    async def giveaway(self, ctx, *, args=None):
        if args is None:
            return await embed_maker.command_error(ctx)

        args = self.parse_giveaway_args(args)
        item = args['i']
        winners = str(args['w'])
        restrict_to_role = args['r']
        giveaway_time = format_time.parse(args['t'])
        time_left = format_time.seconds(giveaway_time)
        expires = round(time.time()) + giveaway_time

        err = ''
        if args['i'] == '':
            err = 'empty items arg'
        if not winners.isdigit():
            err = 'invalid winner count'
        if giveaway_time is None:
            err = 'Invalid time arg'
        if restrict_to_role:
            role = discord.utils.find(lambda r: r.name.lower() == restrict_to_role.lower(), ctx.guild.roles)
            if not role:
                err = f'I couldn\'t find a role by the name {restrict_to_role}'
        else:
            role = ''

        if err:
            return await embed_maker.message(ctx, err, colour='red')

        role_id = '' if not role else role.id

        s = 's' if int(winners) > 1 else ''
        winner_role_str = f'\nWinner{s} will be chosen from users who have the <@&{role.id}> role' if role else ''
        description = f'React with :partying_face: to enter the giveaway!{winner_role_str}\nTime Left: **{time_left}**'
        colour = config.EMBED_COLOUR
        embed = discord.Embed(title=item, colour=colour, description=description, timestamp=datetime.now())
        embed.set_footer(text='Started at', icon_url=ctx.guild.icon_url)

        msg = await ctx.send(embed=embed)
        await msg.add_reaction('🥳')
        await ctx.message.delete(delay=3)

        utils_cog = self.bot.get_cog('Utils')
        await utils_cog.create_timer(
            expires=expires, guild_id=ctx.guild.id, event='giveaway',
            extras={
                'timer_cog': 'Utility', 'timer_function': 'giveaway_timer',
                'args': (msg.id, msg.channel.id, embed.to_dict(), giveaway_time, winners, role_id)
            }
        )

    @commands.Cog.listener()
    async def on_giveaway_timer_over(self, timer):
        message_id, channel_id, embed, _, winner_count, role_id = timer['extras']['args']
        embed = discord.Embed.from_dict(embed)
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            channel = await self.bot.fetch_channel(channel_id)

        msg = await channel.fetch_message(message_id)

        reactions = msg.reactions
        eligible = []
        for r in reactions:
            if r.emoji != '🥳':
                continue
            else:
                if not role_id:
                    eligible = await r.users().flatten()
                    # removes bot from list
                    eligible.pop(0)
                else:
                    eligible = [user for user in await r.users().flatten() if role_id in [role.id for role in user.roles]]

        winners = []
        for i in range(int(winner_count)):
            if len(eligible) == 0:
                break
            user = random.choice(eligible)
            winners.append(user.id)
            eligible.remove(user)

        winners_str = ', '.join([f'<@{w}>' for w in winners])
        if winners_str == '':
            content = ''
            if role_id:
                winners_str = 'No one won, no one eligible entered :('
            else:
                winners_str = 'No one won, no one entered :('
        else:
            content = f'🎊 Congrats to {winners_str} 🎊'

        new_desc = f'Winners: {winners_str}'
        embed.description = new_desc
        embed.set_footer(text='Ended at')
        embed.timestamp = datetime.now()
        embed.color = embed_maker.get_colour('green')
        await msg.clear_reactions()
        await msg.edit(embed=embed, content=content)

    async def giveaway_timer(self, args):
        message_id, channel_id, embed, sleep_duration, winner_count, role_id = args
        embed = discord.Embed.from_dict(embed)
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            channel = await self.bot.fetch_channel(channel_id)

        message = await channel.fetch_message(message_id)

        while sleep_duration > 0:
            s = 's' if int(winner_count) > 1 else ''
            winner_role_str = f'\nWinner{s} will be chosen from users who have the <@&{role_id}> role' if role_id else ''
            description = f'React with :partying_face: to enter the giveaway!{winner_role_str}'
            await asyncio.sleep(10)
            sleep_duration -= 10
            if sleep_duration != 0:
                time_left = format_time.seconds(sleep_duration)
                prev_time_left = format_time.seconds(sleep_duration + 10)
                if time_left == prev_time_left:
                    continue

                description += f'\nTime Left: **{time_left}**'
                embed.description = description
                await message.edit(embed=embed)

        return

    @staticmethod
    def parse_giveaway_args(args):
        result = {
            'i': '',
            'w': 1,
            't': '24h',
            'r': ''
        }
        _args = list(filter(lambda a: bool(a), re.split(r' ?-([i|w|t|r]) ', args)))
        split_args = []
        for i in range(int(len(_args) / 2)):
            split_args.append(f'{_args[i + (i * 1)]} {_args[i + (i + 1)]}')

        for v in split_args:
            tup = tuple(map(str.strip, v.split(' ', 1)))
            if len(tup) <= 1:
                continue
            key, value = tup
            result[key] = value

        return result

    @commands.command(help='Create an anonymous poll. with options adds numbers as reactions, without it just adds thumbs up and down. after x minutes (default 5) is up, results are displayed',
                      usage='anon_poll [-q question] (-o option1, option2, ...)/(-o [emote: option], [emote: option], ...) (-t [time (m/h/d) (-u update interval)',
                      examples=['anon_poll -q best food? -o pizza, burger, fish and chips, salad', 'anon_poll -q Do you guys like pizza? -t 2m', 'anon_poll -q Where are you from? -o [🇩🇪: Germany], [🇬🇧: UK] -t 1d -u 1m'],
                      clearance='Mod', cls=command.Command)
    async def anon_poll(self, ctx, *, args=None):
        if args is None:
            return await embed_maker.command_error(ctx)

        args = self.parse_poll_args(args)
        question = args['q']
        options = args['o']
        poll_time = format_time.parse(args['t'])
        option_emotes = args['o_emotes']
        update_interval = args['u']

        err = ''
        if poll_time is None:
            err = 'Invalid time arg'

        if option_emotes is None:
            err = 'Error with custom option emotes'

        if question == '' or options == '':
            err = 'Empty arg'

        if len(options) > 9:
            err = 'Too many options'
        if len(options) < 2:
            err = 'Too few options'

        if update_interval and format_time.parse(update_interval) is None:
            err = 'Invalid update interval time'
        else:
            update_interval = format_time.parse(update_interval)
            if update_interval < 30:
                err = 'Update interval can\'t be smaller than 30 seconds'

        if err:
            return await embed_maker.message(ctx, err, colour='red')

        description = f'**"{question}"**\n\n'
        colour = config.EMBED_COLOUR
        embed = discord.Embed(title='Anonymous Poll', colour=colour, description=description, timestamp=datetime.now())
        embed.set_footer(text='Started at', icon_url=ctx.guild.icon_url)

        if not options:
            emotes = ['👍', '👎']
        else:
            if option_emotes:
                emotes = list(option_emotes.keys())
                options = list(option_emotes.values())
            else:
                all_num_emotes = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣']
                emotes = all_num_emotes[:len(options)]

            description += '\n\n'.join(f'{e} | **{o}**' for o, e in zip(options, emotes))
            embed.description = description

        poll_msg = await ctx.send(embed=embed)

        embed_colour = config.EMBED_COLOUR
        embed = discord.Embed(colour=embed_colour, timestamp=datetime.now())
        embed.set_footer(text=f'{ctx.guild.name}', icon_url=ctx.guild.icon_url)
        embed.title = f'**"{question}"**'

        async def count(user, msg, emote):
            if msg.id != poll_msg.id:
                return

            data = db.polls.find_one({'guild_id': ctx.guild.id})
            if str(user.id) in data['polls'][str(msg.id)]:

                voted = data['polls'][str(msg.id)][str(user.id)]['voted']
                print(voted)
                if voted:
                    embed.description = f'You have already voted'
                    return await user.send(embed=embed)

            db.polls.update_one({'guild_id': ctx.guild.id}, {'$inc': {f'polls.{msg.id}.{emote.name}': 1}})
            db.polls.update_one({'guild_id': ctx.guild.id}, {'$set': {f'polls.{msg.id}.{user.id}.voted': True}})

            embed.description = f'Your vote has been counted towards: {emote}'
            return await user.send(embed=embed)

        poll = dict.fromkeys(emotes, 0)
        buttons = dict.fromkeys(emotes, count)

        utils_cog = self.bot.get_cog('Utils')
        if update_interval:
            expires = round(time.time()) + round(update_interval)
        else:
            expires = round(time.time()) + round(poll_time)

        extras = {
            'message_id': poll_msg.id,
            'channel_id': poll_msg.channel.id,
            'question': question,
            'options': dict(zip(emotes, options)),
            'update_interval': 0,
            'true_expire': 0
        }
        if update_interval:
            extras['update_interval'] = update_interval
            extras['true_expire'] = round(time.time()) + poll_time

        await utils_cog.create_timer(expires=expires, guild_id=ctx.guild.id, event='anon_poll', extras=extras)
        await utils_cog.new_no_expire_menu(poll_msg, buttons)

        db.polls.update_one({'guild_id': ctx.guild.id}, {'$set': {f'polls.{poll_msg.id}': poll}})

        return await ctx.message.delete(delay=3)

    @commands.Cog.listener()
    async def on_anon_poll_timer_over(self, timer):
        message_id = timer['extras']['message_id']
        channel_id = timer['extras']['channel_id']
        guild_id = timer['guild_id']
        options = timer['extras']['options']
        update_interval = timer['extras']['update_interval']
        true_expire = timer['extras']['true_expire']

        data = db.polls.find_one({'guild_id': guild_id})

        if str(message_id) not in data['polls']:
            return

        question = timer['extras']['question']
        poll = data['polls'][str(message_id)]
        emote_count = poll
        channel = self.bot.get_channel(channel_id)
        message = await channel.fetch_message(message_id)
        total_emotes = sum([v for v in emote_count.values() if isinstance(v, int)])
        description = f'**"{question}"**\n\n'

        if total_emotes == 0:
            # just incase nobody participated
            description += '\n\n'.join(f'{emote} - {options[emote]} - **{emote_count}** | **0%**' for emote, emote_count in emote_count.items() if emote in options)
        else:
            description += '\n\n'.join(f'{emote} - {options[emote]} - **{emote_count}** | **{round((emote_count * 100) / total_emotes)}%**' for emote, emote_count in emote_count.items() if emote in options)

        old_embed = message.embeds[0].to_dict()
        embed = message.embeds[0]
        embed.description = description
        embed.timestamp = datetime.fromtimestamp(true_expire)
        if update_interval:
            embed.set_footer(text=f'Updates every {format_time.seconds(update_interval)} | Ends at')
        else:
            embed.set_footer(text='Ended at')

        if old_embed != embed.to_dict():
            await message.edit(embed=embed)

        utils_cog = self.bot.get_cog('Utils')
        # check if poll passed true expire
        expired = round(time.time()) > true_expire
        if expired:
            if message_id in utils_cog.no_expire_menus:
                del utils_cog.no_expire_menus[message_id]

            db.polls.update_one({'guild_id': guild_id}, {'$unset': {f'polls.{message_id}': ''}})
            await message.clear_reactions()

            # send message about poll being completed
            return await channel.send(
                f'Poll finished: https://discordapp.com/channels/{guild_id}/{channel_id}/{message_id}')

        # run poll timer again if needed
        elif update_interval:
            expires = round(time.time()) + round(update_interval)
            return await utils_cog.create_timer(expires=expires, guild_id=timer['guild_id'], event='anon_poll', extras=timer['extras'])

    @commands.command(help='Create a poll. with options adds numbers as reactions, without it just adds thumbs up and down.',
                      usage='poll [-q question] (-o option1 | option2 | ...)/(-o [emote: option], [emote: option], ...)',
                      examples=['poll -q best food? -o pizza, burger, fish and chips, salad -l 2', 'poll -q Do you guys like pizza?', 'anon_poll -q Where are you from? -o [🇩🇪: Germany], [🇬🇧: UK]'],
                      clearance='Mod', cls=command.Command)
    async def poll(self, ctx, *, args=None):
        if args is None:
            return await embed_maker.command_error(ctx)

        args = self.parse_poll_args(args)
        question = args['q']
        options = args['o']
        option_emotes = args['o_emotes']

        err = ''
        if question == '' or options == '':
            err = 'Empty arg'

        if len(options) > 9:
            err = 'Too many options'
        if len(options) < 2:
            err = 'Too few options'

        if err:
            return await embed_maker.message(ctx, err, colour='red')

        description = f'**"{question}"**\n'
        colour = config.EMBED_COLOUR
        embed = discord.Embed(colour=colour, description=description, timestamp=datetime.now())
        embed.set_author(name='Poll')
        embed.set_footer(text='Started at', icon_url=ctx.guild.icon_url)

        if not options:
            emotes = ['👍', '👎']
        else:
            if option_emotes:
                emotes = list(option_emotes.keys())
                options = list(option_emotes.values())
            else:
                all_num_emotes = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣']
                emotes = all_num_emotes[:len(options)]

            description += '\n'.join(f'\n{e} | **{o}**' for e, o in zip(emotes, options))
            embed.description = description

        poll_msg = await ctx.send(embed=embed)
        for e in emotes:
            await poll_msg.add_reaction(e)

        return await ctx.message.delete(delay=5)

    @staticmethod
    def parse_poll_args(args):
        result = {
            'q': '',
            'o': [],
            't': '5m',
            'o_emotes': {},
            'u': ''
        }
        _args = list(filter(lambda a: bool(a), re.split(r' ?-([t|o|q|u]) ', args)))
        split_args = []
        for i in range(int(len(_args)/2)):
            split_args.append(f'{_args[i + (i * 1)]} {_args[i + (i + 1)]}')

        for a in split_args:
            tup = tuple(map(str.strip, a.split(' ', 1)))
            if len(tup) <= 1:
                continue
            key, value = tup
            result[key] = value

        if result['o']:
            result['o'] = [r.strip() for r in result['o'].split('|')]
        else:
            return result

        # check for custom option emotes
        oe_regex = re.compile(r'\[(.*):(.*)\]')
        if re.match(oe_regex, result['o'][0]):
            for option in result['o']:
                oe = re.findall(oe_regex, option)
                if oe:
                    e, o = oe[0]
                    e = e.strip()
                    result['o_emotes'][e] = o
                    continue

                result['o_emotes'] = None
                break

        return result

    @commands.command(help='Get help smh', usage='help (command)', examples=['help', 'help ping'],
                      clearance='User', cls=command.Command)
    async def help(self, ctx, _cmd=None):
        embed_colour = config.EMBED_COLOUR
        prefix = config.PREFIX
        all_commands = self.bot.commands
        help_object = {}
        data = db.server_data.find_one({'guild_id': ctx.guild.id})

        for cmd in all_commands:
            if hasattr(cmd, 'dm_only'):
                continue

            if 'commands' in data and 'disabled' in data['commands'] and cmd.name in data['commands']['disabled']:
                continue

            # Check if cog is levels and if cmd requires mod perms
            if cmd.cog_name == 'Leveling' and 'Leveling - Staff' not in help_object:
                help_object['Leveling - Staff'] = []
            if cmd.cog_name == 'Leveling' and cmd.clearance != 'User':
                help_object['Leveling - Staff'].append(cmd)
                continue

            if cmd.cog_name not in help_object:
                help_object[cmd.cog_name] = [cmd]
            else:
                help_object[cmd.cog_name].append(cmd)

        clearance = get_user_clearance(ctx.author)

        # check if user has special access
        access_given = []
        access_taken = []
        if 'commands' in data and 'access' in data['commands'] and 'users' in data['commands']['access'] and 'roles' in data['commands']['access']:
            command_data = data['commands']['access']
            # check if user has special access
            cmd_access_list = []
            if str(ctx.author.id) in command_data['users']:
                cmd_access_list += [c for c in command_data['users'][str(ctx.author.id)]]
            if set([str(r.id) for r in ctx.author.roles]) & set(command_data['roles'].keys()):
                cmd_access_list += [command_data['roles'][c] for c in command_data['roles'] if c in [str(r.id) for r in ctx.author.roles]]

            access_given = [c['command'] for c in cmd_access_list if c['type'] == 'give']
            access_taken = [c['command'] for c in cmd_access_list if c['type'] == 'take']

        if _cmd is None:
            embed = discord.Embed(
                colour=embed_colour, timestamp=datetime.now(),
                description=f'**Prefix** : `{prefix}`\nFor additional info on a command, type `{prefix}help [command]`'
            )
            embed.set_author(name=f'Help - {clearance[0]}', icon_url=ctx.guild.icon_url)
            embed.set_footer(text=f'{ctx.author}', icon_url=ctx.author.avatar_url)

            # get special access commands
            special_access_cmds = []

            # add special access field
            if access_given:
                special_access_cmds += [c for c in access_given]

            # remove duplicates
            special_access_cmds = list(dict.fromkeys(special_access_cmds))

            for cat in help_object:
                cat_commands = []
                for cmd in help_object[cat]:
                    if cmd.name in access_taken:
                        continue
                    if cmd.clearance in clearance:
                        cat_commands.append(cmd.name)

                if cat_commands:
                    # remove command from special_access_cmds if user already has access to it
                    common = set(special_access_cmds) & set(cat_commands)
                    if common:
                        for r in common:
                            special_access_cmds.remove(r)

                    embed.add_field(name=f'>{cat}', value=" \| ".join([f'`{c}`' for c in cat_commands]), inline=False)

            if special_access_cmds:
                embed.add_field(name=f'>Special Access', value=" \| ".join([f'`{c}`' for c in special_access_cmds]), inline=False)

            return await ctx.send(embed=embed)
        else:
            if self.bot.get_command(_cmd):
                cmd = self.bot.get_command(_cmd)
                if cmd.hidden:
                    return

                if 'commands' in data and 'disabled' in data['commands'] and cmd.name in data['commands']['disabled']:
                    return

                if access_taken:
                    return
                if ctx.command.clearance not in clearance and not cmd in access_given:
                    return

                examples = f' | {prefix}'.join(cmd.examples)
                cmd_help = f"""
                **Description:** {cmd.help}
                **Usage:** {prefix}{cmd.usage}
                **Examples:** {prefix}{examples}
                """
                embed = discord.Embed(colour=embed_colour, timestamp=datetime.now(), description=cmd_help)
                embed.set_author(name=f'Help - {cmd}', icon_url=ctx.guild.icon_url)
                embed.set_footer(text=f'{ctx.author}', icon_url=ctx.author.avatar_url)
                return await ctx.send(embed=embed)
            else:
                return await embed_maker.message(ctx, f'{_cmd} is not a valid command')

    @commands.command(hidden=True, help='View source code of any command',
                      usage='source (command)', examples=['source', 'source pfp'],
                      clearance='User', cls=command.Command, aliases=['src'])
    async def source(self, ctx, *, command=None):
        u = '\u200b'
        if not command:
            return await embed_maker.message(ctx, 'Check out the full sourcecode on GitHub\nhttps://github.com/Hattyot/TLDR-Bot')

        src = f"```py\n{str(__import__('inspect').getsource(self.bot.get_command(command).callback)).replace('```', f'{u}')}```"
        if len(src) > 2000:
            cmd = self.bot.get_command(command).callback
            if not cmd:
                return await ctx.send("Command not found.")
            file = cmd.__code__.co_filename
            location = os.path.relpath(file)
            total, fl = __import__('inspect').getsourcelines(cmd)
            ll = fl + (len(total) - 1)
            return await embed_maker.message(ctx, f"This code was too long for Discord, you can see it instead [on GitHub](https://github.com/Hattyot/TLDR-Bot/blob/master/{location}#L{fl}-L{ll})")
        else:
            await ctx.send(src)


def setup(bot):
    bot.add_cog(Utility(bot))
