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

from .enums import EventType
from .events import build_event, RawUpdate, UpdateNewMessage
from .input_peer import InputPeer, InputPeerEmpty, InputPeerSelf, InputPeerChat, InputPeerUser, InputPeerChannel
from .entity import (
    build_entity, AnyMessageEntity, MessageEntity, MessageEntityUnknown,
    MessageEntityMention, MessageEntityMentionName,
    MessageEntityHashtag, MessageEntityCashtag, MessageEntityBotCommand, MessageEntityCustomEmoji,
    MessageEntityUrl, MessageEntityTextUrl,
    MessageEntityEmail, MessageEntityPhone, MessageEntityBankCard,
    MessageEntityBold, MessageEntityItalic, MessageEntityUnderline, MessageEntityStrike, MessageEntitySpoiler, MessageEntityBlockquote,
    MessageEntityCode, MessageEntityPre
)


class InputReplyTo: ...
class ReplyMarkup: ...
class InputQuickReplyShortcut: ...
class SuggestedPost: ...
