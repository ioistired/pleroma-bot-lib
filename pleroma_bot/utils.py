import re

# matches @ not preceded by /
# this allows linking to toots in help messages
NON_LINK_AT_SIGN = re.compile('(?<!/)@')

def sanitize_mentions(content):
	return NON_LINK_AT_SIGN.sub('@\N{zero width space}', content)
