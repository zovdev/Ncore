# Документация API Ncore

Фреймворк Ncore предоставляет интуитивно понятный, но в то же время мощный API для создания Telegram ботов. Вся сложность криптографии и TL-парсинга скрыта под капотом, предоставляя разработчику чистый интерфейс.

## ⚙️ Инициализация клиента

Основной класс взаимодействия — `Client` (наследует `BaseClient` и методы API).

```python
from Ncore import Client

client = Client(
    api_id=12345,                  # Ваш API ID
    api_hash="hash",               # Ваш API Hash
    bot_token="token",             # Токен бота
    storagename="session.ncore",   # Файл сессии (msgpack). Используйте ":memory:" для ОЗУ
    device_model="Ncore Server",   # Кастомная модель устройства
    system_version="Ubuntu 22.04", # Версия ОС
    app_version="1.0.0"            # Версия вашего приложения
)
```

### Нативная работа с Proxy
Ncore поддерживает прямое подключение через прокси без сторонних тяжелых библиотек. Вы можете передать строку подключения в метод `run` или `start`. Поддерживаются `socks5` и `http`.

```python
client.run(
    router=router,
    proxy="socks5://username:password@192.168.1.1:1080"
    # или proxy="http://username:password@192.168.1.1:8080"
)
```

---

## 🔀 Механика Роутера (Router)

Ncore обладает мощным роутером на базе регулярных выражений, который позволяет элегантно извлекать аргументы из сообщений.

### Регистрация обработчиков
```python
from Ncore import Router
from Ncore.types import EventType

router = Router(prefixes=["/", "."])

# Обработка команды .join или /join для события updateEditMessage
@router.add("join" EventType.EditMessage)
async def all_messages_handler(event):
    pass
```

### 🧠 Умные параметры и типизация в командах
Ncore автоматически парсит параметры команды из текста сообщения с помощью синтаксиса `<имя_параметра: тип>`. Если параметр обязательный, перед его именем ставится `!` (например, `<!reason: str>`). 

Поддерживаемые типы данных:
| Тип | Описание |
|---|---|
| `int` | Извлекает целые числа. Передастся в функцию как `int`. |
| `float` | Извлекает числа с плавающей точкой. Передастся как `float`. |
| `bool` | Извлекает логические значения (`1/0`, `true/false`, `on/off`, `yes/no`). Передастся как `bool`. |
| `str` | Извлекает строку до следующего пробела/переноса или до конца сообщения. |

**Пример продвинутого использования:**
```python
# Команда: /warn 123456789 Флуд
@router.add("warn <!user_id: int> <reason: str>")
async def warn_handler(event, user_id: int, reason: str | None):
    text = f"Выдано предупреждение пользователю {user_id}."
    if reason:
        text += f"\nПричина: {reason}"
    await event.answer(text)
```
*Роутер Ncore компилирует это в Regex, автоматически обрабатывая динамические пробелы и переносы строк (`\n`) как разделители.*

### Пользовательские фильтры (Custom Filters)

Вы можете передать кастомный асинхронный фильтр в декоратор:

```python
async def is_admin(raw_update: dict) -> bool:
    # Проверка прав (возвращает True/False)
    return True

@router.add("admin", filter=is_admin)
async def admin_command(event):
    await event.answer("Доступ разрешен.")
```

---

## 📨 События и Сущности (Events & Entities)

Каждый обработчик получает объект `event` (например, `NcoreUpdateNewMessage`), содержащий удобные абстракции над сырыми данными Telegram.

### Работа с Entities (Форматирование)
Свойство `event.entities` возвращает список объектов форматирования текста. Фреймворк автоматически парсит их в удобные Python-классы:

```python
from Ncore.types import MessageEntityTextUrl

@router.add(EventType.NewMessage)
async def entity_parser(event):
    if event.entities:
        for ent in event.entities:
            # ent.value возвращает сам текст, к которому применено форматирование
            print(f"Тип: {ent._}, Текст: {ent.value}")
            
            if ent._ == "messageEntityTextUrl":
                print(f"Ссылка: {ent.url}")
            # Или
            if isinstance(ent, MessageEntityTextUrl):
                print(f"Ссылка: {ent.url}")
```

### Быстрый ответ
Метод `answer()` автоматически определяет тип чата (User, Chat, Channel) и топик (forum_topic), отправляя ответ в нужное место.
```python
await event.answer("Это быстрый ответ на ваше сообщение!")
```

---

## 📝 Взаимодействие с API

### 1. Вызов нативных оберток
Вы можете вызывать готовые методы клиента:

```python
import random

from Ncore.types import InputPeerUser

await client.send_message(
    message="Привет напрямую через API!",
    peer=InputPeerUser(user_id=123, access_hash=456),
    random_id=random.getrandbits(60)
)
```

### 2. Сырые запросы (Raw Invoke)
Так как Ncore включает в себя полный парсер `tl_schema.json` на Cython, **вы можете вызвать абсолютно любой метод Telegram API**, даже если для него еще нет красивой обертки в `methods/`.

Для этого используется метод `client.session.invoke()`, который автоматически запакует ваш запрос в нужные TL-структуры, добавит батчинг и обработает `FloodWait`:

```python
# Пример: Получение информации о пользователе через сырой invoke
result = await client.session.invoke({
    "_": "users.getFullUser",
    "id": {
        "_": "inputUser",
        "user_id": 1234567,
        "access_hash": 890123456
    }
})

print(result["user"]["first_name"])
```
*Фреймворк сам найдет конструктор `users.getFullUser` и `inputUser` в схеме, скомпилирует байты и отправит на сервер.*
