"""Module for logging bot events.
"""

import asyncio
import datetime
import logging
import os
import traceback

import discord
import munch
import botlog.embed as embed_lib


class DelayedLog:
    """Represents log data to be sent.

    parameters:
        level (str): the log level (eg. INFO, DEBUG, WARNING, EVENT)
        message (str): the log message
        args (tuple): optional positional arguments
        kwargs (dict): optional keyword arguments
    """

    # pylint: disable=redefined-outer-name
    def __init__(self, level, *args, log_message=None, **kwargs):
        self.level = level
        self.message = log_message
        self.args = args
        self.kwargs = kwargs
        self.kwargs["time"] = datetime.datetime.utcnow()


class BotLogger:
    """Logging channel interface for the bot.

    parameters:
        bot (bot.BasementBot): the bot object
        name (str): the name of the logging channel
        queue (bool): True if a queue should be used for writing logs
    """

    # this defaults to False because most logs shouldn't send out
    DEFAULT_LOG_SEND = False
    # this defaults to True because most error logs should send out
    DEFAULT_ERROR_LOG_SEND = True

    def __init__(self, **kwargs):
        self.bot = kwargs.get("bot")

        try:
            self.debug_mode = bool(int(os.environ.get("DEBUG", 0)))
        except ValueError:
            self.debug_mode = False

        # pylint: disable=using-constant-test
        logging.basicConfig(
            level=logging.DEBUG if self.debug_mode else logging.INFO)

        self.console = logging.getLogger(kwargs.get("name", "root"))

        self.queue_wait = kwargs.get("queue_wait")
        self.send_queue = asyncio.Queue(
            maxsize=1000) if self.queue_wait else None

        self.send = kwargs.get("send")

        if self.queue_wait:
            self.bot.loop.create_task(self.log_from_queue())

    async def info(self, message, *args, **kwargs):
        """Logs at the INFO level.

        parameters:
            message (str): the message to log
            send (bool): The reverse of the above (overrides console_only)
            channel (int): the ID of the channel to send the log to
        """
        if self.queue_wait:
            await self.send_queue.put(
                DelayedLog(level="info", log_message=message, *args, **kwargs)
            )
            return

        await self.handle_generic_log(
            message, "info", self.console.info, *args, **kwargs
        )

    async def debug(self, message, *args, **kwargs):
        """Logs at the DEBUG level.

        parameters:
            message (str): the message to log
            send (bool): The reverse of the above (overrides console_only)
            channel (int): the ID of the channel to send the log to
        """
        if not self.debug_mode:
            return

        if self.queue_wait:
            await self.send_queue.put(
                DelayedLog(level="debug", log_message=message, *args, **kwargs)
            )
            return

        await self.handle_generic_log(
            message, "debug", self.console.debug, *args, **kwargs
        )

    async def warning(self, message, *args, **kwargs):
        """Logs at the WARNING level.

        parameters:
            message (str): the message to log
            send (bool): The reverse of the above (overrides console_only)
            channel (int): the ID of the channel to send the log to
        """
        if self.queue_wait:
            await self.send_queue.put(
                DelayedLog(level="warning",
                           log_message=message, *args, **kwargs)
            )
            return

        await self.handle_generic_log(
            message, "warning", self.console.warning, *args, **kwargs
        )

    async def handle_generic_log(self, message, level_, console, *args, **kwargs):
        """Handles most logging contexts.

        parameters:
            message (str): the message to log
            level (str): the logging level
            console (func): logging level method
            send (bool): The reverse of the above (overrides console_only)
            channel (int): the ID of the channel to send the log to
        """
        console_only = self._is_console_only(kwargs, is_error=False)

        channel_id = kwargs.get("channel", None)

        console(message)

        if console_only:
            return

        channel = self.bot.get_channel(int(channel_id)) if channel_id else None

        if channel:
            target = channel
        else:
            target = await self.bot.get_owner()

        if not target:
            self.console.warning(
                f"Could not determine Discord target to send {level_} log"
            )
            return

        embed = embed_lib.generate_log_embed(message, level_)
        embed.timestamp = kwargs.get("time", datetime.datetime.utcnow())

        try:
            await target.send(embed=embed)
        except discord.Forbidden:
            pass

    async def event(self, event_type, *args, **kwargs):
        """Logs at the EVENT level.

        This provides an interface for logging Discord events (eg, on_member_update)

        parameters:
            event_type (str): the event type suffix
            send (bool): The reverse of the above (overrides console_only)
            channel (int): the ID of the channel to send the log to
        """
        if self.queue_wait:
            kwargs["event_type"] = event_type
            await self.send_queue.put(DelayedLog(level="event", *args, **kwargs))
            return

        await self.handle_event_log(event_type, *args, **kwargs)

    async def handle_event_log(self, event_type, *args, **kwargs):
        """Handles event logging.

        parameters:
            event_type (str): the event type suffix
            send (bool): The reverse of the above (overrides console_only)
            channel (int): the ID of the channel to send the log to
        """
        console_only = self._is_console_only(kwargs, is_error=False)

        channel_id = kwargs.get("channel", None)

        event_data = self.generate_event_data(event_type, *args, **kwargs)
        if not event_data:
            return

        message = event_data.get("message")
        if not message:
            return

        # events are a special case of the INFO level
        self.console.info(message)

        if console_only:
            return

        channel = self.bot.get_channel(int(channel_id)) if channel_id else None

        if channel:
            target = channel
        else:
            target = await self.bot.get_owner()

        if not target:
            self.console.warning(
                "Could not determine Discord target to send EVENT log")
            return

        embed = event_data.get("embed")
        if not embed:
            return

        embed.timestamp = kwargs.get("time", datetime.datetime.utcnow())

        try:
            await target.send(embed=embed)
        except discord.Forbidden:
            pass

    async def error(self, message, *args, **kwargs):
        """Logs at the ERROR level.

        parameters:
            message (str): the message to log
            exception (Exception): the exception object
            send (bool): The reverse of the above (overrides console_only)
            channel (int): the ID of the channel to send the log to
            critical (bool): True if the critical error handler should be invoked
        """
        if self.queue_wait:
            await self.send_queue.put(
                DelayedLog(level="error", log_message=message, *args, **kwargs)
            )
            return
        await self.handle_error_log(message, *args, **kwargs)

    async def handle_error_log(self, message, *args, **kwargs):
        """Handles error logging.

        parameters:
            message (str): the message to log with the error
            exception (Exception): the exception object
            send (bool): The reverse of the above (overrides console_only)
            channel (int): the ID of the channel to send the log to
            critical (bool): True if the critical error handler should be invoked
        """
        exception = kwargs.get("exception", None)
        critical = kwargs.get("critical")
        channel_id = kwargs.get("channel", None)
        console_only = self._is_console_only(kwargs, is_error=True)

        self.console.error(message)

        if console_only:
            return

        exception_string = "".join(
            traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
        )
        exception_string = exception_string[:1992]

        embed = embed_lib.generate_log_embed(message, "error")
        embed.timestamp = kwargs.get("time", datetime.datetime.utcnow())

        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
        else:
            channel = None

        # tag user if critical
        if channel:
            content = channel.guild.owner.mention if critical else None
            target = channel
        else:
            target = await self.bot.get_owner()
            content = target.mention if critical else None

        if not target:
            self.console.warning(
                "Could not determine Discord target to send ERROR log")
            return

        try:
            await target.send(content=content, embed=embed)
            await target.send(f"```py\n{exception_string}```")
        except discord.Forbidden:
            pass

    def _is_console_only(self, kwargs, is_error):
        """Determines from a kwargs dict if console_only is absolutely True.

        This is so `send` can be provided as a convenience arg.

        parameters:
            kwargs (dict): the kwargs to parse
            is_error (bool): True if the decision is for an error log
        """
        # check if sending is disabled globally
        if not self.send:
            return True
        default_send = (
            self.DEFAULT_ERROR_LOG_SEND if is_error else self.DEFAULT_LOG_SEND
        )
        return not kwargs.get("send", default_send)

    # pylint: disable=inconsistent-return-statements
    def generate_event_data(self, event_type, *args, **kwargs):
        """Generates an event message and embed.

        parameters:
            event_type (str): the event type suffix
        """
        message = None
        embed = None

        # hacky AF but I love it
        render_func_name = f"render_{event_type}_event"
        render_func = getattr(self, render_func_name,
                              self.render_default_event)

        kwargs["event_type"] = event_type

        try:
            message, embed = render_func(*args, **kwargs)
        except Exception as exception:
            self.console.error(
                f"Could not render event data: {exception} (using default render)"
            )
            message, embed = self.render_default_event(*args, **kwargs)

        return {"message": message, "embed": embed}

    def render_default_event(self, *args, **kwargs):
        """Renders the message and embed for the default case."""
        event_type = kwargs.get("event_type")

        message = f"New event: {event_type}"
        embed = embed_lib.generate_log_embed(message, "event")

        return message, embed

    def render_command_event(self, *args, **kwargs):
        """Renders the named event."""
        ctx = kwargs.get("context", kwargs.get("ctx"))
        server_text = self.get_server_text(ctx)

        sliced_content = f"Command detected: `{ctx.message.content[:100]}`"
        message = f"Command detected: {sliced_content}"

        embed = embed_lib.generate_log_embed(sliced_content, "event")
        embed.add_field(name="User", value=ctx.author)
        embed.add_field(name="Channel", value=getattr(
            ctx.channel, "name", "DM"))
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_message_delete_event(self, *args, **kwargs):
        """Renders the named event."""
        message_object = kwargs.get("message")
        server_text = self.get_server_text(message_object)

        message = f"Message with ID {message_object.id} deleted"

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="Content", value=message_object.content or "None")
        embed.add_field(name="Author", value=message_object.author)
        embed.add_field(
            name="Channel",
            value=getattr(message_object.channel, "name", "DM"),
        )
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_message_edit_event(self, *args, **kwargs):
        """Renders the named event."""
        before = kwargs.get("before")
        after = kwargs.get("after")

        attrs = ["content", "embeds"]
        diff = self.get_object_diff(before, after, attrs)

        server_text = self.get_server_text(before.channel)

        message = f"Message edit detected on message with ID {before.id}"

        embed = embed_lib.generate_log_embed(message, "event")

        embed = self.add_diff_fields(embed, diff)

        embed.add_field(name="Author", value=before.author)
        embed.add_field(name="Channel", value=getattr(
            before.channel, "name", "DM"))
        embed.add_field(
            name="Server",
            value=server_text,
        )

        return message, embed

    def render_bulk_message_delete_event(self, *args, **kwargs):
        """Renders the named event."""
        messages = kwargs.get("messages")

        unique_channels = set()
        unique_servers = set()
        for message in messages:
            unique_channels.add(message.channel.name)
            unique_servers.add(
                f"{message.channel.guild.name} ({message.channel.guild.id})"
            )

        message = f"{len(messages)} messages bulk deleted!"

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="Channels", value=",".join(unique_channels))
        embed.add_field(name="Servers", value=",".join(unique_servers))

        return message, embed

    def render_reaction_add_event(self, *args, **kwargs):
        """Renders the named event."""
        reaction = kwargs.get("reaction")
        user = kwargs.get("user")
        server_text = self.get_server_text(reaction.message.channel)

        message = f"Reaction added to message with ID {reaction.message.id} by user with ID {user.id}"

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="Emoji", value=reaction.emoji)
        embed.add_field(name="User", value=user)
        embed.add_field(
            name="Message", value=reaction.message.content or "None")
        embed.add_field(name="Message Author", value=reaction.message.author)
        embed.add_field(
            name="Channel", value=getattr(reaction.message.channel, "name", "DM")
        )
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_reaction_remove_event(self, *args, **kwargs):
        """Renders the named event."""
        reaction = kwargs.get("reaction")
        user = kwargs.get("user")
        server_text = self.get_server_text(reaction.message.channel)

        message = f"Reaction removed from message with ID {reaction.message.id} by user with ID {user.id}"

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="Emoji", value=reaction.emoji)
        embed.add_field(name="User", value=user)
        embed.add_field(
            name="Message", value=reaction.message.content or "None")
        embed.add_field(name="Message Author", value=reaction.message.author)
        embed.add_field(
            name="Channel", value=getattr(reaction.message.channel, "name", "DM")
        )
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_reaction_clear_event(self, *args, **kwargs):
        """Renders the named event."""
        message = kwargs.get("message")
        reactions = kwargs.get("reactions")
        server_text = self.get_server_text(message.channel)

        message = f"{len(reactions)} cleared from message with ID {message.id}"

        unique_emojis = set()
        for reaction in reactions:
            unique_emojis.add(reaction.emoji)

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="Emojis", value=",".join(unique_emojis))
        embed.add_field(name="Message", value=message.content or "None")
        embed.add_field(name="Message Author", value=message.author)
        embed.add_field(name="Channel", value=getattr(
            message.channel, "name", "DM"))
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_guild_channel_delete_event(self, *args, **kwargs):
        """Renders the named event."""
        channel = kwargs.get("channel_")
        server_text = self.get_server_text(channel)

        message = (
            f"Channel with ID {channel.id} deleted in guild with ID {channel.guild.id}"
        )

        embed = embed_lib.generate_log_embed(message, "event")

        embed.add_field(name="Channel Name", value=channel.name)
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_guild_channel_create_event(self, *args, **kwargs):
        """Renders the named event."""
        channel = kwargs.get("channel_")
        server_text = self.get_server_text(channel)

        message = (
            f"Channel with ID {channel.id} created in guild with ID {channel.guild.id}"
        )

        embed = embed_lib.generate_log_embed(message, "event")

        embed.add_field(name="Channel Name", value=channel.name)
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_guild_channel_update_event(self, *args, **kwargs):
        """Renders the named event."""
        before = kwargs.get("before")
        after = kwargs.get("after")
        server_text = self.get_server_text(before)

        attrs = [
            "category",
            "changed_roles",
            "name",
            "overwrites",
            "permissions_synced",
            "position",
        ]
        diff = self.get_object_diff(before, after, attrs)

        message = (
            f"Channel with ID {before.id} modified in guild with ID {before.guild.id}"
        )

        embed = embed_lib.generate_log_embed(message, "event")

        embed = self.add_diff_fields(embed, diff)

        embed.add_field(name="Channel Name", value=before.name)
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_guild_channel_pins_update_event(self, *args, **kwargs):
        """Renders the named event."""
        channel = kwargs.get("channel_")
        # last_pin = kwargs.get("last_pin")
        server_text = self.get_server_text(channel)

        message = f"Channel pins updated in channel with ID {channel.id} in guild with ID {channel.guild.id}"

        embed = embed_lib.generate_log_embed(message, "event")

        embed.add_field(name="Channel Name", value=channel.name)
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_guild_integrations_update_event(self, *args, **kwargs):
        """Renders the named event."""
        guild = kwargs.get("guild")
        server_text = self.get_server_text(None, guild=guild)

        message = f"Integrations updated in guild with ID {guild.id}"

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_webhooks_update_event(self, *args, **kwargs):
        """Renders the named event."""
        channel = kwargs.get("channel_")
        server_text = self.get_server_text(channel)

        message = f"Webooks updated for channel with ID {channel.id} in guild with ID {channel.guild.id}"

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="Channel", value=channel.name)
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_member_join_event(self, *args, **kwargs):
        """Renders the named event."""
        member = kwargs.get("member")
        server_text = self.get_server_text(member)

        message = (
            f"Member with ID {member.id} has joined guild with ID {member.guild.id}"
        )
        embed = embed_lib.generate_log_embed(message, "event")

        embed.add_field(name="Member", value=member)
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_member_remove_event(self, *args, **kwargs):
        """Renders the named event."""
        member = kwargs.get("member")
        server_text = self.get_server_text(member)

        message = f"Member with ID {member.id} has left guild with ID {member.guild.id}"
        embed = embed_lib.generate_log_embed(message, "event")

        embed.add_field(name="Member", value=member)
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_member_update_event(self, *args, **kwargs):
        """Renders the named event."""
        before = kwargs.get("before")
        after = kwargs.get("after")
        server_text = self.get_server_text(before)

        attrs = ["avatar_url", "avatar", "nick", "roles", "status"]
        diff = self.get_object_diff(before, after, attrs)

        message = (
            f"Member with ID {before.id} was updated in guild with ID {before.guild.id}"
        )

        if diff:
            embed = embed_lib.generate_log_embed(message, "event")

            embed = self.add_diff_fields(embed, diff)

            embed.add_field(name="Member", value=before)
            embed.add_field(name="Server", value=server_text)
        else:
            # avoid spamming of member activity changes
            message, embed = None, None

        return message, embed

    def render_guild_join_event(self, *args, **kwargs):
        """Renders the named event."""
        guild = kwargs.get("guild")
        server_text = self.get_server_text(None, guild=guild)

        message = f"Joined guild with ID {guild.id}"

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_guild_remove_event(self, *args, **kwargs):
        """Renders the named event."""
        guild = kwargs.get("guild")
        server_text = self.get_server_text(None, guild=guild)

        message = f"Left guild with ID {guild.id}"

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_guild_update_event(self, *args, **kwargs):
        """Renders the named event."""
        before = kwargs.get("before")
        after = kwargs.get("after")
        server_text = self.get_server_text(None, guild=before)

        attrs = [
            "banner",
            "banner_url",
            "bitrate_limit",
            "categories",
            "default_role",
            "description",
            "discovery_splash",
            "discovery_splash_url",
            "emoji_limit",
            "emojis",
            "explicit_content_filter",
            "features",
            "icon",
            "icon_url",
            "name",
            "owner",
            "region",
            "roles",
            "rules_channel",
            "verification_level",
        ]
        diff = self.get_object_diff(before, after, attrs)

        message = f"Guild with ID {before.id} updated"

        embed = embed_lib.generate_log_embed(message, "event")

        embed = self.add_diff_fields(embed, diff)

        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_guild_role_create_event(self, *args, **kwargs):
        """Renders the named event."""
        role = kwargs.get("role")
        server_text = self.get_server_text(role)

        message = (
            f"New role with name {role.name} added to guild with ID {role.guild.id}"
        )

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_guild_role_delete_event(self, *args, **kwargs):
        """Renders the named event."""
        role = kwargs.get("role")
        server_text = self.get_server_text(role)

        message = (
            f"Role with name {role.name} deleted from guild with ID {role.guild.id}"
        )

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_guild_role_update_event(self, *args, **kwargs):
        """Renders the named event."""
        before = kwargs.get("before")
        after = kwargs.get("after")
        server_text = self.get_server_text(before)

        attrs = ["color", "mentionable", "name",
                 "permissions", "position", "tags"]
        diff = self.get_object_diff(before, after, attrs)

        message = (
            f"Role with name {before.name} updated in guild with ID {before.guild.id}"
        )

        embed = embed_lib.generate_log_embed(message, "event")

        embed = self.add_diff_fields(embed, diff)

        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_guild_emojis_update_event(self, *args, **kwargs):
        """Renders the named event."""
        guild = kwargs.get("guild")
        # before = kwargs.get("before")
        # after = kwargs.get("after")
        server_text = self.get_server_text(None, guild=guild)

        message = f"Emojis updated in guild with ID {guild.id}"

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_member_ban_event(self, *args, **kwargs):
        """Renders the named event."""
        guild = kwargs.get("guild")
        user = kwargs.get("user")
        server_text = self.get_server_text(None, guild=guild)

        message = f"User with ID {user.id} banned from guild with ID {guild.id}"

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="User", value=user)
        embed.add_field(name="Server", value=server_text)

        return message, embed

    def render_member_unban_event(self, *args, **kwargs):
        """Renders the named event."""
        guild = kwargs.get("guild")
        user = kwargs.get("user")
        server_text = self.get_server_text(None, guild=guild)

        message = f"User with ID {user.id} unbanned from guild with ID {guild.id}"

        embed = embed_lib.generate_log_embed(message, "event")
        embed.add_field(name="User", value=user)
        embed.add_field(name="Server", value=server_text)

        return message, embed

    @staticmethod
    def get_server_text(upper_object, guild=None):
        """Gets the embed text for a guild.

        parameters:
            upper_object (obj): the object to pull the guild from
            guild (discord.Guild): the guild to use instead of an upper object
        """
        guild = guild or getattr(upper_object, "guild", None)
        return f"{guild.name} ({guild.id})" if guild else "DM"

    @staticmethod
    def get_object_diff(before, after, attrs_to_check):
        """Finds differences in before, after object pairs.

        before (obj): the before object
        after (obj): the after object
        attrs_to_check (list): the attributes to compare
        """
        result = {}

        for attr in attrs_to_check:
            after_value = getattr(after, attr, None)
            if not after_value:
                continue

            before_value = getattr(before, attr, None)
            if not before_value:
                continue

            if before_value != after_value:
                result[attr] = munch.munchify(
                    {"before": before_value, "after": after_value}
                )

        return result

    @staticmethod
    def add_diff_fields(embed, diff):
        """Adds fields to an embed based on diff data.

        parameters:
            embed (discord.Embed): the embed object
            diff (dict): the diff data for an object
        """
        for attr, diff_data in diff.items():
            attru = attr.upper()
            if isinstance(diff_data.before, list):
                action = (
                    "added"
                    if len(diff_data.before) < len(diff_data.after)
                    else "removed"
                )
                list_diff = set(diff_data.after) ^ set(diff_data.before)

                embed.add_field(
                    name=f"{attru} {action}", value=",".join(str(o) for o in list_diff)
                )
                continue

            embed.add_field(name=f"{attru} (before)", value=diff_data.before)
            embed.add_field(name=f"{attru} (after)", value=diff_data.after)

        return embed

    async def log_from_queue(self):
        """Logs from the in-memory log queue.

        This provides an easier way of handling log throughput to Discord.
        """
        while True:
            try:
                await self.handle_queue_log()
            except Exception as exception:
                self.console.error(
                    f"Could not read from log queue: {exception}")
            await asyncio.sleep(self.queue_wait)

    async def handle_queue_log(self):
        """Handles a log from the queue.
        """
        log_data = await self.send_queue.get()
        if not log_data:
            return

        if log_data.level == "info":
            await self.handle_generic_log(
                log_data.message,
                "info",
                self.console.info,
                *log_data.args,
                **log_data.kwargs,
            )

        elif log_data.level == "debug":
            await self.handle_generic_log(
                log_data.message,
                "debug",
                self.console.debug,
                *log_data.args,
                **log_data.kwargs,
            )

        elif log_data.level == "warning":
            await self.handle_generic_log(
                log_data.message,
                "warning",
                self.console.warning,
                *log_data.args,
                **log_data.kwargs,
            )

        elif log_data.level == "event":
            event_type = log_data.kwargs.pop("event_type", None)
            if not event_type:
                raise AttributeError(
                    "Unable to get event_type from event log data"
                )

            await self.handle_event_log(
                event_type, *log_data.args, **log_data.kwargs
            )

        elif log_data.level == "error":
            await self.handle_error_log(
                log_data.message, *log_data.args, **log_data.kwargs
            )

        else:
            self.console.warning(
                f"Received unprocessable log level: {log_data.level}"
            )
