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

from .message_entity import *


ENTITY_ROUTER = {
    "messageEntityUnknown": MessageEntityUnknown,
    "messageEntityMention": MessageEntityMention,
    "messageEntityMentionName": MessageEntityMentionName,
    "messageEntityHashtag": MessageEntityHashtag,
    "messageEntityCashtag": MessageEntityCashtag,
    "messageEntityBotCommand": MessageEntityBotCommand,
    "messageEntityCustomEmoji": MessageEntityCustomEmoji,
    "messageEntityUrl": MessageEntityUrl,
    "messageEntityTextUrl": MessageEntityTextUrl,
    "messageEntityEmail": MessageEntityEmail,
    "messageEntityPhone": MessageEntityPhone,
    "messageEntityBankCard": MessageEntityBankCard,
    "messageEntityBold": MessageEntityBold,
    "messageEntityItalic": MessageEntityItalic,
    "messageEntityUnderline": MessageEntityUnderline,
    "messageEntityStrike": MessageEntityStrike,
    "messageEntitySpoiler": MessageEntitySpoiler,
    "messageEntityBlockquote": MessageEntityBlockquote,
    "messageEntityCode": MessageEntityCode,
    "messageEntityPre": MessageEntityPre
}


def build_entity(entity, message=""):
    entity_class = ENTITY_ROUTER.get(entity["_"], MessageEntityUnknown)
    entity["_message"] = message
    return entity_class(**entity)
