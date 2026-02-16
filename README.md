# Ncore

[![PyPI version](https://badge.fury.io/py/Ncore.svg)](https://badge.fury.io/py/Ncore)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)


Высокопроизводительная, асинхронная библиотека для работы с протоколом MTProto (Telegram API), написанная с нуля с фокусом на скорость и низкое потребление памяти.

## Особенности

- **Высокая производительность:** Оптимизированный сетевой код и работа с памятью.
- **Современный `asyncio`:** Полностью асинхронная архитектура.
- **Минимальные зависимости:** Только самое необходимое для работы.
- **Простая лицензия:** Apache 2.0, подходит для любых проектов.

## Установка

```bash
pip install Ncore
```

## Быстрый старт

```python
from Ncore import Client
from Ncore.router import Router
from Ncore.types import EventType, UpdateNewMessage, RawUpdate


ADMINID = 772947818

client = Client(api_id=..., api_hash="...", bot_token="...")
router = Router(["/", "."])


async def is_admin(event):
    return event["users"][0]["id"] == ADMINID


@router.add("admin", EventType.NewMessage | EventType.EditMessage, is_admin)
async def handle_getuser(event: UpdateNewMessage):
    await event.answer("da")


@router.add({"msgsAck"})
async def handle_ack(event: RawUpdate):
    print(f"handle_ack {event}")


@router.add({"updateDeleteMessages"})
async def handle_update_delete_messages(event: RawUpdate):
    print(f"handle_update_delete_messages {event}")


client.loop.run_until_complete(client.start(router=router))
client.loop.run_forever()

```

## Лицензия

Проект распространяется под лицензией **Apache License, Version 2.0**. Подробности см. в файле [LICENSE](LICENSE).

В проекте используются следующие сторонние библиотеки:

* **msgpack** (Apache 2.0)
* **tgcrypto** (LGPLv3 — динамическое связывание)

**Сборка:**
Для компиляции модуля `tl` используется **Cython** (Apache 2.0).