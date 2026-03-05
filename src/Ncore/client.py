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

import sys
import inspect
import asyncio
import msgpack


from .router import Router
from .session import Session


class BaseClient:
    def info(self, txt):
        sys.stdout.write(f"\033[1;34m[ INFO ] [ {inspect.currentframe().f_back.f_code.co_name} ] {txt}\033[0m\n")

    def warn(self, txt):
        sys.stdout.write(f"\033[1;33m[ WARN ] [ {inspect.currentframe().f_back.f_code.co_name} ] {txt}\033[0m\n")

    def error(self, txt):
        sys.stdout.write(f"\033[1;31m[ ERROR ] [ {inspect.currentframe().f_back.f_code.co_name} ] {txt}\033[0m\n")

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        bot_token: str,
        loop: asyncio.AbstractEventLoop | None=None,
        storagename: str | None="storage",
        device_model: str="Ncore python",
        system_version: str="10.0",
        app_version: str="4.0",
        system_lang_code: str="ru",
        lang_pack: str="tdesktop",
        lang_code: str="ru"
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_token = bot_token
        self.storagename = storagename
        self.loop = loop
        self._init_config = {
            "device_model": device_model,
            "system_version": system_version,
            "app_version": app_version,
            "system_lang_code": system_lang_code,
            "lang_pack": lang_pack,
            "lang_code": lang_code,
        }

        self.storage = {
            "id": None,
            "first_name": None,
            "username": None,
            "dc_id": 2,
            "auth_key": None,
        }

        try:
            if self.storagename and self.storagename != ":memory:":
                self.storage = msgpack.load(open(self.storagename, "rb"))
                self.info(f"Сессия [{self.storagename}] загружена")
            else:
                self.info("Сессия [:memory:] загружена")
        except:
            self.save_storage()

    def save_storage(self):
        if not self.storagename:
            return
        try:
            msgpack.dump(self.storage, open(self.storagename, "wb"))
        except BaseException as ex:
            self.error(f"Ошибка сохранения сессии [{self.storagename}] -> {ex}")

    async def handle_updates(self, message):
        self.info(message)

        # TODO добавить pre_middleware

        await self.router.feed(message)

        # TODO добавить post_middleware

    async def idle(self):
        stop_event = asyncio.Event()
        await stop_event.wait()

    async def start(self, router: Router | None=None, handle_updates=None, proxy: str | None=None):
        self.loop = asyncio.get_running_loop()

        if handle_updates is not None:
            self.handle_updates = handle_updates

        if router is not None:
            router.finalize(self)
            self.router = router

        self.proxy = proxy

        self.session = Session(self)

        await self.session.start()
        await self.session.invoke({"_": "getState"})

    def run(self, router: Router | None=None, handle_updates=None, proxy: str | None=None):
        if self.loop is None:
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self.start(router=router, handle_updates=handle_updates, proxy=proxy))
            self.loop.run_forever()
        except KeyboardInterrupt:
            self.loop.run_until_complete(self.session.stop(r=0))
            self.info("Бот остановлен пользователем (Ctrl+C)")