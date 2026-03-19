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

from random import getrandbits

from .base import RawUpdate
from ..entity import build_entity, AnyMessageEntity
from ..input_peer import InputPeerUser, InputPeerChannel, InputPeerChat


class UpdateNewMessage(RawUpdate):
    __slots__ = ("client", "update", "raw_update")

    @property
    def id(self) -> int:
        """ID сообщения"""
        return self.update["message"]["id"]

    @property
    def peer_id(self) -> dict:
        """ID чата"""
        return self.update["message"]["peer_id"]

    @property
    def from_id(self) -> dict | None:
        """Отправитель сообщения"""
        return self.update["message"]["from_id"]

    @property
    def date(self) -> int:
        """Время отправки"""
        return self.update["message"]["date"]

    @property
    def edit_date(self) -> int | None:
        """Время редактирования"""
        return self.update["message"]["edit_date"]

    @property
    def is_out(self) -> bool:
        """Исходящее ли сообщение"""
        return self.update["message"]["out"]

    @property
    def mentioned(self) -> bool:
        """Упомянули ли нас"""
        return self.update["message"]["mentioned"]

    @property
    def media_unread(self) -> bool:
        """Непрочитанное медиа"""
        return self.update["message"]["media_unread"]

    @property
    def silent(self) -> bool:
        """Без звука"""
        return self.update["message"]["silent"]

    @property
    def post(self) -> bool:
        """Пост в канале"""
        return self.update["message"]["post"]

    @property
    def from_scheduled(self) -> bool:
        """Из отложенных"""
        return self.update["message"]["from_scheduled"]

    @property
    def legacy(self) -> bool:
        """Устаревший формат"""
        return self.update["message"]["legacy"]

    @property
    def edit_hide(self) -> bool:
        """Скрыта ли метка изменения"""
        return self.update["message"]["edit_hide"]

    @property
    def pinned(self) -> bool:
        """Закреплено"""
        return self.update["message"]["pinned"]

    @property
    def noforwards(self) -> bool:
        """Запрет пересылки"""
        return self.update["message"]["noforwards"]

    @property
    def invert_media(self) -> bool:
        """Медиа над текстом"""
        return self.update["message"]["invert_media"]

    @property
    def offline(self) -> bool:
        """Отправлено в офлайне"""
        return self.update["message"]["offline"]

    @property
    def text(self) -> str:
        """Текст или подпись к медиа"""
        return self.update["message"]["message"]

    @property
    def media(self) -> dict | None:
        """Прикрепленное медиа"""
        return self.update["message"]["media"]

    @property
    def entities(self) -> list[AnyMessageEntity] | None:
        """Форматирование текста"""
        ents = self.update["message"]["entities"]
        if ents is None:
            return None
        msg = self.update["message"]["message"]
        return [build_entity(e, msg) for e in ents]

    @property
    def reply_markup(self) -> dict | None:
        """Клавиатура"""
        return self.update["message"]["reply_markup"]

    @property
    def fwd_from(self) -> dict | None:
        """Информация о пересылке"""
        return self.update["message"]["fwd_from"]

    @property
    def reply_to(self) -> dict | None:
        """На какое сообщение ответ"""
        return self.update["message"]["reply_to"]

    @property
    def views(self) -> int | None:
        """Количество просмотров"""
        return self.update["message"]["views"]

    @property
    def forwards(self) -> int | None:
        """Количество пересылок"""
        return self.update["message"]["forwards"]

    @property
    def replies(self) -> dict | None:
        """Комментарии/Ответы к сообщению"""
        return self.update["message"]["replies"]

    @property
    def post_author(self) -> str | None:
        """Подпись автора поста"""
        return self.update["message"]["post_author"]

    @property
    def grouped_id(self) -> int | None:
        """ID альбома"""
        return self.update["message"]["grouped_id"]

    @property
    def reactions(self) -> dict | None:
        """Реакции"""
        return self.update["message"]["reactions"]

    @property
    def restriction_reason(self) -> list[dict] | None:
        """Причины ограничения"""
        return self.update["message"]["restriction_reason"]

    @property
    def ttl_period(self) -> int | None:
        """Время автоудаления"""
        return self.update["message"]["ttl_period"]

    @property
    def effect(self) -> dict | None:
        """Анимированный эффект"""
        return self.update["message"]["effect"]

    @property
    def factcheck(self) -> dict | None:
        """Проверка фактов"""
        return self.update["message"]["factcheck"]

    async def answer(self, message: str, **kwargs) -> dict:
        """Ответить на сообщение"""
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

        if "reply_to" not in kwargs and self.update["message"]["reply_to"] and self.update["message"]["reply_to"]["forum_topic"]:
            if self.update["message"]["reply_to"]["reply_to_top_id"]:
                kwargs["reply_to"] = {
                    "_": "inputReplyToMessage",
                    "reply_to_msg_id": self.update["message"]["reply_to"]["reply_to_top_id"]
                }
            elif self.update["message"]["reply_to"]["reply_to_msg_id"]:
                kwargs["reply_to"] = {
                    "_": "inputReplyToMessage",
                    "reply_to_msg_id": self.update["message"]["reply_to"]["reply_to_msg_id"]
                }

        return await self.client.send_message(
            message=message,
            peer=cid,
            random_id=getrandbits(60),
            **kwargs
        )
