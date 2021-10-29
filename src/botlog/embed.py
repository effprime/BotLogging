"""Module for log embeds.
"""
import discord


class LogEmbed(discord.Embed):
    title = None
    color = None

    def __init__(self, message):
        super().__init__(title=self.title.upper(), description=message, color=self.color)


class InfoEmbed(LogEmbed):
    title = "info"
    color = discord.Color.green()


class DebugEmbed(LogEmbed):
    title = "debug"
    color = discord.Color.dark_green()


class WarningEmbed(LogEmbed):
    title = "warning"
    color = discord.Color.gold()


class ErrorEmbed(LogEmbed):
    title = "error"
    color = discord.Color.red()


class EventEmbed(LogEmbed):
    title = "event"
    color = discord.Color.blurple()


def generate_log_embed(message, level):
    """Wrapper for generating a log embed.

    parameters:
        message (str): the message
        level (str): the logging level
    """
    level = level.lower()
    if level == "info":
        embed_cls = InfoEmbed
    elif level == "debug":
        embed_cls = DebugEmbed
    elif level == "warning":
        embed_cls = WarningEmbed
    elif level == "error":
        embed_cls = ErrorEmbed
    elif level == "event":
        embed_cls = EventEmbed
    else:
        raise ValueError("invalid log level provided")

    embed = embed_cls(message)

    return embed
