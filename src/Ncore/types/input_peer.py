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

class InputPeer(dict):
    __slots__ = ()


class InputPeerEmpty(InputPeer):
    __slots__ = ()

    def __init__(self):
        dict.__init__(self, _="inputPeerEmpty")


class InputPeerSelf(InputPeer):
    __slots__ = ()

    def __init__(self):
        dict.__init__(self, _="inputPeerSelf")


class InputPeerChat(InputPeer):
    __slots__ = ()

    def __init__(self, chat_id: int):
        dict.__init__(self, _="inputPeerChat", chat_id=chat_id)


class InputPeerUser(InputPeer):
    __slots__ = ()

    def __init__(self, user_id: int, access_hash: int):
        dict.__init__(self, _="inputPeerUser", user_id=user_id, access_hash=access_hash)


class InputPeerChannel(InputPeer):
    __slots__ = ()

    def __init__(self, channel_id: int, access_hash: int):
        dict.__init__(self, _="inputPeerChannel", channel_id=channel_id, access_hash=access_hash)
