import discord
import config
from discord.ext import commands
from modules import database, embed_maker, command
from datetime import datetime

db = database.Connection()


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(help='Get help smh', usage='help (command)', examples=['help', 'help ping'], clearance='User', cls=command.Command)
    async def help(self, ctx, _cmd=None):
        embed_colour = config.DEFAULT_EMBED_COLOUR
        prefix = config.DEFAULT_PREFIX
        cmds = self.bot.commands
        help_object = {}
        for cmd in cmds:
            if hasattr(cmd, 'dm_only'):
                continue

            if cmd.cog_name not in help_object:
                help_object[cmd.cog_name] = [cmd]
            else:
                help_object[cmd.cog_name].append(cmd)

        clearance = ctx.author_clearance
        if _cmd is None:
            embed = discord.Embed(colour=embed_colour, timestamp=datetime.now(), description=f'**Prefix** : `{prefix}`\nFor additional info on a command, type `{prefix}help [command]`')
            embed.set_author(name=f'Help - {clearance[0]}', icon_url=ctx.guild.icon_url)
            embed.set_footer(text=f'{ctx.author}', icon_url=ctx.author.avatar_url)
            for cat in help_object:
                cat_commands = []
                for cmd in help_object[cat]:
                    if cmd.clearance in clearance:
                        cat_commands.append(f'`{cmd}`')

                if cat_commands:
                    embed.add_field(name=f'>{cat}', value=" \| ".join(cat_commands), inline=False)

            return await ctx.send(embed=embed)
        else:
            if self.bot.get_command(_cmd):
                cmd = self.bot.get_command(_cmd)
                if cmd.hidden:
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
                embed = embed_maker.message(ctx, f'{_cmd} is not a valid command')
                return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(General(bot))
