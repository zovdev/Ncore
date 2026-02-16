# Copyright 2026 zovdev
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from Ncore.types import InputPeerUser, InputPeerChannel, InputPeerChat


class EventType:
    """Типы событий для обработчиков
    @router.add("command", EventType.NewMessage | EventType.EditMessage)
    """

    NewMessage = {"updateNewMessage", "updateNewChannelMessage"}
    EditMessage = {"updateEditMessage", "updateEditChannelMessage"}


class RawUpdate:
    """RawUpdate для не определённых типов.
    Доступ к обновлению RawUpdate.update
    Полное событие RawUpdate.raw_update
    Доступ к экземпляру клиента RawUpdate.client"""

    __slots__ = ("client", "update", "raw_update")

    def __init__(self, client, update, raw_update):
        self.client = client
        self.update = update
        self.raw_update = raw_update


class UpdateNewMessage:
    __slots__ = ("client", "update", "raw_update")

    def __init__(self, client, update, raw_update):
        self.client = client
        self.update = update
        self.raw_update = raw_update

    @property
    def peer_id(self):
        return self.update["message"]["peer_id"]

    async def answer(self, message: str, **kwargs) -> dict:
        cid = self.update["message"]["peer_id"]
        if cid["_"] == "peerUser":
            for t in self.raw_update["users"]:
                if t["id"] == cid["user_id"]:
                    break
            else:
                raise self.client.error("Юзер для ответа не найден")
            cid = InputPeerUser(t["id"], t["access_hash"])
        elif cid["_"] == "peerChannel":
            for t in self.raw_update["chats"]:
                if t["id"] == cid["channel_id"]:
                    break
            else:
                raise self.client.error("Чат для ответа не найден")
            cid = InputPeerChannel(t["id"], t["access_hash"])
        elif cid["_"] == "peerChat":
            cid = InputPeerChat(cid["chat_id"])

        return await self.client.send_message(
            message=message,
            peer=cid,
            random_id=self.update["message"]["id"] + self.raw_update["date"],
            **kwargs
        )


EVENT_ROUTER = {
    "updateNewMessage": UpdateNewMessage,
    "updateNewChannelMessage": UpdateNewMessage,
    "updateShortMessage": UpdateNewMessage,
    "updateShortChatMessage": UpdateNewMessage,
    "updateEditMessage": UpdateNewMessage,
    "updateEditChannelMessage": UpdateNewMessage
}


def build_event(client, update, raw_update):
    event_class = EVENT_ROUTER.get(update["_"], RawUpdate)

    return event_class(client, update, raw_update)