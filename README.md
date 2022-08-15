# BotLog

BotLog is a logging interface module for Discord bots. It allows bot developers to log to Discord channels along with the standard terminal console, providing an easy way to track events and errors.

```bash
pip install botlog
```

## Logging Levels

The logging interface is designed to simulate the standard Python logging levels: `debug`, `info`, `warning`, and `error`. 

### Debug / Info / Warning

The first three levels by default do *not* send to Discord. However, setting `send=True` provides this.

```py
from discord.ext import commands
import botlog

token = ""
bot = commands.Bot(token)
logger = botlog.BotLogger(bot=bot, name="mybot")
logging_channel = 818657960038250216

@bot.command(name="echo")
async def echo(ctx, *, input: str):
    await logger.info("Executing echo command", send=True, channel=logging_channel)
    await ctx.send(content=input)
```

### Error

For errors, the default is to send to Discord along with a traceback. Note, `critical=True` will add a mention to the message, so the guild owner will be notified directly.

```py
@bot.command(name="run")
async def run(ctx):
    try:
        await some_function()
    except Exception as e:
        await logger.error(
            "Could not execute some_function!", 
            exception=e, 
            context=context, 
            channel=logging_channel, 
            critical=True
        )

    await ctx.send(content=input)
```

## Console

If you just want to log to the standard logging console, you can still reference it with the bot logger. This is useful because it is not an async method and can be used in synchronous code.

```py
def setup_bot_config(bot, logger):
    logger.console.debug("Loading bot config")
    # ...
```
