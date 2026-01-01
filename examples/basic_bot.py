import asyncio
from Ncore import Client


async def main():
    client = Client(api_id=12345, api_hash="...", bot_token="...")
    await client.start()
    print("Клиент успешно запущен!")

    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Завершение работы.")
