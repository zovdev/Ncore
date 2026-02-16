# Copyright 2026 zovdev
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
from typing import overload

from Ncore.types import build_event, EventType


_BOOL_TRUE_VALUES = frozenset({"1", "true", "on", "yes", "enable"})


class HandlerMeta:
    __slots__ = ("func", "arg_instructions", "custom_filter")

    def __init__(self, func, args_mapping, custom_filter):
        self.func = func

        if args_mapping:
            self.arg_instructions = tuple(
                (g_name, arg_name, conv) 
                for g_name, (arg_name, conv) in args_mapping.items()
            )
        else:
            self.arg_instructions = None

        self.custom_filter = custom_filter


class RouteNode:
    __slots__ = ("regex", "handlers_meta")
    def __init__(self, regex, handlers_meta):
        self.regex = regex
        self.handlers_meta = handlers_meta


class Router:
    def __init__(self, prefixes: list[str]=["/"]):
        self._raw_registrations = []
        self._routes = {}
        self._tag_parser = re.compile(r"^<(!?)([a-zA-Z0-9_]+):\s*(int|str|float|bool)>$")
        self.prefixes = sorted(prefixes, key=len, reverse=True)

    @overload
    def add(self, command: str, event_type: set[str] | None, filter=lambda e: True):
        ...

    @overload
    def add(self, event_type: set[str], command: str | None, filter=lambda e: True):
        ...

    def add(self, arg1: str | set[str], arg2: str | set[str] | None=None, filter=lambda e: True):
        def decorator(func):
            command_pattern = None
            event_types = set()

            for arg in [arg1, arg2]:
                if isinstance(arg, str):
                    command_pattern = arg
                elif isinstance(arg, set):
                    event_types = arg

            if not event_types:
                event_types = EventType.NewMessage

            self._raw_registrations.append({
                "func": func,
                "cmd": command_pattern,
                "types": frozenset(event_types),
                "filter": filter
            })
            return func
        return decorator

    def _convert_bool(self, val):
        return val.lower() in _BOOL_TRUE_VALUES

    def _compile_cmd_pattern(self, command, handler_uid):
        arg_idx = 0
        final_pattern = ""
        args_map = {}
        parts = [p.strip() for p in re.split(r"(<[^>]+>)", command) if p.strip()]

        for i, part in enumerate(parts):
            part_regex = ""
            is_optional_param = False
            tag_match = self._tag_parser.match(part)

            if tag_match:
                req_mark, name, typ = tag_match.groups()
                is_optional_param = not (req_mark == "!")

                g_name = f"{handler_uid}_a{arg_idx}"
                arg_idx += 1

                if typ == "int":
                    ptn = r"\d+"
                    cnv = int
                elif typ == "float":
                    ptn = r"\d+(?:\.\d+)?" 
                    cnv = float
                elif typ == "str":
                    ptn = r".+"
                    cnv = str
                elif typ == 'bool':
                    ptn = r"(?i:1|0|true|false|on|off|yes|no)"
                    cnv = self._convert_bool
                else:
                    ptn = r"\S+"
                    cnv = str

                part_regex = f"(?P<{g_name}>{ptn})"
                args_map[g_name] = (name, cnv)
            else:
                part_regex = re.escape(part)

            if i == 0:
                if is_optional_param:
                    final_pattern += f"(?:{part_regex})?"
                else:
                    final_pattern += part_regex
            else:
                if is_optional_param:
                    final_pattern += f"(?:\\s+{part_regex})?"
                else:
                    final_pattern += f"\\s+{part_regex}"

        return final_pattern, args_map

    def finalize(self, client):
        self.client = client

        prefix_regex = ""
        if self.prefixes:
            prefix_regex = f"(?:{'|'.join(re.escape(p) for p in self.prefixes)})\\s*"

        grouped = {}
        for reg in self._raw_registrations:
            t = reg["types"]
            if t not in grouped: grouped[t] = []
            grouped[t].append(reg)

        for types_set, handlers in grouped.items():
            regex_opts = []
            meta_map = {}
            specific= []
            generics = []

            for h in handlers:
                (specific if h["cmd"] else generics).append(h)

            specific.sort(key=lambda x: len(x["cmd"]), reverse=True)

            for i, h in enumerate(specific + generics):
                uid = f"h{i}"
                if h["cmd"]:
                    p_str, args = self._compile_cmd_pattern(h["cmd"], uid)
                    regex_opts.append(f"(?P<{uid}>^{prefix_regex}{p_str}$)")
                else:
                    p_str, args = r".*", {}
                    regex_opts.append(f"(?P<{uid}>^{p_str}$)")

                meta_map[uid] = HandlerMeta(h["func"], args, h["filter"])

            if not regex_opts: continue

            full_regex = re.compile("|".join(regex_opts), re.DOTALL)
            group_index_map = full_regex.groupindex

            for uid, meta in meta_map.items():
                if meta.arg_instructions:
                    new_instructions = []
                    for g_name, arg_name, conv in meta.arg_instructions:
                        g_idx = group_index_map.get(g_name)
                        new_instructions.append((g_idx, arg_name, conv))

                    meta.arg_instructions = tuple(new_instructions)

            node = RouteNode(full_regex, meta_map)

            for t_str in types_set:
                self._routes[t_str] = node

        del self._raw_registrations

    async def _process_single_update(self, update, full_context):
        if update["_"] not in self._routes:
            return

        node = self._routes[update["_"]]

        if "message" not in update:
            match = node.regex.match("")
        elif "message" not in update["message"]:
            match = node.regex.match("")
        else:
            match = node.regex.match(update["message"]["message"])

        if not match:
            return

        meta = node.handlers_meta[match.lastgroup]
        if not await meta.custom_filter(full_context):
            return

        if meta.arg_instructions is None:
            return await meta.func(build_event(self.client, update, full_context))

        kwargs = {}
        for g_idx, arg_name, conv in meta.arg_instructions:
            val = match.group(g_idx)
            if val is None:
                kwargs[arg_name] = None
            else:
                kwargs[arg_name] = conv(val)

        await meta.func(build_event(self.client, update, full_context), **kwargs)

    async def feed(self, raw_data):
        obj_type = raw_data["_"]
        if obj_type in {"updates", "updatesCombined"}:
            for update in raw_data["updates"]:
                await self._process_single_update(update, full_context=raw_data)
        elif obj_type == "updateShort":
            return await self._process_single_update(raw_data["update"], full_context=raw_data)
        else:
            return await self._process_single_update(raw_data, full_context=raw_data)