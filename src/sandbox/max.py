from pathlib import Path
import asyncio
from pymax import Chat, ExtraConfig, Message, SyncOverrides, WebClient


class SandboxMax:
    """Interactive sandbox client for selecting and observing a chat."""

    chat_id_file = Path("selected_chat_id.txt")

    def __init__(self) -> None:
        self.client = WebClient(
            work_dir="sessions",
            session_name="max_sandbox_web.db",
            extra_config=ExtraConfig(sync=SyncOverrides(chats_sync=-1)),
        )
        self.client.on_start()(self.on_start)
        self.client.on_message()(self.on_message)

    async def on_start(self, client: WebClient) -> None:
        print("Web-client started")
        await self.choose_chat(client)

    @staticmethod
    def chat_info(chat: Chat) -> str:
        """Return the chat details shown in the selection prompt."""
        title = chat.title or "Untitled chat"
        return (
            f"{title!r}, messages={chat.messages_count}, "
            f"participants={chat.participants_count}"
        )

    async def choose_chat(self, client: WebClient) -> Chat | None:
        """Prompt for a chat and save its CID for later use."""
        chats = [chat for chat in (client.chats or []) if chat.type == "CHAT"]
        if not chats:
            print("No chats available.")
            return None

        print("\nChoose a chat:")
        for index, chat in enumerate(chats, start=1):
            print(f"{index}. {self.chat_info(chat)}")

        while True:
            selection = await asyncio.to_thread(input, "Chat number (or q to quit): ")
            if selection.strip().lower() == "q":
                return None
            try:
                index = int(selection) - 1
            except ValueError:
                print("Enter a chat number or q.")
                continue
            if 0 <= index < len(chats):
                chat = chats[index]
                if chat.cid is None:
                    print("The selected chat has no CID and cannot be saved.")
                    return None
                self.chat_id_file.write_text(f"{chat.cid}\n", encoding="utf-8")
                print(f"Saved CID {chat.cid} to {self.chat_id_file}.")
                return chat
            print(f"Choose a number from 1 to {len(chats)}.")

    async def on_message(self, message: Message, client: WebClient) -> None:
        print(message.chat_id, message.sender, message.text)

    async def run(self) -> None:
        await self.client.start()
