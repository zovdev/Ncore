# Ncore

[![PyPI version](https://badge.fury.io/py/Ncore.svg)](https://badge.fury.io/py/Ncore)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)


Высокопроизводительная, асинхронная библиотека для работы с протоколом MTProto (Telegram API) на python, написанная с нуля с фокусом на скорость и низкое потребление памяти.

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


client = Client(api_id=1234, api_hash="...", bot_token="...")


async def custom_handle_updates(message):
    client.info(f"Новое событие - {message}")

    if message["_"] != "updates":
        return

    if message["updates"][0]["_"] != "updateNewMessage":
        return

    msg = message["updates"][0]["message"]
    if msg["out"]:
        return

    await client.session.invoke({
        "_": "messages.sendMessage",
        "peer" : {
            "_": "inputPeerUser",
            "user_id": message["users"][0]["id"],
            "access_hash": message["users"][0]["access_hash"]
        },
        "message": "Ncore echo v2",
        "random_id": msg["id"]+1
    })


client.loop.run_until_complete(client.start(handle_updates=custom_handle_updates))

client.loop.run_forever()

```

## Лицензия

Проект распространяется под лицензией **Apache License, Version 2.0**. Подробности см. в файле [LICENSE](LICENSE).

В проекте используются следующие сторонние библиотеки:

* **msgpack** (Apache 2.0)
* **tgcrypto** (LGPLv3 — динамическое связывание)

**Сборка:**

Для компиляции модуля `tl` используется **Cython** (Apache 2.0).
