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


ADMINID = 777

client = Client(api_id=..., api_hash="...", bot_token="...")
router = Router(["/", "."])


async def is_admin(event):
    return event["users"][0]["id"] == ADMINID


@router.add("admin", EventType.NewMessage | EventType.EditMessage, is_admin)
async def handle_admin(event: UpdateNewMessage):
    """хендлер для команды /admin
    с типо обновления новое/редактированое сообщение
    с вызовом кастомной функции-фильтра
    """
    await event.answer("da")


@router.add("ban <!target: int> <reason: str>", EventType.NewMessage, is_admin)
async def handle_ban(event: UpdateNewMessage, target: int, reason: str | None):
    """хендлер для команды /ban
    с обязательным аргументом target (без которого не исполнится хендлер)
    и не обязательным аргументом reason, который при отсутсвии заменяется на None.
        при этом если тип reason будет int, а админ укажет "spamer", хендлер тоже не сработает
    с типо обновления новое сообщение
    с вызовом кастомной функции-фильтра
    """

    if reason is None:
        normal_reason = "без причны"
    else:
        normal_reason = reason

    print(f"баним {target} по причине {normal_reason}")


@router.add(EventType.EditMessage)
async def handle_editmessage(event: UpdateNewMessage):
    """хендлер по уже добавленным типам обновлений"""
    print(f"handle_editmessage {event.update}")


@router.add({"updateDeleteMessages"})
async def handle_custom_update_type(event: RawUpdate):
    """хендлер для ещё не добавленных типов обновлений, на случай если Ncore не успел обновиться под обновление Telegram"""
    print(f"handle_custom_update_type {event}")


client.run(router=router, proxy="socks5://127.0.0.1:1089")

```

## Лицензия

Проект распространяется под лицензией **Apache License, Version 2.0**. Подробности см. в файле [LICENSE](LICENSE).

В проекте используются следующие сторонние библиотеки:

* **msgpack** (Apache 2.0)
* **tgcrypto** (LGPLv3 — динамическое связывание)

**Сборка:**
Для компиляции модуля `tl` используется **Cython** (Apache 2.0).
