"""
Minefield map extension.
Copyright (c) 2013 learn_more
See the file license.txt or http://opensource.org/licenses/MIT for copying permission.

Allows mappers to specify the map bounds, outside of which players will trip mines.
Breaking blocks (when standing close to the field) also triggers a mine.

example extension from mapname.txt:

extensions = {
	'minefields' : [
		{
			'border' : 1,
			'left' : 59,
			'top' : 154,
			'right' : 451,
			'bottom' : 355,
		}
	]
}
"""

MINEFIELD_VERSION = 1.0

from pyspades.world import Grenade
from pyspades.server import grenade_packet
from pyspades.common import Vertex3
from pyspades.collision import collision_3d
from pyspades.constants import DESTROY_BLOCK, SPADE_DESTROY
from twisted.internet.reactor import callLater
from random import choice

KILL_MESSAGES = [
	'{player} wandered into a minefield',
	'{player} should not walk into a minefield',
	'{player} was not carefull enough in the minefield',
	'{player} thought those mines were toys!'
]
MINEFIELD_TIP = 'Be carefull, there are mines in this map!'
MINEFIELD_MOTD = 'Be carefull for minefields!'
MINEFIELD_HELP = 'There are mines in this map!'

class Minefield:
	def __init__(self, ext):
		self.isBorder = ext.get('border', False)
		self.left = ext.get('left', 0)
		self.top = ext.get('top', 0)
		self.right = ext.get('right', 512)
		self.bottom = ext.get('bottom', 512)

	def isValid(self):
		if self.isBorder:
			return self.left < self.right and self.top < self.bottom
		return False

	def check_hit(self, x, y, z):
		if self.isBorder:
			return self.left > x or self.right < x or self.top > y or self.bottom < y
		return False

	def spawnNade(self, connection, x, y, z):
		protocol = connection.protocol
		fuse = 0.1
		position = Vertex3(x, y, z)
		orientation = None
		velocity = Vertex3(0, 0, 0)
		grenade = protocol.world.create_object(Grenade, fuse, position, orientation, velocity, connection.grenade_exploded)
		grenade.name = 'mine'
		grenade_packet.value = grenade.fuse
		grenade_packet.player_id = 32
		grenade_packet.position = position.get()
		grenade_packet.velocity = velocity.get()
		protocol.send_contained(grenade_packet)

def parseField(ext):
	m = Minefield(ext)
	if m.isValid():
		return m
	return None

def apply_script(protocol, connection, config):
	class MineConnection(connection):
		def on_position_update(self):
			pos = self.world_object.position
			x, y, z = int(pos.x) + 0.5, int(pos.y) + 0.5, int(pos.z) + 0.5
			z = self.protocol.map.get_z(x, y, z)
			self.protocol.check_mine(self, x, y, z)
			connection.on_position_update(self)

		def on_block_destroy(self, x, y, z, mode):
			if mode == DESTROY_BLOCK or mode == SPADE_DESTROY:
				pos = self.world_object.position
				xx, yy, zz = x + 0.5, y + 0.5, z + 0.5
				if collision_3d(xx, yy, zz, pos.x, pos.y, pos.z, 10):
					self.protocol.check_mine(self, xx, yy, zz)
			return connection.on_block_destroy(self, x, y, z, mode)
		
		def on_kill(self, killer, type, grenade):
			if grenade and grenade.name == 'mine':
				message = choice(KILL_MESSAGES).format(player = self.name)
				self.protocol.send_chat(message, global_message = True)
			connection.on_kill(self, killer, type, grenade)

	class MineProtocol(protocol):
		mines_enabled = False
		minefields = []
		minefield_version = MINEFIELD_VERSION
		def on_map_change(self, map):
			self.minefields = []
			self.mines_enabled = False
			extensions = self.map_info.extensions
			for f in extensions.get('minefields', []):
				m = parseField(f)
				if not m is None:
					self.minefields.append(m)
			self.mines_enabled = len(self.minefields) > 0
			return protocol.on_map_change(self, map)

		def addif(self, lst, entry):
			if lst is None or entry is None:
				return
			if self.mines_enabled:
				if not entry in lst:
					lst.append(entry)
			else:
				if entry in lst:
					lst.remove(entry)

		def update_format(self):
			protocol.update_format(self)
			self.addif(self.tips, MINEFIELD_TIP)
			self.addif(self.motd, MINEFIELD_MOTD)
			self.addif(self.help, MINEFIELD_HELP)

		def check_mine(self, connection, x, y, z, waitTime = 0.1):
			if self.mines_enabled:
				for m in self.minefields:
					if m.check_hit(x, y, z):
						callLater(waitTime, m.spawnNade, connection, x, y, z)
						break

	return MineProtocol, MineConnection
