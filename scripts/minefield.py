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

Support thread: http://buildandshoot.com/viewtopic.php?f=19&t=8089
Script location: https://github.com/learn-more/pysnip/blob/master/scripts/minefield.py
"""
#todo: reset intel in minefield
#todo: black decals on level 63

MINEFIELD_VERSION = 1.5

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
	'{player} thought those mines were toys!',
	#JoJoe's messages
	'{player} showed his team the minefield. What a hero!',
	'{player} should not use their spade to defuse mines.',
	'{player} made a huge mess in the minefield.',
	'{player} detected a mine.',
	'{player} has concluded the mine-sweeping demonstration.',
	'{player} now marks the edge of the minefield.',
	'{player} disarmed a mine by stomping on it.',
	'{player} should build a bridge across the minefield next time.',
	'{player} forgot about the minefield.',
	'Ummmm {player}, Accidentally , the minefield...',
	'{player} made soup in the minefield.',
	'Score Minefield: {mine_kills}, {player} 0, Minefield is Winning!!'
]


MINEFIELD_TIP = 'Be carefull, there are mines in this map!'
MINEFIELD_MOTD = 'Be carefull for minefields!'
MINEFIELD_HELP = 'There are mines in this map!'
DEBUG_MINEFIELD = False

class Minefield:
	def __init__(self, ext):
		self.isBorder = ext.get('border', False)
		area = ext.get('area', False)
		if area:
			self.left, self.top, self.right, self.bottom = area
		else:
			self.left = ext.get('left', 0)
			self.top = ext.get('top', 0)
			self.right = ext.get('right', 512)
			self.bottom = ext.get('bottom', 512)
		self.height = ext.get('height', 0)

	def __str__(self):
		type = 'Border' if self.isBorder else 'Inner'
		return '{type} field({left}, {top}, {right}, {bottom})'.format(type = type, left = self.left, top = self.top, right = self.right, bottom = self.bottom)

	def isValid(self):
		return self.left < self.right and self.top < self.bottom

	def check_hit(self, x, y, z):
		if z > self.height:
			if self.isBorder:
				return self.left > x or self.right < x or self.top > y or self.bottom < y
			return x >= self.left and x <= self.right and y >= self.top and y <= self.bottom
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
		if DEBUG_MINEFIELD:
			print 'Spawning nade at', position

def parseField(ext):
	m = Minefield(ext)
	if m.isValid():
		if DEBUG_MINEFIELD:
			print 'Minefield:', m
		return m
	return None

def apply_script(protocol, connection, config):
	class MineConnection(connection):
		def on_position_update(self):
			pos = self.world_object.position
			x, y, z = int(pos.x) + 0.5, int(pos.y) + 0.5, int(pos.z) + 3.5
			if self.world_object.crouch:
				z -= 1
			self.protocol.check_mine(self, x, y, z + 0.5, spawnUp = True)
			connection.on_position_update(self)

		def on_block_destroy(self, x, y, z, mode):
			if DEBUG_MINEFIELD:
				print 'Block destroyed at (', x, y, z, ')'
			if mode == DESTROY_BLOCK or mode == SPADE_DESTROY:
				pos = self.world_object.position
				xx, yy, zz = x + 0.5, y + 0.5, z + 0.5
				if collision_3d(xx, yy, zz, pos.x, pos.y, pos.z, 10):
					self.protocol.check_mine(self, xx, yy, zz)
			return connection.on_block_destroy(self, x, y, z, mode)
		
		def on_kill(self, killer, type, grenade):
			if grenade and grenade.name == 'mine':
				self.protocol.mine_kills += 1
				message = choice(KILL_MESSAGES).format(player = self.name, mine_kills = self.protocol.mine_kills)
				self.protocol.send_chat(message, global_message = True)
			connection.on_kill(self, killer, type, grenade)

	class MineProtocol(protocol):
		mines_enabled = False
		minefields = []
		minefield_version = MINEFIELD_VERSION
		def on_map_change(self, map):
			self.minefields = []
			self.mines_enabled = False
			self.mine_kills = 0
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

		def check_mine(self, connection, x, y, z, waitTime = 0.1, spawnUp = False):
			if self.mines_enabled:
				for m in self.minefields:
					if m.check_hit(x, y, z):
						if spawnUp:
							z -= 1
						callLater(waitTime, m.spawnNade, connection, x, y, z)
						break

	return MineProtocol, MineConnection
