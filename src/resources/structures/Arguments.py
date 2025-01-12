from asyncio import TimeoutError
from discord.errors import Forbidden, NotFound, HTTPException
from discord import Embed
from ..structures.Bloxlink import Bloxlink # pylint: disable=import-error
from ..exceptions import CancelledPrompt, CancelCommand, Error # pylint: disable=import-error
from ..constants import RED_COLOR, INVISIBLE_COLOR # pylint: disable=import-error
from config import RELEASE # pylint: disable=no-name-in-module
from ..constants import IS_DOCKER, TIP_CHANCES, SERVER_INVITE, PROMPT # pylint: disable=import-error
import random

get_resolver = Bloxlink.get_module("resolver", attrs="get_resolver")
broadcast = Bloxlink.get_module("ipc", attrs="broadcast")

prompts = {}



class Arguments:
    def __init__(self, CommandArgs, author, channel, command, guild=None, message=None, subcommand=None, slash_command=None):
        self.channel = channel
        self.author  = author
        self.message = message
        self.guild   = guild

        self.command    = command
        self.subcommand = subcommand

        self.command_args = CommandArgs
        self.response     = CommandArgs.response
        self.locale       = CommandArgs.locale
        self.prefix       = CommandArgs.prefix

        self.messages  = []
        self.dm_post   = None
        self.cancelled = False
        self.dm_false_override = False
        self.skipped_args = []

        self.slash_command = slash_command

        self.parsed_args = {}

    async def initial_command_args(self, text_after=None):
        if self.subcommand:
            prompts = self.subcommand[1].get("arguments")
        else:
            prompts = self.command.arguments


        if self.slash_command:
            if not isinstance(self.slash_command, bool):
                self.skipped_args = [x[1] for x in self.slash_command]

            self.parsed_args = await self.prompt(prompts, slash_command=True) if prompts else {}
            self.command_args.add(parsed_args=self.parsed_args, string_args=[])

            return

        arg_len = len(prompts) if prompts else 0
        skipped_args = []
        split = text_after.split(" ")
        temp = []

        for arg in split:
            if arg:
                if arg.startswith('"') and arg.endswith('"'):
                    arg = arg.replace('"', "")

                if len(skipped_args) + 1 == arg_len:
                    t = text_after.replace('"', "")
                    toremove = " ".join(skipped_args)

                    if t.startswith(toremove):
                        t = t[len(toremove):]

                    t = t.strip()

                    skipped_args.append(t)

                    break

                if arg.startswith('"') or (temp and not arg.endswith('"')):
                    temp.append(arg.replace('"', ""))

                elif arg.endswith('"'):
                    temp.append(arg.replace('"', ""))
                    skipped_args.append(" ".join(temp))
                    temp.clear()

                else:
                    skipped_args.append(arg)

        if len(skipped_args) > 1:
            self.skipped_args = skipped_args
        else:
            if text_after:
                self.skipped_args = [text_after]
            else:
                self.skipped_args = []

        if prompts:
            self.parsed_args = await self.prompt(prompts)

        self.command_args.add(parsed_args=self.parsed_args, string_args=text_after and text_after.split(" ") or [])


    async def say(self, text, type=None, footer=None, embed_title=None, is_prompt=True, embed_color=INVISIBLE_COLOR, embed=True, dm=False):
        embed_color = embed_color or INVISIBLE_COLOR

        if self.dm_false_override:
            dm = False

        if footer:
            footer = f"{footer}\n"
        else:
            footer = ""

        if not embed:
            if is_prompt:
                text = f"{text}\n\n{footer}{self.locale('prompt.toCancel')}\n\n{self.locale('prompt.timeoutWarning', timeout=PROMPT['PROMPT_TIMEOUT'])}"

            return await self.response.send(text, dm=dm, no_dm_post=True, strict_post=True)

        description = f"{text}\n\n{footer}{self.locale('prompt.toCancel')}"

        if type == "error":
            new_embed = Embed(title=embed_title or self.locale("prompt.errors.title"))
            new_embed.colour = RED_COLOR

            show_help_tip = random.randint(1, 100)

            if show_help_tip <= TIP_CHANCES["PROMPT_ERROR"]:
                description = f"{description}\n\nExperiencing issues? Our [Support Server]({SERVER_INVITE}) has a team of Helpers ready to help you if you're having trouble!"
        else:
            new_embed = Embed(title=embed_title or self.locale("prompt.title"))
            new_embed.colour = embed_color

        new_embed.description = description

        new_embed.set_footer(text=self.locale("prompt.timeoutWarning", timeout=PROMPT["PROMPT_TIMEOUT"]))

        msg = await self.response.send(embed=new_embed, dm=dm, no_dm_post=True, strict_post=True, ignore_errors=True)

        if not msg:
            if is_prompt:
                text = f"{text}\n\n{self.locale('prompt.toCancel')}\n\n{self.locale('prompt.timeoutWarning', timeout=PROMPT['PROMPT_TIMEOUT'])}"

            return await self.response.send(text, dm=dm, no_dm_post=True, strict_post=True)

        if msg and not dm:
            self.messages.append(msg.id)

        return msg


    @staticmethod
    def in_prompt(author):
        return prompts.get(author.id)

    async def prompt(self, arguments, error=False, embed=True, dm=False, no_dm_post=False, last=False, slash_command=False):
        prompts[self.author.id] = True

        checked_args = 0
        err_count = 0
        resolved_args = {}
        had_args = {x:True for x, y in enumerate(self.skipped_args)}

        if dm:
            if IS_DOCKER:
                try:
                    m = await self.author.send("Loading setup...")
                except Forbidden:
                    dm = False
                else:
                    try:
                        await m.delete()
                    except NotFound:
                        pass

                    if not no_dm_post:
                        self.dm_post = await self.response.send(f"{self.author.mention}, **please check your DMs to continue.**", ignore_errors=True, strict_post=True)
            else:
                dm = False

        try:
            while checked_args != len(arguments):
                if err_count == PROMPT["PROMPT_ERROR_COUNT"]:
                    raise CancelledPrompt("Too many failed attempts.", type="delete")

                if last and checked_args +1 == len(arguments):
                    self.skipped_args = [" ".join(self.skipped_args)]

                prompt_ = arguments[checked_args]
                skipped_arg = self.skipped_args and str(self.skipped_args[0])
                message = self.message

                if prompt_.get("optional") and not had_args.get(checked_args):
                    if self.skipped_args:
                        self.skipped_args.pop(0)
                        had_args[checked_args] = True

                    resolved_args[prompt_["name"]] = None
                    checked_args += 1

                    continue

                formatting = prompt_.get("formatting", True)
                prompt_text = prompt_["prompt"]

                if not skipped_arg:
                    try:
                        if formatting:
                            prompt_text = prompt_text.format(**resolved_args, prefix=self.prefix)

                        await self.say(prompt_text, embed_title=prompt_.get("embed_title"), embed_color=prompt_.get("embed_color"), footer=prompt_.get("footer"), type=error and "error", embed=embed, dm=dm)

                        if dm and IS_DOCKER:
                            message_content = await broadcast(self.author.id, type="DM", send_to=f"{RELEASE}:CLUSTER_0", waiting_for=1, timeout=PROMPT["PROMPT_TIMEOUT"])
                            skipped_arg = message_content[0]

                            if not skipped_arg:
                                await self.say("Cluster which handles DMs is temporarily unavailable. Please say your message in the server instead of DMs.", type="error", embed=embed, dm=dm)
                                self.dm_false_override = True
                                dm = False

                                message = await Bloxlink.wait_for("message", check=self._check_prompt(), timeout=PROMPT["PROMPT_TIMEOUT"])

                                skipped_arg = message.content

                                if prompt_.get("delete_original", True):
                                    self.messages.append(message.id)

                            if skipped_arg == "cluster timeout":
                                skipped_arg = "cancel (timeout)"

                        else:
                            message = await Bloxlink.wait_for("message", check=self._check_prompt(dm), timeout=PROMPT["PROMPT_TIMEOUT"])

                            skipped_arg = message.content

                            if prompt_.get("delete_original", True):
                                self.messages.append(message.id)

                        skipped_arg_lower = skipped_arg.lower()
                        if skipped_arg_lower == "cancel":
                            raise CancelledPrompt(type="delete", dm=dm)
                        elif skipped_arg_lower == "cancel (timeout)":
                            raise CancelledPrompt(f"timeout ({PROMPT['PROMPT_TIMEOUT']}s)", dm=dm)

                    except TimeoutError:
                        raise CancelledPrompt(f"timeout ({PROMPT['PROMPT_TIMEOUT']}s)", dm=dm)

                skipped_arg_lower = str(skipped_arg).lower()

                if skipped_arg_lower in prompt_.get("exceptions", []):
                    if self.skipped_args:
                        self.skipped_args.pop(0)
                        had_args[checked_args] = True

                    checked_args += 1
                    resolved_args[prompt_["name"]] = skipped_arg_lower

                    continue

                resolver_types = prompt_.get("type", "string")

                if not isinstance(resolver_types, list):
                    resolver_types = [resolver_types]

                resolve_errors = []
                resolved = False
                error_message = None

                for resolver_type in resolver_types:
                    resolver = get_resolver(resolver_type)
                    resolved, error_message = await resolver(prompt_, content=skipped_arg, guild=self.guild, message=message)

                    if resolved:
                        if prompt_.get("validation"):
                            res = [await prompt_["validation"](content=skipped_arg, message=not dm and message, prompt=self.prompt)]

                            if isinstance(res[0], tuple):
                                if not res[0][0]:
                                    error_message = res[0][1]
                                    resolved = False

                            else:
                                if not res[0]:
                                    error_message = "Prompt failed validation. Please try again."
                                    resolved = False

                            if resolved:
                                resolved = res[0]
                    else:
                        error_message = f"{self.locale('prompt.errors.invalidArgument', arg='**' + resolver_type + '**')}: `{error_message}`"

                    if error_message:
                        resolve_errors.append(error_message)
                    else:
                        break

                if resolved:
                    checked_args += 1
                    resolved_args[prompt_["name"]] = resolved
                else:
                    await self.say("\n".join(resolve_errors), type="error", embed=embed, dm=dm)

                    if self.skipped_args:
                        self.skipped_args.pop(0)
                        had_args[checked_args] = True

                    err_count += 1

                if self.skipped_args:
                    self.skipped_args.pop(0)
                    had_args[checked_args] = True

            return resolved_args

        finally:
            prompts.pop(self.author.id, None)


    def _check_prompt(self, dm=False):
        def wrapper(message):
            if message.author.id  == self.author.id:
                if dm:
                    return not message.guild
                else:
                    return message.channel.id == self.channel.id
            else:
                return False

        return wrapper