from inspect import cleandoc
import uuid
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import config
from bot.database import MongoDB
from bot.utilities.helpers import DataEncoder, RateLimiter
from bot.utilities.pyrofilters import ConvoMessage, PyroFilters
from bot.utilities.pyrotools import HelpCmd

database = MongoDB()

def calculate_message_range(start_msg_id: int, total_files: int, exclude_ids: set) -> list[int]:
    """Calculate the range of message IDs based on the start message ID and total files, excluding specified IDs."""
    return [msg_id for msg_id in range(start_msg_id, start_msg_id + total_files) if msg_id not in exclude_ids]

@Client.on_message(
    filters.private & PyroFilters.admin() & filters.command("batch_plus")
)
@RateLimiter.hybrid_limiter(func_count=1)
async def batch_plus(client: Client, message: ConvoMessage) -> Message | None:
    """>**Fetch a batch of files directly from backup channel starting from a specific message and create a sharable link.**

    **Usage:**
        /batch_plus [start link] [total files] [(optional) exclude id]

        /batch_plus https://t.me/c/-100/9 10

        /batch_plus https://t.me/c/-100/9 10 69 70 80 90

    >This fetches 10 files starting from file ID 9 and excludes 69, 79, 80, and 90.
    """
    
    if len(message.command) < 3:
        return await message.reply(cleandoc(batch_plus.__doc__ or ""))

    # Extract the start link and total files from the command
    start_file_link = message.command[1].split("/")
    total_files = int(message.command[2])
    
    if start_file_link[-2] != str(config.BACKUP_CHANNEL).removeprefix("-100"):
        return await message.reply(text="Only send a file link from your current database channel", quote=True)

    # Parse exclude file IDs if provided
    exclude_file_ids = set(map(int, message.command[3:])) if len(message.command) > 3 else set()

    # Calculate the range of file IDs to fetch
    start_file_id = int(start_file_link[-1])
    file_ids_range = calculate_message_range(start_msg_id=start_file_id, total_files=total_files, exclude_ids=exclude_file_ids)

    # Fetch the files from the backup channel
    fetch_files = await client.get_messages(chat_id=config.BACKUP_CHANNEL, message_ids=file_ids_range)
    fetch_files = [fetch_files] if not isinstance(fetch_files, list) else fetch_files

    files_to_store = []
    for file in fetch_files:
        file_type = file.document or file.video or file.photo or file.audio or file.sticker

        if not file_type or file.empty:
            continue

        files_to_store.append(
            {
                "caption": file.caption.markdown if file.caption else None,
                "file_id": file_type.file_id,
                "message_id": file.id,
            }
        )

    if not files_to_store:
        return await message.reply(text="Couldn't fetch any files from the specified range.", quote=True)

    # Generate a unique link using UUID
    unique_link = f"{uuid.uuid4().int}"
    file_link = DataEncoder.encode_data(unique_link)
    file_origin = config.BACKUP_CHANNEL

    # Store the files in the database
    add_file = await database.add_file(file_link=file_link, file_origin=file_origin, file_data=files_to_store)

    if add_file:
        link = f"https://telegram.me/{client.me.username}?start={file_link}"  # type: ignore[reportOptionalMemberAccess]
        reply_markup = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Share URL", url=f"https://t.me/share/url?url={link}"), 
                 InlineKeyboardButton("Get File", url=f"{link}")]
            ],
        )

        return await message.reply(
            text=f"Here is your link:\n>`{link}`</code>",
            quote=True,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )

    return await message.reply(text="Couldn't add files to database", quote=True)


HelpCmd.set_help(
    command="batch_plus",
    description=batch_plus.__doc__,
    allow_global=False,
    allow_non_admin=False,
)
