# SPDX-License-Identifier: EUPL-1.2

import yarl
import httpx
import hashlib
import asyncwebsockets

from . import __version__

class Client:
	def __init__(self, *, access_token=None, api_base_url):
		self.api_base_url = api_base_url
		self.access_token = access_token
		self.http = httpx.AsyncClient()
		self.http.headers['User-Agent'] = (
			f'pleroma-bot-lib/{__version__} (https://github.com/ioistired/pleroma-bot-lib) '
			+ self.http.headers['User-Agent']
		)

	async def __aenter__(self):
		self.http = await self.http.__aenter__()
		return self

	async def __aexit__(self, *excinfo):
		return await self.http.__aexit__(*excinfo)

	__SALT = bytes.fromhex('d590e3c48d599db6776e89dfc8ebaf53c8cd84866a76305049d8d8c5d4126ce1')

	async def request(self, method, path, **kwargs):
		headers = kwargs.pop('headers', None) or {}
		if self.access_token:
			headers['Authorization'] = 'Bearer ' + self.access_token

		# blocklist of some horrible instances
		if hashlib.sha256(
			yarl.URL(self.api_base_url).host.encode()
			+ self.__SALT
		).hexdigest() in {
			'1932431fa41a0baaccce7815115b01e40e0237035bb155713712075b887f5a19',
			'a42191105a9f3514a1d5131969c07a95e06d0fdf0058f18e478823bf299881c9',
			'6570dcd1255a5e73e784a2a4358b09e50af8dc9a4482e12347955501a8d6521b',
			'56704d4d95b882e81c8e7765e9079be0afc4e353925ba9add8fd65976f52db83',
			'c12e73467f49ad699fe2c3a7047195c58dee8d8e10576fe78731e7d5118c6dd2',
		}:
			raise RuntimeError('stop being a chud')

		r = await self.http.request(method, self.api_base_url + path, headers=headers, **kwargs)
		r.raise_for_status()
		return r.json()

	async def me(self):
		"""Return details of the current logged-in user."""
		return await self.request('GET', '/api/v1/accounts/verify_credentials')
