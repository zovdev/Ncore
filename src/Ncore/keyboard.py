from .base.types import aliases
from .base.types import ReplyInlineMarkup, ReplyKeyboardMarkup, KeyboardButtonRow, KeyboardButton


class InlineKeyboard(dict):
    __slots__ = ("__idx", "__max_idx")

    def __init__(self, rows: list[aliases.AnyKeyboardButtonRow] | None=None):
        if rows is None:
            rows = []

        dict.__init__(self, rows=rows, _="replyInlineMarkup")
        self.__max_idx = len(rows)-1
        self.__idx = -1

    def row(self, current_row: int | None=None):
        if current_row is not None:
            if current_row > self.__max_idx:
                raise ValueError("current_row должен быть меньше или равен максимальному количеству рядов")
            self.__idx = current_row
            return self

        self.__idx += 1

        print(self.__idx, self.__max_idx)

        if self.__idx > self.__max_idx:
            self["rows"].append({"buttons": [], '_': "keyboardButtonRow"})
            self.__max_idx += 1

        return self



keyb = InlineKeyboard() # создание клавиатуры
print(keyb)

keyb.row() # добавление новой строки ряда

keyb.row() # добавление новой строки ряда

print(keyb)
print("="*6)


keyb = InlineKeyboard(rows=[
    KeyboardButtonRow([KeyboardButton("lol"), KeyboardButton("lol2")]),
    KeyboardButtonRow([KeyboardButton("lol3"), KeyboardButton("lol4")])
]) # создание заполненой клавиатуры
print(keyb)

keyb.row() # переход к 0 строке ряда

keyb.row() # переход к 1 строке ряда

keyb.row() # создание и переход к 2 строке ряда

keyb.row() # создание и переход к 3 строке ряда

print(keyb)

keyb.row(current_row=1) # переход к 1 строке ряда

print(keyb)