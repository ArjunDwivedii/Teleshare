from inspect import cleandoc
from pyrogram import filters
from pyrogram.client import Client
from pyrogram.types import Message
from bot.config import config
from bot.database import MongoDB
from bot.utilities.helpers import DataEncoder, RateLimiter
from bot.utilities.pyrofilters import ConvoMessage, PyroFilters
from bot.utilities.pyrotools import HelpCmd
import uuid

database = MongoDB()

@Client.on_message(
    filters.private & PyroFilters.admin() & (filters.command("batch_pro") | filters.command("batch_files") | filters.command("batch"))
)
@RateLimiter.hybrid_limiter(func_count=1)
async def batch_pro(client: Client, message: ConvoMessage) -> Message | None:
    """>**Fetch files directly from backup channel to create sharable links of ranged file IDs.**

    **Usage:**
        /batch_pro [start link] [end link] [files per batch] [total files]

        /batch_pro https://t.me/c/-100/9 https://t.me/c/-100/100 10 50

    >This fetches files from the database starting with file ID 9 to 100, creating links in batches.
    """

    if len(message.command) < 5:
        return await message.reply(cleandoc(batch_pro.__doc__ or ""))

    start_file_link = message.command[1].split("/")
    end_file_link = message.command[2].split("/")

    if start_file_link[-2] != str(config.BACKUP_CHANNEL).removeprefix("-100") or end_file_link[-2] != str(config.BACKUP_CHANNEL).removeprefix("-100"):
        return await message.reply(text="Only send file links from your current database channel", quote=True)

    files_per_batch = int(message.command[3])
    total_files = int(message.command[4])

    exclude_file_ids = set(map(int, message.command[5:])) if len(message.command) > 5 else set()

    file_ids_range = [
        num for num in range(int(start_file_link[-1]), int(end_file_link[-1]) + 1) if num not in exclude_file_ids
    ]

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
            },
        )

    if not files_to_store:
        return await message.reply(text="Couldn't fetch any files from the given range.", quote=True)

    # Calculate number of batches
    total_batches = (len(files_to_store) + files_per_batch - 1) // files_per_batch

    links = []
    progress_message = await message.reply(text="📦 Batching in progress, please wait...")

    for batch in range(total_batches):
        batch_files = files_to_store[batch * files_per_batch:(batch + 1) * files_per_batch]

        # Generate a unique link using UUID
        unique_link = f"{uuid.uuid4().int}"
        file_link = DataEncoder.encode_data(unique_link)
        file_origin = config.BACKUP_CHANNEL

        # Store each batch in the database
        await database.add_file(file_link=file_link, file_origin=file_origin, file_data=batch_files)

        link = f"https://telegram.me/{client.me.username}?start={file_link}" # type: ignore
        links.append(f"Batch {batch + 1}/{total_batches}:\n`{link}`\n")  # Adjust format here

    # Edit the progress message after processing is complete
    await progress_message.edit(text="Batch processing complete.")

    # Send links to user in groups of 10
    for i in range(0, len(links), 10):
        link_group = "\n".join(links[i:i + 10])
        await message.reply(
            text=link_group,
            quote=True,
            disable_web_page_preview=True,
        )

    return  # No deletion of the batching message, allowing it to remain visible

HelpCmd.set_help(
    command="batch_pro",
    description=batch_pro.__doc__,
    allow_global=False,
    allow_non_admin=False,
)
