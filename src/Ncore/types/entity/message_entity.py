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

from typing import overload


class MessageEntity(dict):
    _: str
    __slots__ = ("_message")

    @overload
    def __init__(self, offset: int, length: int):
        ...

    def __init__(self, offset: int, length: int, _="", _message="", **kwargs):
        self._message = _message
        dict.__init__(self, _=self._ or _, offset=offset, length=length, **kwargs)

    @property
    def offset(self) -> int:
        return self["offset"]

    @property
    def length(self) -> int:
        return self["length"]

    @property
    def value(self) -> str | None:
        return self._message[self["offset"] : self["offset"]+self["length"]] if self._message else None


class MessageEntityUnknown(MessageEntity):
    _ = "messageEntityUnknown"
    __slots__ = ("_message")


class MessageEntityMention(MessageEntity):
    _ = "messageEntityMention"
    __slots__ = ("_message")


class MessageEntityHashtag(MessageEntity):
    _ = "messageEntityHashtag"
    __slots__ = ("_message")


class MessageEntityBotCommand(MessageEntity):
    _ = "messageEntityBotCommand"
    __slots__ = ("_message")


class MessageEntityUrl(MessageEntity):
    _ = "messageEntityUrl"
    __slots__ = ("_message")


class MessageEntityEmail(MessageEntity):
    _ = "messageEntityEmail"
    __slots__ = ("_message")


class MessageEntityBold(MessageEntity):
    _ = "messageEntityBold"
    __slots__ = ("_message")


class MessageEntityItalic(MessageEntity):
    _ = "messageEntityItalic"
    __slots__ = ("_message")


class MessageEntityCode(MessageEntity):
    _ = "messageEntityCode"
    __slots__ = ("_message")


class MessageEntityPhone(MessageEntity):
    _ = "messageEntityPhone"
    __slots__ = ("_message")


class MessageEntityCashtag(MessageEntity):
    _ = "messageEntityCashtag"
    __slots__ = ("_message")


class MessageEntityUnderline(MessageEntity):
    _ = "messageEntityUnderline"
    __slots__ = ("_message")


class MessageEntityStrike(MessageEntity):
    _ = "messageEntityStrike"
    __slots__ = ("_message")


class MessageEntityBankCard(MessageEntity):
    _ = "messageEntityBankCard"
    __slots__ = ("_message")


class MessageEntitySpoiler(MessageEntity):
    _ = "messageEntitySpoiler"
    __slots__ = ("_message")


class MessageEntityPre(MessageEntity):
    _ = "messageEntityPre"
    __slots__ = ("_message")

    @overload
    def __init__(self, offset: int, length: int, language: str):
        ...

    def __init__(self, offset, length, language, **kwargs):
        super().__init__(offset, length, language=language, **kwargs)

    @property
    def language(self) -> str:
        return self["language"]


class MessageEntityTextUrl(MessageEntity):
    _ = "messageEntityTextUrl"
    __slots__ = ("_message")

    @overload
    def __init__(self, offset: int, length: int, url: str):
        ...

    def __init__(self, offset, length, url, **kwargs):
        super().__init__(offset, length, url=url, **kwargs)

    @property
    def url(self) -> str:
        return self["url"]


class MessageEntityMentionName(MessageEntity):
    _ = "messageEntityMentionName"
    __slots__ = ("_message")

    @overload
    def __init__(self, offset: int, length: int, user_id: int):
        ...

    def __init__(self, offset, length, user_id, **kwargs):
        super().__init__(offset, length, user_id=user_id, **kwargs)

    @property
    def user_id(self) -> int:
        return self["user_id"]


class MessageEntityCustomEmoji(MessageEntity):
    _ = "messageEntityCustomEmoji"
    __slots__ = ("_message")

    @overload
    def __init__(self, offset: int, length: int, document_id: int):
        ...

    def __init__(self, offset, length, document_id, **kwargs):
        super().__init__(offset, length, document_id=document_id, **kwargs)

    @property
    def document_id(self) -> int:
        return self["document_id"]


class MessageEntityBlockquote(MessageEntity):
    _ = "messageEntityBlockquote"
    __slots__ = ("_message")

    @overload
    def __init__(self, offset: int, length: int, collapsed: bool):
        ...

    def __init__(self, offset, length, collapsed, **kwargs):
        super().__init__(offset, length, collapsed=collapsed, **kwargs)

    @property
    def collapsed(self) -> bool:
        return self["collapsed"]


AnyMessageEntity = (
    MessageEntityUnknown |
    MessageEntityMention | MessageEntityMentionName |
    MessageEntityHashtag | MessageEntityCashtag | MessageEntityBotCommand | MessageEntityCustomEmoji |
    MessageEntityUrl | MessageEntityTextUrl |
    MessageEntityEmail | MessageEntityPhone | MessageEntityBankCard |
    MessageEntityBold | MessageEntityItalic | MessageEntityUnderline | MessageEntityStrike | MessageEntitySpoiler | MessageEntityBlockquote |
    MessageEntityCode | MessageEntityPre
)
