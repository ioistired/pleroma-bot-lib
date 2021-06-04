import re
import time
import inspect
import mastodon
import traceback
import contextlib
from .errors import *
from .view import StringView
from bs4 import BeautifulSoup
from .utils import sanitize_mentions

class Command:
	def __init__(self, func):
		self.name = func.__name__.replace('_', '-')
		if func.__doc__:
			self.short_help = func.__doc__.partition('\n')[0]
		else:
			self.short_help = None
		self._callback = func

	@property
	def callback(self):
		return self._callback

	@property
	def __doc__(self):
		return self.callback.__doc__

	def __call__(self, *args, **kwargs):
		return self.callback(*args, **kwargs)

class PleromaBot:
	def __init__(self, pleroma: mastodon.Mastodon, *, about=''):
		self.pleroma = pleroma
		self.me = self.pleroma.me()
		self.about = about
		self.commands = {}
		self.command(self.help)

	def command(self, func):
		command = Command(func)
		self.commands[command.name] = command
		return command

	def prepare_docs(self, docs):
		docs = docs.format(username=self.me['acct'])
		docs = inspect.cleandoc(docs)
		return sanitize_mentions(docs)

	def help(self, notif, command_name=None, /, *_):
		"""Shows this message. Pass the name of a command for more info."""
		if command_name:
			try:
				docs = self.commands[command_name].__doc__
			except KeyError:
				return self.reply(notif, f'Command {command_name} not found.')

			if not docs:
				return self.reply(notif, f'{command_name}: no help given.')

			self.reply(notif, self.prepare_docs(docs))
		else:
			topics = []
			for command in self.commands.values():
				if command.short_help:
					topics.append(f'• {command.name} — {command.short_help}')
				else:
					topics.append(f'• {command.name}')

			self.reply(
				notif,
				self.about
				+ '\nAvailable commands/help topics:\n\n'
				+ '\n'.join(topics)
			)

	def get_image(self, status):
		"""Get the first image referred to in the thread or attached in the status."""
		return self.get_media(status, 'image')

	def get_video(self, status):
		"""Get the first video referred to in the thread or attached in the status."""
		return self.get_media(status, 'video')

	def get_media(self, status, type):
		def get_attach(status):
			attachments = status['media_attachments']
			for attach in attachments:
				if attach['type'] == type:
					return attach

		return (
			get_attach(status)
			or next(filter(None, map(get_attach, self.pleroma.status_context(status['id'])['ancestors'])), None)
		)

	@classmethod
	def _html_to_plain(cls, content):
		soup = BeautifulSoup(content, 'html.parser')
		for br in soup.find_all('br'):
			br.replace_with('\n')
		return soup.text

	def _parse_args(self, content):
		"""'@a @b @bot @c ping pong' -> ['ping', 'pong']

		'@a @b @c foo bar
		@bot quux garply'
		-> ['quux', 'garply']
		"""
		command_content = []
		in_mentions_block = False
		has_me = False
		view = StringView(self._html_to_plain(content))
		while not view.eof:
			view.skip_ws()
			word = view.get_word()
			# only match the first block of mentions that pings us
			if command_content and not in_mentions_block and word.startswith('@'):
				break
			if word == '@' + self.me['acct']:
				has_me = True
				in_mentions_block = True
			elif word.startswith('@') and not in_mentions_block:
				in_mentions_block = True
				has_me = False
			if not word.startswith('@'):
				in_mentions_block = False
			if has_me and not in_mentions_block:
				view.undo()
				command_content.append(view.get_quoted_word())

		return command_content

	def dispatch(self, notif):
		try:
			command_name, *command_args = self._parse_args(notif['status']['content'])
		except ValueError:
			return
		except ArgumentParsingError as exc:
			return self.reply(notif, str(exc))

		try:
			handler = self.commands[command_name]
		except KeyError:
			return

		try:
			return handler(notif, *command_args)
		except Exception:
			print('Unhandled exception in', command_name + ':')
			traceback.print_exc()

	def run(self, poll_interval=1.0):
		print('Logged in as:', '@' + self.me['acct'])
		with contextlib.suppress(KeyboardInterrupt):
			self._run(poll_interval)

	def _run(self, poll_interval):
		while True:
			notifs = self.pleroma.notifications(mentions_only=True)
			for notif in notifs:
				self.dispatch(notif)
			if notifs:
				self.pleroma.notifications_clear()

			time.sleep(poll_interval)
