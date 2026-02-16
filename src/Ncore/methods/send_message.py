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

import Ncore

from Ncore import types


class SendMessage:
    @overload
    async def send_message(
        self,
        message: str,
        peer: types.InputPeer,
        random_id: int,
        entities: list[types.MessageEntity] | None = None,
        reply_to: types.InputReplyTo | None = None,
        reply_markup: types.ReplyMarkup | None = None,
        no_webpage: bool = False,
        silent: bool = False,
        background: bool = False,
        clear_draft: bool = False,
        noforwards: bool = False,
        update_stickersets_order: bool = False,
        invert_media: bool = False,
        allow_paid_floodskip: bool = False,
        schedule_date: int | None = None,
        send_as: types.InputPeer | None = None,
        quick_reply_shortcut: types.InputQuickReplyShortcut | None = None,
        effect: int | None = None,
        allow_paid_stars: int | None = None,
        suggested_post: types.SuggestedPost | None = None,
    ) -> dict:
        ...

    async def send_message(self, message, peer, random_id, **params):
        params["_"] = "messages.sendMessage"
        params["message"] = message
        params["peer"] = peer
        params["random_id"] = random_id
        return await self.session.invoke(params)
