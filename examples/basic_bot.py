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
