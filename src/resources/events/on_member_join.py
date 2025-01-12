from ..structures.Bloxlink import Bloxlink # pylint: disable=import-error
from ..constants import DEFAULTS # pylint: disable=import-error
from ..exceptions import CancelCommand, RobloxDown # pylint: disable=import-error
from discord.errors import Forbidden

get_guild_value = Bloxlink.get_module("cache", attrs=["get_guild_value"])
guild_obligations = Bloxlink.get_module("roblox", attrs=["guild_obligations"])


@Bloxlink.module
class MemberJoinEvent(Bloxlink.Module):
    def __init__(self):
        pass

    async def __setup__(self):

        @Bloxlink.event
        async def on_member_join(member):
            guild = member.guild

            if self.redis:
                options = await get_guild_value(guild, ["autoRoles", DEFAULTS.get("autoRoles")], ["autoVerification", DEFAULTS.get("autoVerification")], ["verifiedDM", DEFAULTS.get("welcomeMessage")], ["unverifiedDM", DEFAULTS.get("unverifiedDM")])

                auto_roles = options.get("autoRoles")
                auto_verification = options.get("autoVerification")
                verified_dm = options.get("verifiedDM")
                unverified_dm = options.get("unverifiedDM")

                join_dm = verified_dm or unverified_dm

                if member.pending:
                    if join_dm:
                        try:
                            await member.send(f"This server ({guild.name}) has **Member Screening** enabled. Please "
                                              "complete the screening in order to access the rest of the server.")
                        except Forbidden:
                            pass
                else:
                    if auto_verification or auto_roles:
                        try:
                            await guild_obligations(member, guild, cache=False, dm=True, event=True, exceptions=("RobloxDown",))
                        except CancelCommand:
                            pass
                        except RobloxDown:
                            try:
                                await member.send("Roblox appears to be down, so I was unable to retrieve your Roblox information. Please try again later.")
                            except Forbidden:
                                pass
