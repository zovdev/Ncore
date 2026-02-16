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

class InputPeerEmpty:
    def __new__(cls) -> dict:
        return {"_": "inputPeerEmpty"}


class InputPeerSelf:
    def __new__(cls) -> dict:
        return {"_": "inputPeerSelf"}


class InputPeerChat:
    def __new__(cls, chat_id: int) -> dict:
        return {"_": "inputPeerChat", "chat_id": chat_id}


class InputPeerUser:
    def __new__(cls, user_id: int, access_hash: int) -> dict:
        return {"_": "inputPeerUser", "user_id": user_id, "access_hash": access_hash}


class InputPeerChannel:
    def __new__(cls, channel_id: int, access_hash: int) -> dict:
        return {"_": "inputPeerChannel", "channel_id": channel_id, "access_hash": access_hash}