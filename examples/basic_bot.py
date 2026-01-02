from Ncore import Client


client = Client(api_id=1234, api_hash="...", bot_token="...")


async def custom_handle_updates(message):
    client.info(f"Новое событие - {message['_']}")


client.loop.run_until_complete(client.start(handle_updates=custom_handle_updates))

client.loop.run_forever()
