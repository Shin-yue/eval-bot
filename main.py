import html
import logging
import io
import os
import traceback
import uuid

from typing import (
    Any,
    Dict,
    List,
    Optional,
    Tuple,
    cast
)

import meval
from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    Application,
    ContextTypes,
    CommandHandler,
    Defaults
)

TOKEN = os.getenv("TOKEN")

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s.%(funcName)s | %(levelname)s | %(message)s",
    datefmt="%m/%d %H:%M:%S",
)

logging.getLogger("httpx").setLevel(logging.WARNING)


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await cast(Message, update.message).reply_text(
        f"Hi {user.mention_html()}!\n"
        "Welcome, This bot is designed to help you run Python code efficiently.\n\n"
        "To get started, use the /run command followed by the "
        "Python code you want to execute. Make sure your code "
        "is complete so it can run properly.\n\n"
        "📦 <b>Source Code:</b> https://github.com/shin-yue/eval-bot"
    )


async def handle_eval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    The main function to handle the evaluation of Python code sent via command.
    
    Args:
        update: The Telegram update.
        context: The callback context as provided by the application.

    Returns:
        str: The result of the evaluated code or error message if evaluation fails.
    """
    message = cast(Message, update.effective_message)
    
    if len(context.args) < 1:
        await message.reply_text(
            "To execute Python code, please include "
            "the code you wish to run. Use the command /run followed by your code."
        )
        return
        
    command = message.text.split(None, 1)[1]
    
    sent_message = await message.reply_text("<i>Executing your code...</i>")

    output_buffer = io.StringIO()    
    def print_output(*args: Any, **kwargs: Any) -> None:
        if "file" not in kwargs:
            kwargs["file"] = output_buffer
        print(*args, **kwargs)

    environment = {
        "message": message,
        "m": message,
        "print": print_output,
        "r": message.reply_to_message if message.reply_to_message else None,
        "bot": context.application.bot,
        "user": update.effective_user
    }

    prefix, execution_result = await execute_code(command, environment)

    if execution_result is not None:
        print(execution_result, file=output_buffer)
    output_text = output_buffer.getvalue().rstrip()  # Remove trailing newline if present

    await handle_response(sent_message, message, prefix, command, output_text)


async def execute_code(command_args: str, execution_environment: dict) -> Tuple[str, Optional[str]]:
    """Executes the given Python code asynchronously."""
    try:
        return "", await meval.meval(command_args, globals(), **execution_environment)
    except Exception as exception:
        formatted_traceback = format_exception_with_traceback(exception)
        return "<b>Error while executing snippet:</b>\n\n", formatted_traceback
    

async def handle_response(
    sent_message: Message, message: Message, prefix: str, command_args: str, output: str
) -> None:
    """Handles the response after evaluating the Python code."""
    if len(str(output)) > 4096:
        with io.BytesIO(str.encode(str(output))) as file:
            file.name = str(uuid.uuid4()).split("-")[0].upper() + ".TXT"
            caption = "Output is too large to be sent as a text message."
            await sent_message.delete()
            await message.reply_document(file, caption=caption)
            return

    result = f"{prefix}<b>Input:</b>\n"
    result += f"<pre><code class='language-python'>{html.escape(command_args)}</code></pre>\n"
    result += f"<b>Output:</b>\n"
    result += f"<pre><code class='language-python'>{html.escape(output)}</code></pre>\n"
    await sent_message.edit_text(text=result)


def create_traceback_message(error: BaseException, frames: Optional[List[traceback.FrameSummary]] = None) -> str:
    """Generate a formatted error message with traceback information."""    
    if frames is None:
        frames = traceback.extract_tb(error.__traceback__)
    
    base_directory = os.getcwd()    
    for frame in frames:
        if base_directory in frame.filename:
            frame.filename = os.path.relpath(frame.filename, base_directory)
    
    traceback_details = "".join(traceback.format_list(frames))
    error_details = str(error)    
    if error_details:
        error_details = ": " + error_details
    
    return f"Traceback (most recent call last):\n{traceback_details}{type(error).__name__}{error_details}"


def format_exception_with_traceback(excp: Exception) -> str:
    """Formats the exception traceback for better readability."""
    tb = traceback.extract_tb(excp.__traceback__)
    first_snip_idx = next(
        (i for i, frame in enumerate(tb) if frame.filename == "<string>" or frame.filename.endswith("ast.py")), -1
    )
    stripped_tb = tb[first_snip_idx:]
    return create_traceback_message(error=excp, frames=stripped_tb)


def main() -> None:
    application = ApplicationBuilder().token(TOKEN).defaults(Defaults(parse_mode=ParseMode.HTML)).build()
    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("run", handle_eval))
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
