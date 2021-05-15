__version_info__ = (0, 0, 0)
__version__ = '.'.join(map(str, __version_info__))

from .client import Client
from .bot import Bot
from .errors import *
