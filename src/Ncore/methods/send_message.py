from typing import overload


class SendMessage:
    @overload
    def send_message(
        self,
        message: str,
        rnd_id: int
    ) -> dict:
        """TEST METHOD, NOT WORK"""
        ...

    def send_message(self, **params):
        params["_"] = "messages.sendMessage"
        return params