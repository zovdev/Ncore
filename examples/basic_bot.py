from Ncore import Client


async def custom_handle_updates(message):
    client.info(f"Новое событие - {message['_']}")


def main():
    client = Client(api_id=1234, api_hash="...", bot_token="...")

    client.loop.run_until_complete(client.start(handle_updates=custom_handle_updates))

    client.loop.run_forever()

main()