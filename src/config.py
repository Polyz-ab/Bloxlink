from resources.constants import RELEASE, IS_DOCKER # pylint: disable=import-error

# More optional settings can be set, such as a Trello key/token. Look at the docker-compose.yml for additional values.

PREFIX = "!"

WEBHOOKS = { # discord webhook links
	"LOGS":  None,
	"ERRORS": None
}

REACTIONS = { # discord emote mention strings
	"LOADING": "<a:BloxlinkLoading:530113171734921227>",
	"DONE": "<:BloxlinkSuccess:506622931791773696>",
	"DONE_ANIMATED": "<a:BloxlinkDone:528252043211571210>",
	"ERROR": "<:BloxlinkError:506622933226225676>",
	"VERIFIED": "<a:Verified:734628839581417472>",
	"BANNED": "<:ban:476838302092230672>"
}

RETHINKDB_HOST = "rethinkdb"
RETHINKDB_PASSWORD = None
RETHINKDB_PORT = 28015
RETHINKDB_DB = "bloxlink"

REDIS_HOST = "redis"
REDIS_PORT = 6379
REDIS_PASSWORD = None

TOKEN = ODAxODYwODA4MTk0NjU0MjI4.YAm1Eg.UykjkDGwtpSZvIqkpnw1vQrbOQ8

BLOXLINK_GUILD = None # your guild ID, used to load nitro boosters and other data

BOTS = {
	"PRO": 469652514501951518,
	"MAIN": 426537812993638400,
	"CANARY": 442912486702710784,
	"LOCAL": 454053406471094282
}

RESTRICTIONS_TRELLO = "" # Your Trello board link to load restrictions.
						 # Board must have 3 lists: "Roblox IDs", "Discord IDs", and "Servers"
						 # Card format:
						 	# card name: label:id
							# card desc: restriction text
							# The label has no effect on restrictions. It's for visual purposes only.
