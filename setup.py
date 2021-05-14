#!/usr/bin/env python3

from setuptools import setup

with open('README.md') as f:
	long_description = f.read()

setup(
	name='pleroma-bot-lib',
	version='0.0.0',
	description='Simple call and response library for Pleroma bots',
	long_description=long_description,
	long_description_content_type='text/x-markdown; flavor=GFM',
	author='io',
	author_email='io@mintz.cc',
	url='https://github.com/ioistired/pleroma-bot-lib',
	license='EUPL-1.2',
	keywords='mastodon pleroma api microblogging activitypub bot',
	packages=['pleroma_bot'],
	install_requires=[
		'Mastodon.py @ git+https://github.com/animeavi/Mastodon.py@file_name',
	],
	python_requires='>=3.6',
	classifiers=[
		'Development Status :: 3 - Alpha',
		'Intended Audience :: Developers',
		'Topic :: Software Development :: User Interfaces',
		'Natural Language :: English',
		'Operating System :: OS Independent',
		'Programming Language :: Python :: 3 :: Only',
		'Programming Language :: Python :: 3.6',
		'Programming Language :: Python :: 3.7',
		'Programming Language :: Python :: 3.8',
		'Programming Language :: Python :: 3.9',
		'Programming Language :: Python :: 3.10',
		'License :: OSI Approved :: European Union Public Licence 1.2 (EUPL 1.2)',
	],
)
