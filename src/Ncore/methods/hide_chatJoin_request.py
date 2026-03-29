from ..base import InputUser, AnyInputPeer


class HideChatJoinRequest:
    async def chat_join_approved(
            self,
            peer: AnyInputPeer,
            user_id: InputUser,
            approved: bool | None = True,
            **params
    ) -> dict:
        params["_"] = "messages.hideChatJoinRequest"
        params["peer"] = peer
        params["user_id"] = user_id
        params["approved"] = approved
        return await self.invoke(params)
