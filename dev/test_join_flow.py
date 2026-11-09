import os, sys, json, socket, time
os.environ['ROS_RT_KEY'] = 'f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf'
sys.path.insert(0, r'C:\DieHardROS\runtime\app')
import rrboot
rrboot.install()

from backend_server import battle, battle_server, paths

# Check current configuration of battle
with open(paths.BATTLE_CONFIG_PATH, 'r', encoding='utf-8') as f:
    config_dict = json.load(f)
config = battle.BattleConfig.from_dict(config_dict)
print("Config bots:", config.bots)
print("Config bot_radius:", config.bot_radius)
print("Config match_players:", config.match_players)

# Let's create a Battle instance
b = battle.Battle(1, 10501, config)
print("Created battle 1. Initial bots count:", len([e for e in b.entities.values() if e.kind == battle.BOT]))

# Let's test queue_up
q = b.queue_up("test_session")
print("queue_up:", q)

# Let's test join
join_req = {
    'session': 'test_session',
    'name': 'sean',
    'gid': 10000002,
    'map': 700,
    'look': {},
    'team': 1,
    'spawn': [9577.93, -927.59, -2480.59]
}
entity = b.join(join_req['session'], join_req['name'], join_req['gid'], join_req['team'], join_req['look'])
print("Joined entity:", entity.public())
b.set_spawn(join_req['spawn'], refine=True)
print("Battle spawn:", b.spawn)
print("Battle info:", b.info())
print("Bots count after join:", len([e for e in b.entities.values() if e.kind == battle.BOT]))
bot_positions = [e.position for e in b.entities.values() if e.kind == battle.BOT]
print("First 5 bot positions:", bot_positions[:5])
