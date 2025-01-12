from discord.errors import Forbidden, HTTPException, DiscordException, NotFound
from discord import Object, Webhook, AllowedMentions, User, Member, TextChannel, DMChannel
from discord.webhook import WebhookMessage
from ..exceptions import PermissionError, Message # pylint: disable=no-name-in-module, import-error
from ..structures import Bloxlink, Paginate # pylint: disable=no-name-in-module, import-error
from config import REACTIONS # pylint: disable=no-name-in-module
from ..constants import IS_DOCKER, EMBED_COLOR # pylint: disable=no-name-in-module, import-error
import asyncio

from discord.http import Route # temporary slash command workaround

loop = asyncio.get_event_loop()

get_features = Bloxlink.get_module("premium", attrs=["get_features"])
cache_set, cache_get, cache_pop = Bloxlink.get_module("cache", attrs=["set", "get", "pop"])


class InteractionWebhook(WebhookMessage):
    def __init__(self, interaction_token, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.interaction_token = interaction_token

    async def edit(self, content=None, embed=None, *args, **kwargs):
        payload = {
            "content": content,
            "embeds": [embed.to_dict()] if embed else None
        }

        route = Route("PATCH", "/webhooks/{application_id}/{interaction_token}/messages/{message_id}",
                      application_id=Bloxlink.user.id,
                      interaction_token=self.interaction_token, message_id=self.id)

        await self._state.http.request(route, json=payload)


    async def delete(self):
        route = Route("DELETE", "/webhooks/{application_id}/{interaction_token}/messages/{message_id}",
                      application_id=Bloxlink.user.id,
                      interaction_token=self.interaction_token, message_id=self.id)

        await self._state.http.request(route)


class ResponseLoading:
    def __init__(self, response, backup_text):
        self.response = response
        self.original_message = response.message
        self.reaction = None
        self.channel = response.channel

        self.reaction_success = False
        self.from_reaction_fail_msg = None

        self.backup_text = backup_text

    @staticmethod
    def _check_reaction(message):
        def _wrapper(reaction, user):
            return reaction.me and str(reaction) == REACTIONS["LOADING"] and message.id == reaction.message.id

    async def _send_loading(self):
        try:
            future = Bloxlink.wait_for("reaction_add", check=self._check_reaction(self.original_message), timeout=60)

            try:
                await self.original_message.add_reaction(REACTIONS["LOADING"])
            except (Forbidden, HTTPException):
                try:
                    self.from_reaction_fail_msg = await self.channel.send(self.backup_text)
                except Forbidden:
                    raise PermissionError
            else:
                reaction, _ = await future
                self.reaction_success = True
                self.reaction = reaction

        except (NotFound, asyncio.TimeoutError):
            pass

    async def _remove_loading(self, success=True, error=False):
        try:
            if self.reaction_success:
                for reaction in self.original_message.reactions:
                    if reaction == self.reaction:
                        try:
                            async for user in reaction.users():
                                await self.original_message.remove_reaction(self.reaction, user)
                        except (NotFound, HTTPException):
                            pass

                if error:
                    await self.original_message.add_reaction(REACTIONS["ERROR"])
                elif success:
                    await self.original_message.add_reaction(REACTIONS["DONE"])

            elif self.from_reaction_fail_msg is not None:
                await self.from_reaction_fail_msg.delete()

        except (NotFound, HTTPException):
            pass

    def __enter__(self):
        if not self.response.slash_command:
            loop.create_task(self._send_loading())
        return self

    def __exit__(self, tb_type, tb_value, traceback):
        if (tb_type is None) or (tb_type == Message):
            loop.create_task(self._remove_loading(error=False))
        else:
            loop.create_task(self._remove_loading(error=True))

    async def __aenter__(self):
        if not self.response.slash_command:
            await self._send_loading()

    async def __aexit__(self, tb_type, tb_value, traceback):
        if not self.response.slash_command:
            if tb_type is None:
                await self._remove_loading(success=True)
            elif tb_type == Message:
                await self._remove_loading(success=False, error=False)
            else:
                await self._remove_loading(error=True)



class Response(Bloxlink.Module):
    def __init__(self, CommandArgs, author, channel, guild=None, message=None, slash_command=False):
        self.message = message
        self.guild   = guild
        self.author  = author
        self.channel = channel
        self.prompt  = None # filled in on commands.py
        self.args    = CommandArgs
        self.command = CommandArgs.command

        self.delete_message_queue = []
        self.bot_responses        = []

        self.slash_command = slash_command

        if self.command.addon:
            if hasattr(self.command.addon, "whitelabel"):
                self.webhook_only = getattr(self.command.addon, "whitelabel")
            else:
                self.webhook_only = bool(CommandArgs.guild_data.get("customBot", {}))
        else:
            self.webhook_only = bool(CommandArgs.guild_data.get("customBot", {}))

        if self.webhook_only:
            if isinstance(self.webhook_only, bool):
                self.bot_name   = self.args.guild_data["customBot"].get("name", "Bloxlink")
                self.bot_avatar = self.args.guild_data["customBot"].get("avatar", "")
            else:
                self.bot_name   = self.webhook_only[0]
                self.bot_avatar = self.webhook_only[1]
        else:
            self.bot_name = self.bot_avatar = None

    def loading(self, text="Please wait until the operation completes."):
        return ResponseLoading(self, text)

    def delete(self, *messages):
        for message in messages:
            self.delete_message_queue.append(message.id)

    async def slash_ack(self):
        if self.slash_command:
            route = Route("POST", "/interactions/{interaction_id}/{interaction_token}/callback", interaction_id=self.slash_command["id"], interaction_token=self.slash_command["token"])

            payload = {
                "type": 5
            }

            await self.channel._state.http.request(route, json=payload)

    async def send_to(self, dest, content=None, files=None, embed=None, allowed_mentions=AllowedMentions(everyone=False, roles=False), send_as_slash_command=True, hidden=False, reference=None, reply=None, mention_author=None, fail_on_dm=None):
        msg = None

        if reply:
            reference = reference or self.message

        if fail_on_dm and isinstance(dest, (DMChannel, User, Member)):
            return None

        if isinstance(dest, Webhook):
            msg = await dest.send(content, username=self.bot_name, avatar_url=self.bot_avatar, embed=embed, files=files, wait=True, allowed_mentions=allowed_mentions)

        elif self.slash_command and send_as_slash_command:
            payload = {
                "content": content,
                "embeds": [embed.to_dict()] if embed else None,
                "flags": 1 << 6 if hidden else None
            }

            route = Route("POST", "/webhooks/{application_id}/{interaction_token}", application_id=Bloxlink.user.id, interaction_token=self.slash_command["token"])

            response = await self.channel._state.http.request(route, json=payload)

            msg = InteractionWebhook(interaction_token=self.slash_command["token"], data=response, state=self.channel._state, channel=self.channel)

        else:
            msg = await dest.send(content, embed=embed, files=files, allowed_mentions=allowed_mentions, reference=reference, mention_author=mention_author)


        self.bot_responses.append(msg.id)

        return msg

    async def send(self, content=None, embed=None, dm=False, no_dm_post=False, strict_post=False, files=None, ignore_http_check=False, paginate_field_limit=None, send_as_slash_command=True, channel_override=None, allowed_mentions=AllowedMentions(everyone=False, roles=False), hidden=False, ignore_errors=False, reply=True, reference=None, mention_author=False):
        if (dm and not IS_DOCKER) or (self.slash_command and hidden):
            dm = False

        if dm or isinstance(self.channel, DMChannel):
            send_as_slash_command = False
            reply = False
            reference = None
            mention_author = False

        content = str(content) if content else None

        channel = original_channel = channel_override or (dm and self.author) or self.channel
        webhook = None
        msg = None

        if not dm and not self.slash_command and self.webhook_only and self.guild and hasattr(channel, "webhooks"):
            my_permissions = self.guild.me.guild_permissions

            if my_permissions.manage_webhooks:
                profile, _ = await get_features(Object(id=self.guild.owner_id), guild=self.guild)

                if profile.features.get("premium"):
                    webhook = await cache_get(f"webhooks:{channel.id}")

                    if not webhook:
                        try:
                            for webhook in await channel.webhooks():
                                if webhook.token:
                                    await cache_set(f"webhooks:{channel.id}", webhook)
                                    break
                            else:
                                webhook = await channel.create_webhook(name="Bloxlink Webhooks")
                                await cache_set(f"webhooks:{channel.id}", webhook)

                        except (Forbidden, NotFound):
                            self.webhook_only = False

                            try:
                                msg = await channel.send("Customized Bot is enabled, but I couldn't "
                                                         "create the webhook! Please give me the `Manage Webhooks` permission.")
                            except (Forbidden, NotFound):
                                pass
                            else:
                                self.bot_responses.append(msg.id)
            else:
                self.webhook_only = False

                try:
                    msg = await channel.send("Customized Bot is enabled, but I couldn't "
                                             "create the webhook! Please give me the `Manage Webhooks` permission.")
                except (Forbidden, NotFound):
                    pass
                else:
                    self.bot_responses.append(msg.id)

        paginate = False
        pages = None

        if paginate_field_limit:
            pages = Paginate.get_pages(embed, embed.fields, paginate_field_limit)

            if len(pages) > 1:
                paginate = True

        if embed and not dm and not embed.color:
            embed.color = EMBED_COLOR

        if not paginate:
            try:
                msg = await self.send_to(webhook or channel, content, files=files, embed=embed, allowed_mentions=allowed_mentions, send_as_slash_command=send_as_slash_command, hidden=hidden, reply=reply, reference=reference, mention_author=mention_author)

                if dm and not (no_dm_post or isinstance(self.channel, (DMChannel, User, Member))):
                    await self.send_to(self.channel, "**Please check your DMs!**", reply=reply, reference=reference, mention_author=mention_author)

            except (Forbidden, NotFound):
                channel = channel_override or (not strict_post and (dm and self.channel or self.author) or channel) # opposite channel
                reply = False
                reference = None
                mention_author = False

                if isinstance(channel, (User, Member)) and isinstance(original_channel, TextChannel):
                    content = f"Disclaimer: you are getting this message DM'd since I don't have permission to post in {original_channel.mention}!\n{content or ''}"[:2000]
                else:
                    content = f"{original_channel.mention}, I was unable to DM you! Here's the message here instead:\n{content or ''}"[:2000]

                if webhook:
                    await cache_pop(f"webhooks:{channel.id}")

                if strict_post:
                    if not ignore_errors:
                        if dm:
                            try:
                                await self.send_to(self.channel, "I was unable to DM you! Please check your privacy settings and try again.", reply=reply, reference=reference, mention_author=mention_author)
                            except (Forbidden, NotFound):
                                pass
                        else:
                            try:
                                await self.send_to(self.author, f"I was unable to post in {channel.mention}! Please double check my permissions and try again.", reply=reply, reference=reference, mention_author=mention_author)
                            except (Forbidden, NotFound):
                                pass
                    return

                try:
                    msg = await self.send_to(channel, content, files=files, embed=embed, allowed_mentions=allowed_mentions, hidden=hidden, reply=reply, reference=reference, mention_author=mention_author)
                except (Forbidden, NotFound):
                    if not no_dm_post:
                        if channel == self.author:
                            try:
                                await self.send_to(self.channel, "I was unable to DM you! Please check your privacy settings and try again.", hidden=True, reply=reply, reference=reference, mention_author=mention_author)
                            except (Forbidden, NotFound):
                                pass
                        else:
                            try:
                                await self.send_to(self.channel, "I was unable to post in the specified channel!", hidden=True, reply=reply, reference=reference, mention_author=mention_author)
                            except (Forbidden, NotFound):
                                pass

            except HTTPException:
                if not ignore_http_check:
                    if self.webhook_only:
                        self.webhook_only = False

                        return await self.send(content=content, embed=embed, dm=dm, hidden=hidden, no_dm_post=no_dm_post, strict_post=strict_post, files=files, send_as_slash_command=send_as_slash_command, allowed_mentions=allowed_mentions, ignore_errors=ignore_errors)

                    else:
                        if embed:
                            paginate = True

                        else:
                            raise HTTPException
        if paginate:
            paginator = Paginate(self.author, channel, embed, self, field_limit=paginate_field_limit, original_channel=self.channel, hidden=hidden, pages=pages, dm=dm)

            return await paginator()


        return msg

    async def error(self, text, *, embed_color=0xE74C3C, embed=None, dm=False, **kwargs):
        emoji = self.webhook_only and ":cry:" or "<:BloxlinkDead:823633973967716363>"

        if embed and not dm:
            embed.color = embed_color

        return await self.send(f"{emoji} {text}", **kwargs)

    async def confused(self, text, *, embed_color=0xE74C3C, embed=None, dm=False, **kwargs):
        emoji = self.webhook_only and ":cry:" or "<:BloxlinkConfused:823633690910916619>"

        if embed and not dm:
            embed.color = embed_color

        return await self.send(f"{emoji} {text}", **kwargs)

    async def success(self, success, embed=None, embed_color=0x36393E, dm=False, **kwargs):
        emoji = self.webhook_only and ":thumbsup:" or "<:BloxlinkHappy:823633735446167552>"

        if embed and not dm:
            embed.color = embed_color

        return await self.send(f"{emoji} {success}", embed=embed, dm=dm, **kwargs)

    async def silly(self, text, embed=None, embed_color=0x36393E, dm=False, **kwargs):
        emoji = self.webhook_only and ":sweat_smile:" or "<:BloxlinkSilly:823634273604468787>"

        if embed and not dm:
            embed.color = embed_color

        return await self.send(f"{emoji} {text}", embed=embed, dm=dm, **kwargs)

    async def info(self, text, embed=None, embed_color=0x36393E, dm=False, **kwargs):
        emoji = self.webhook_only and ":mag_right:" or "<:BloxlinkDetective:823633815171629098>"

        if embed and not dm:
            embed.color = embed_color

        return await self.send(f"{emoji} {text}", embed=embed, dm=dm, **kwargs)

    async def reply(self, text, embed=None, embed_color=0x36393E, dm=False, **kwargs):
        return await self.send(f"{self.author.mention}, {text}", embed=embed, dm=dm, **kwargs)
