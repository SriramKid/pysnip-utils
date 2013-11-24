"""
List all players in a server, including their ip, rights and id.

Copyright (c) 2013 learn_more
See the file license.txt or http://opensource.org/licenses/MIT for copying permission.
"""

from commands import add, admin

@admin
def players(connection):
	fmt = '#%-2s  %-20s %s%s\n'
	protocol = connection.protocol
	message = fmt % ('id', 'Name', 'ip', ' (rights)')
	for player in protocol.players.values():
		usrt = ', '.join(player.user_types)
		if len(usrt):
			usrt = ' (' + usrt + ')'
		message += fmt % (player.player_id, player.name, player.address[0], usrt)
	return message

def apply_script(protocol, connection, config):
	return protocol, connection

add(players)
