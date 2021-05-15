# SPDX-License-Identifier: EUPL-1.2

import pytz
import yarl
import httpx
import string
import random
import typing
import hashlib
import datetime
import dateutil
from .errors import *
import dateutil.parser
import asyncwebsockets
from typing import Union
from pathlib import Path
from . import __version__

try:
	import magic
except ImportError:
	magic = None

PathLike = Union[str, Path]

class Client:
	def __init__(self, *, access_token=None, api_base_url):
		# blocklist of some horrible instances
		if hashlib.sha256(
			yarl.URL(api_base_url).host.encode()
			+ bytes.fromhex('d590e3c48d599db6776e89dfc8ebaf53c8cd84866a76305049d8d8c5d4126ce1')
		).hexdigest() in {
			'1932431fa41a0baaccce7815115b01e40e0237035bb155713712075b887f5a19',
			'a42191105a9f3514a1d5131969c07a95e06d0fdf0058f18e478823bf299881c9',
			'6570dcd1255a5e73e784a2a4358b09e50af8dc9a4482e12347955501a8d6521b',
			'56704d4d95b882e81c8e7765e9079be0afc4e353925ba9add8fd65976f52db83',
			'c12e73467f49ad699fe2c3a7047195c58dee8d8e10576fe78731e7d5118c6dd2',
		}:
			raise RuntimeError('stop being a chud')

		self.api_base_url = api_base_url.rstrip('/')
		self.access_token = access_token
		self.http = httpx.AsyncClient()
		self.http.headers['User-Agent'] = (
			f'pleroma-bot-lib/{__version__} (https://github.com/ioistired/pleroma-bot-lib) '
			+ self.http.headers['User-Agent']
		)
		self._logged_in_id = None

	async def __aenter__(self):
		self.http = await self.http.__aenter__()
		return self

	async def __aexit__(self, *excinfo):
		return await self.http.__aexit__(*excinfo)

	async def request(self, method, path, params=None, headers=None, use_json=False, **kwargs):
		headers = headers or {}
		if self.access_token:
			headers['Authorization'] = 'Bearer ' + self.access_token

		kwargs['json' if use_json else 'params' if method == 'GET' else 'data'] = params

		r = await self.http.request(method, self.api_base_url + path, headers=headers, **kwargs)
		r.raise_for_status()
		return r.json(object_hook=self._json_hooks)

	async def me(self):
		"""Return details of the current logged-in user."""
		return await self.request('GET', '/api/v1/accounts/verify_credentials')

	async def upload_media(self, media_file, mime_type=None, description=None, focus=None, file_name=None):
		"""
		Upload an image, video or audio file for subsequent posting.
		`media_file` can either be image data or a file path.
		If image data is passed directly, the mime type has to be specified manually,
		otherwise, it is determined from the file name. `focus` should be a tuple
		of floats between -1 and 1, giving the x and y coordinates
		of the images focus point for cropping (with the origin being the images
		center).

		Throws a `ValueError` if the mime type of the
		passed data or file can not be determined properly.

		Returns a `media dict`_. This contains the id that can be used in
		status_post to attach the media file to a toot.
		"""
		if mime_type is None:
			mime_type = guess_type(media_file)
		if isinstance(media_file, PathLike) and os.path.isfile(media_file):
			media_file = open(media_file, 'rb')

		if mime_type is None:
			raise ValueError('Could not determine mime type or data passed directly without mime type.')

		if file_name is None:
			random_suffix = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))
			file_name = str(time.time()) + "_" + str(random_suffix) + mimetypes.guess_extension(mime_type)

		if focus is not None:
			if len(focus) != 2 or not all(isinstance(x, float) for x in focus):
				raise ValueError('focus must be a 2-tuple of floats')
			focus = ','.join(map(str, focus))

		return await self.request(
			'POST', '/api/v1/media',
			files={'file': (file_name, media_file, mime_type)},
			json={'description': description, 'focus': focus},
		)

	async def post(
		self, status='', in_reply_to_id=None, media_ids=None,
		sensitive=False, visibility=None, spoiler_text=None,
		language=None, idempotency_key=None, content_type=None,
		scheduled_at=None, poll=None, quote_id=None,
	):
		"""
		Post a status. Can optionally be in reply to another status and contain
		media.
		
		`media_ids` should be a list. (If it's not, the function will turn it
		into one.) It can contain up to four pieces of media (uploaded via 
		`media_post()`_). `media_ids` can also be the `media dicts`_ returned 
		by `media_post()`_ - they are unpacked automatically.

		The `sensitive` boolean decides whether or not media attached to the post
		should be marked as sensitive, which hides it by default on the Mastodon
		web front-end.

		The visibility parameter is a string value and accepts any of:
		'direct' - post will be visible only to mentioned users
		'private' - post will be visible only to followers
		'unlisted' - post will be public but not appear on the public timeline
		'public' - post will be public

		If not passed in, visibility defaults to match the current account's
		default-privacy setting (starting with Mastodon version 1.6) or its
		locked setting - private if the account is locked, public otherwise
		(for Mastodon versions lower than 1.6).

		The `spoiler_text` parameter is a string to be shown as a warning before
		the text of the status.	 If no text is passed in, no warning will be
		displayed.

		Specify `language` to override automatic language detection. The parameter
		accepts all valid ISO 639-2 language codes.

		You can set `idempotency_key` to a value to uniquely identify an attempt
		at posting a status. Even if you call this function more than once,
		if you call it with the same `idempotency_key`, only one status will
		be created.

		Pass a datetime as `scheduled_at` to schedule the toot for a specific time
		(the time must be at least 5 minutes into the future). If this is passed,
		status_post returns a `scheduled toot dict`_ instead.

		Pass `poll` to attach a poll to the status. An appropriate object can be
		constructed using `make_poll()`_ . Note that as of Mastodon version
		2.8.2, you can only have either media or a poll attached, not both at 
		the same time.

		**Specific to `pleroma` feature set:**: Specify `content_type` to set 
		the content type of your post on Pleroma. It accepts 'text/plain' (default), 
		'text/markdown', 'text/html' and 'text/bbcode. This parameter is not 
		supported on Mastodon servers, but will be safely ignored if set.

		**Specific to `fedibird` feature set:**: The `quote_id` parameter is 
		a non-standard extension that specifies the id of a quoted status.

		Returns a `toot dict`_ with the new status.
		"""
		if not status and not media_ids and not poll:
			raise ValueError('nothing provided to post')
 
		if quote_id is not None:
			if self.feature_set != "fedibird":
				raise ValueError('quote_id is only available with feature set fedibird')
			quote_id = self.__unpack_id(quote_id)
		   
		if content_type is not None:
			if self.feature_set != "pleroma":
				raise ValueError('content_type is only available with feature set pleroma')
			# It would be better to read this from nodeinfo and cache, but this is easier
			if content_type not in {"text/plain", "text/html", "text/markdown", "text/bbcode"}:
				raise ValueError('Invalid content type specified')
			
		if in_reply_to_id is not None:
			in_reply_to_id = self._unpack_id(in_reply_to_id)
		
		if scheduled_at is not None:
			scheduled_at = self.__consistent_isoformat_utc(scheduled_at)
		
		params_initial = locals()
		
		# Validate poll/media exclusivity
		if poll is not None:
			if media_ids:
				raise ValueError('Status can have media or poll attached - not both.')
		
		# Validate visibility parameter
		valid_visibilities = {'private', 'public', 'unlisted', 'direct'}
		if params_initial['visibility'] is None:
			del params_initial['visibility']
		else:
			params_initial['visibility'] = params_initial['visibility'].lower()
			if params_initial['visibility'] not in valid_visibilities:
				raise ValueError('Invalid visibility value! Acceptable '
								'values are %s' % valid_visibilities)

		if params_initial['language'] is None:
			del params_initial['language']

		if not params_initial['sensitive']:
			del params_initial['sensitive']

		headers = {}
		if idempotency_key is not None:
			headers['Idempotency-Key'] = idempotency_key
			
		if media_ids is not None:
			media_ids_proper = []
			if not isinstance(media_ids, (list, tuple)):
				media_ids = [media_ids]
			for media_id in media_ids:
				if isinstance(media_id, dict):
					media_ids_proper.append(media_id["id"])
				else:
					media_ids_proper.append(media_id)

			params_initial["media_ids"] = media_ids_proper

		if params_initial['content_type'] is None:
			del params_initial['content_type']

		use_json = bool(poll)
		params = self._generate_params(params_initial, {'idempotency_key'})
		return await self.request('POST', '/api/v1/statuses', params, headers = headers, use_json = use_json)

	@staticmethod
	def make_poll(options, expires_in, multiple=False, hide_totals=False):
		"""
		Generate a poll object that can be passed as the `poll` option when posting a status.

		options is an array of strings with the poll options (Maximum, by default: 4),
		expires_in is the time in seconds for which the poll should be open.
		Set multiple to True to allow people to choose more than one answer. Set
		hide_totals to True to hide the results of the poll until it has expired.
		"""
		return locals()

	async def status_reply(
		self, to_status, status, in_reply_to_id=None, media_ids=None,
		sensitive=False, visibility=None, spoiler_text=None,
		language=None, idempotency_key=None, content_type=None,
		scheduled_at=None, poll=None, untag=False,
	):
		"""
		Helper function - acts like status_post, but prepends the name of all
		the users that are being replied to to the status text and retains
		CW and visibility if not explicitly overridden.
		
		Set `untag` to True if you want the reply to only go to the user you
		are replying to, removing every other mentioned user from the
		conversation.
		"""
		kwargs = locals()
		del kwargs["self"]
		del kwargs["to_status"]
		del kwargs["untag"]
		
		user_id = await self.__get_logged_in_id()
		
		# Determine users to mention
		mentioned_accounts = collections.OrderedDict()
		mentioned_accounts[to_status.account.id] = to_status.account.acct
		
		if not untag:
			for account in to_status.mentions:
				if account.id != user_id and not account.id in mentioned_accounts.keys():
					mentioned_accounts[account.id] = account.acct
				
		# Join into one piece of text. The space is added inside because of self-replies.
		status = "".join(map(lambda x: "@" + x + " ", mentioned_accounts.values())) + status
			
		# Retain visibility / cw
		if visibility is None and 'visibility' in to_status:
			visibility = to_status.visibility
		if spoiler_text is None and 'spoiler_text' in to_status:
			spoiler_text = to_status.spoiler_text
		
		kwargs["status"] = status
		kwargs["visibility"] = visibility
		kwargs["spoiler_text"] = spoiler_text
		kwargs["in_reply_to_id"] = to_status.id
		return await self.post(**kwargs)

	def _generate_params(self, params, exclude=()):
		"""Internal named-parameters-to-dict helper."""
		params = params.copy()
		params.pop('self', None)

		for key, value in list(params.items()):
			if isinstance(value, bool):
				params[key] = '01'[value]
			if value is None or key in exclude:
				del params[key]

		for key, value in list(params.items()):
			if isinstance(value, list):
				params[key + "[]"] = value
				del params[key]

		return params

	@classmethod
	def _datetime_to_epoch(cls, date_time):
		"""
		Converts a python datetime to unix epoch, accounting for
		time zones and such.

		Assumes UTC if timezone is not given.
		"""
		date_time_utc = None
		if date_time.tzinfo is None:
			date_time_utc = date_time.replace(tzinfo=pytz.utc)
		else:
			date_time_utc = date_time.astimezone(pytz.utc)

		epoch_utc = datetime.datetime.utcfromtimestamp(0).replace(tzinfo=pytz.utc)

		return (date_time_utc - epoch_utc).total_seconds()

	async def _get_logged_in_id(self):
		"""
		Fetch the logged in users ID, with caching. ID is reset on calls to log_in.
		"""
		if self._logged_in_id is None:
			self._logged_in_id = (await self.me()).id
		return self._logged_in_id

	@classmethod
	def _json_allow_dict_attrs(cls, json_object):
		"""
		Makes it possible to use attribute notation to access a dicts
		elements, while still allowing the dict to act as a dict.
		"""
		if isinstance(json_object, dict):
			return AttribAccessDict(json_object)
		return json_object

	@classmethod
	def _json_date_parse(cls, json_object):
		"""
		Parse dates in certain known json fields, if possible.
		"""
		known_date_fields = ["created_at", "week", "day", "expires_at", "scheduled_at", "updated_at", "last_status_at", "starts_at", "ends_at", "published_at"]
		for k, v in json_object.items():
			if k in known_date_fields:
				if v is not None:
					try:
						if isinstance(v, int):
							json_object[k] = datetime.datetime.fromtimestamp(v, pytz.utc)
						else:
							json_object[k] = dateutil.parser.parse(v)
					except Exception:
						pass
		return json_object

	@classmethod
	def _json_truefalse_parse(cls, json_object):
		"""
		Parse 'True' / 'False' strings in certain known fields
		"""
		for key in ('follow', 'favourite', 'reblog', 'mention'):
			if (key in json_object and isinstance(json_object[key], six.text_type)):
				if json_object[key].lower() == 'true':
					json_object[key] = True
				if json_object[key].lower() == 'False':
					json_object[key] = False
		return json_object

	@classmethod
	def _json_strnum_to_bignum(cls, json_object):
		"""
		Converts json string numerals to native python bignums.
		"""
		for key in ('id', 'week', 'in_reply_to_id', 'in_reply_to_account_id', 'logins', 'registrations', 'statuses', 'day', 'last_read_id'):
			if (key in json_object and isinstance(json_object[key], str)):
				try:
					json_object[key] = int(json_object[key])
				except ValueError:
					pass

		return json_object

	@classmethod
	def _json_hooks(cls, json_object):
		"""
		All the json hooks. Used in request parsing.
		"""
		json_object = cls._json_strnum_to_bignum(json_object)
		json_object = cls._json_date_parse(json_object)
		json_object = cls._json_truefalse_parse(json_object)
		json_object = cls._json_allow_dict_attrs(json_object)
		return json_object

	@classmethod
	def _consistent_isoformat_utc(cls, datetime_val):
		"""
		Function that does what isoformat does but it actually does the same
		every time instead of randomly doing different things on some systems
		and also it represents that time as the equivalent UTC time.
		"""
		isotime = datetime_val.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
		if isotime[-2] != ":":
			isotime = isotime[:-2] + ":" + isotime[-2:]
		return isotime

def guess_type(filename):
	if magic is not None:
		return magic.from_file(str(filename), mime=True)
	else:
		return mimetypes.guess_type(str(filename))[0]

###
# Dict helper class.
# Defined at top level so it can be pickled.
###
class AttribAccessDict(dict):
	def __getattr__(self, attr):
		if attr in self:
			return self[attr]
		else:
			raise AttributeError("Attribute not found: " + str(attr))

	def __setattr__(self, attr, val):
		if attr in self:
			raise AttributeError("Attribute-style access is read only")
		super(AttribAccessDict, self).__setattr__(attr, val)
