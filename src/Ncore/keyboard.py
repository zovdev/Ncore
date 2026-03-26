from typing import Optional, overload


from .base.types import aliases
from .base.types import ReplyInlineMarkup, ReplyKeyboardMarkup, KeyboardButtonRow, KeyboardButton


class InlineKeyboard(ReplyInlineMarkup):
    __slots__ = ("__idx", "__max_idx")

    def __init__(self, rows: list[aliases.AnyKeyboardButtonRow] | None=None):
        self['_'] = 'replyInlineMarkup'

        if not rows:
            self['rows'] = [{"buttons": [], '_': "keyboardButtonRow"}]
            self.__max_idx = 0
            self.__idx = 0
        else:
            self['rows'] = rows
            self.__max_idx = len(rows) - 1
            self.__idx = self.__max_idx

    def row(self, current_row: int | None=None):
        if current_row is not None:
            if current_row > self.__max_idx:
                raise ValueError("current_row должен быть меньше или равен максимальному количеству рядов")
            self.__idx = current_row
            return self

        self.__idx += 1

        if self.__idx > self.__max_idx:
            self["rows"].append({"buttons": [], '_': "keyboardButtonRow"})
            self.__max_idx += 1

        return self

    @overload
    def url(self, text: str, url: str, style: Optional[aliases.AnyKeyboardButtonStyle] = ...): ...

    def url(self, text, url, _='keyboardButtonUrl', **kwargs):
        kwargs['text'] = text
        kwargs['url'] = url
        kwargs['_'] = _

        self["rows"][self.__idx]["buttons"].append(kwargs)
        return self

    @overload
    def callback(self, text: str, data: bytes, requires_password: Optional[bool] = ..., style: Optional[aliases.AnyKeyboardButtonStyle] = ...): ...

    def callback(self, text, data, _='keyboardButtonCallback', **kwargs):
        kwargs['text'] = text
        kwargs['data'] = data
        kwargs['_'] = _

        self["rows"][self.__idx]["buttons"].append(kwargs)
        return self

    @overload
    def switch_inline(self, text: str, query: str, same_peer: Optional[bool] = ..., style: Optional[aliases.AnyKeyboardButtonStyle] = ..., peer_types: Optional[list[aliases.AnyInlineQueryPeerType]] = ...): ...

    def switch_inline(self, text, query, _='keyboardButtonSwitchInline', **kwargs):
        kwargs['text'] = text
        kwargs['query'] = query
        kwargs['_'] = _

        self["rows"][self.__idx]["buttons"].append(kwargs)
        return self

    @overload
    def game(self, text: str, style: Optional[aliases.AnyKeyboardButtonStyle] = ...): ...

    def game(self, text, _='keyboardButtonGame', **kwargs):
        kwargs['text'] = text
        kwargs['_'] = _

        self["rows"][self.__idx]["buttons"].append(kwargs)
        return self

    @overload
    def buy(self, text: str, style: Optional[aliases.AnyKeyboardButtonStyle] = ...): ...

    def buy(self, text, _='keyboardButtonBuy', **kwargs):
        kwargs['text'] = text
        kwargs['_'] = _

        self["rows"][self.__idx]["buttons"].append(kwargs)
        return self

    @overload
    def url_auth(self, text: str, url: str, bot: aliases.AnyInputUser, request_write_access: Optional[bool] = ..., style: Optional[aliases.AnyKeyboardButtonStyle] = ..., fwd_text: Optional[str] = ...): ...

    def url_auth(self, text, url, bot, _='inputKeyboardButtonUrlAuth', **kwargs):
        kwargs['text'] = text
        kwargs['url'] = url
        kwargs['bot'] = bot
        kwargs['_'] = _

        self["rows"][self.__idx]["buttons"].append(kwargs)
        return self

    @overload
    def web_view(self, text: str, url: str, style: Optional[aliases.AnyKeyboardButtonStyle] = ...): ...

    def web_view(self, text, url, _='keyboardButtonWebView', **kwargs):
        kwargs['text'] = text
        kwargs['url'] = url
        kwargs['_'] = _

        self["rows"][self.__idx]["buttons"].append(kwargs)
        return self

    @overload
    def simple_web_view(self, text: str, url: str, style: Optional[aliases.AnyKeyboardButtonStyle] = ...): ...

    def simple_web_view(self, text, url, _='keyboardButtonSimpleWebView', **kwargs):
        kwargs['text'] = text
        kwargs['url'] = url
        kwargs['_'] = _

        self["rows"][self.__idx]["buttons"].append(kwargs)
        return self

    @overload
    def copy_button(self, text: str, copy_text: str, style: Optional[aliases.AnyKeyboardButtonStyle] = ...): ...

    def copy_button(self, text, copy_text, _='keyboardButtonCopy', **kwargs):
        kwargs['text'] = text
        kwargs['copy_text'] = copy_text
        kwargs['_'] = _

        self["rows"][self.__idx]["buttons"].append(kwargs)
        return self

    @overload
    def user_profile(self, text: str, user_id: aliases.AnyInputUser, style: Optional[aliases.AnyKeyboardButtonStyle] = ...): ...

    def user_profile(self, text, user_id, _='inputKeyboardButtonUserProfile', **kwargs):
        kwargs['text'] = text
        kwargs['user_id'] = user_id
        kwargs['_'] = _

        self["rows"][self.__idx]["buttons"].append(kwargs)
        return self


keyb = InlineKeyboard() # создание клавиатуры
print(keyb)

keyb.row() # добавление новой строки ряда

keyb.url("lox", "vk.com") # добавление кнопки ссылки

keyb.row() # добавление новой строки ряда

print(keyb)
print("="*20)


keyb = InlineKeyboard() # создание клавиатуры
print(keyb)

keyb.row() # добавление новой строки ряда

keyb.row() # добавление новой строки ряда

print(keyb)
print("="*20)


keyb = InlineKeyboard(rows=[
    KeyboardButtonRow([KeyboardButton("lol"), KeyboardButton("lol2")]),
    KeyboardButtonRow([KeyboardButton("lol3"), KeyboardButton("lol4")])
]) # создание заполненой клавиатуры
print(keyb)

keyb.row() # создание 3 ряда

keyb.row() # создание 4 ряда

print(keyb)

keyb.row(current_row=1) # переход к 1 строке ряда

print(keyb)
