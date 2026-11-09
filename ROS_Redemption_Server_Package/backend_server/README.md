# backend_server

The local replacement for the Rules of Survival online services.

| module | role |
| --- | --- |
| `update_server.py` | HTTP/HTTPS on 127.0.0.1:80/443: no-update manifest, server list, `{}` for the lobby's web calls (Host 127.0.0.1, no file extension); 404 for everything else |
| `servers.py` | the servers — `local_update/servers.json` → `server_list_pc.txt` (no trailing newline) |
| `game_server.py` | UDP/TCP, one port per server: login, state, saves, RPC endpoint, packet log (the `hello ros` latency probe is ignored) |
| `sessions.py` | login sessions: account + server + character |
| `database.py` | `server_data/accounts.db`: accounts, characters, wallets, data, history, chat |
| `migrate.py` | one-time import of `account.json` / `local_lobby_state.json` / `chat_history.json` |
| `pyserver.py` | answers `player.base.<rpc>()` calls (routes, handlers, replays), one per character |
| `supplement_rpc.py` | SUPPLY: `@rpc` handlers for the supply-box RPCs (uses the `supplement` feature) |
| `battle_rpc.py` | START: `getReadyForBattleGround` / cancel, answered with the battle ticket |
| `battle.py` | the battleground world: entities, bots, the round clock (no sockets) |
| `battle_server.py` | the battle host: UDP on `game port + 100`, join / input / snapshot |
| `pycodec.py` | typed values over JSON (int-keyed dicts, tuples) for the hook |
| `chat.py` | `chat` / `chatPrivate`: echo, history, `/commands` |
| `account.py` | one character's wallet, depot, manual, platoon (a database transaction per change) |
| `features/` | store, supply, supplement, topup, manual, platoon, depot actions |
| `state.py` | the state sent at login + lobby preview settings (`local_lobby_state.json`) |
| `paths.py` | every file location |
| `data/` | catalogs (prices, boxes, packs, manual rewards) and `rpc_routes.json` |

Run it alone with `python -m backend_server` (add `--no-update-server` to skip
ports 80/443, `--no-battle-server` to skip the battle hosts).

## Database

`local_update/server_data/accounts.db` (SQLite, WAL mode; open it with any
SQLite browser while the game is closed):

| table | rows |
| --- | --- |
| `accounts` | `id`, `username` (UniSDK uid), `created`, `last_login`, `last_server`, `banned`, `note` |
| `characters` | `gid` (from 10001), `account_id`, `server_id` (one row per account and server), `nickname` (unique per server among created characters), `character_type`, `created` (0/1: creation finished), `base_level`, `level`, `lobby` (JSON), `created_at`, `last_login` |
| `wallets` | `gid`, `gp`, `sp`, `freeYuanbao`, `payYuanbao` |
| `character_data` | `gid`, `data` — depot, equipped, manual, platoon, supply, topup (JSON) |
| `history` | `gid`, `time`, `kind` (grant / charge / item), `fields` (JSON) |
| `chat_messages` | `server_id`, `channel`, `time`, `gid`, `name`, `text` (200 kept per channel) |
| `platoons` | the server's platoons (the game's RosMatchTeam): `server_id`, `name` (unique per server, any case), `info` (JSON: Desc, Notice, Logo, LogoType, Check, Score, Nation, Lang), `exp`, `act`, `sign_day`, `sign_cnt`, `created` |
| `platoon_members` | `gid` (one platoon per character), `platoon_id`, `role` (0 member, 1 deputy, 2 leader), `joined`, `act`, `sign_day`; `platoon_applies` (`platoon_id`, `gid`, `created`), `platoon_events` (the journal, 100 kept per platoon), `platoon_left` (rejoin cooldown) — deleting a platoon deletes the rest (cascade) |
| `meta` | schema version, migration marker |

Features never touch SQL: `Account(db, gid).edit()` yields the character as a
dict and saves it in one transaction (rolled back if the action raises, so a
failed purchase changes nothing).

## Protocol (game hook ⇄ game_server, UDP on the chosen server's port)

| request | reply |
| --- | --- |
| `ROS_LOCAL_LOGIN_V1 {"account", "port"}` | `{"ok", "session", "state"}` or `{"ok": false, "error", "message"}` |
| `ROS_LOCAL_STATE_V1 {"session"}` | state JSON: `version`, `player`, `lobby`, `lobbyModel`, and with a session `server`, `account`, `session` |
| `ROS_LOCAL_SAVE_V1 {"session", "player": {...}}` | `ROS_LOCAL_SAVE_OK` / `ROS_LOCAL_SAVE_ERR <reason>` |
| `ROS_LOCAL_PROPS_V1 {"session"}` | `{"gp": 0, ...}` properties applied at lobby entry (wallet + supplement props + `player_props.json`) |
| `ROS_LOCAL_ITEMS_V1 {"session"}` | `{"items": [{"item", "count", "expires"}]}` - the whole depot, pushed into the game's DEPOT package at lobby entry |
| `ROS_LOCAL_RPC_V1 {"session", "method", "args", "kwargs"}` | `{"handled", "callbacks", "props", "tip", "ok", "delay"?, "items"?}` |
| `hello ros` | no reply: the server-list latency test is ignored (an answer hangs the loading screen) |

The hook logs in when the game calls `BigWorld.logOn(host, "<uid>@<channel>",
password, port, callback)`: the uid is the account, the port the server.
Requests without `session` use the newest session on the port they reach.

For an RPC reply the hook sets every `props` entry on the player (and redraws
the top bar), pushes `items` into the game's DEPOT package, calls each
`callbacks[i].method(*args)` on the player, and shows `tip` with the game's
own tip banner.

`items` is added automatically: every action runs with a fresh
`Account.recent_changes`, and whatever it added to the depot is answered as
`{"item": id, "count": n, "expires": epoch or 0}` (see
[DEPOT](../README.md#depot)).  A feature never builds it by hand.

A callback may give `"named": {"text": ..., "gid": ..., "name": ...}` instead
of `"args"`; the hook then passes each value to the callback parameter whose
name means that (see `NAMED_ALIASES` in `client/lobby_hook.py`).  Chat uses
this because `onChat`'s parameter order is not known in advance.

`ok` is false when the call was refused or failed (the reply is still
`handled: true`, so the hook never guesses a success reply).  When `delay`
(seconds) is present the hook delivers props and callbacks that much later
instead of inside the game's call (supply replies use 0.3: the game first
enters its pay-loading screen, which the reply callback closes).

## Battle protocol (battle hook ⇄ battle_server, UDP on `game port + 100`)

Online, START sends the client to a different machine: the server answers
`getReadyForBattleGround` with `transferToBattleServer(ip, port, ...)` and the
client logs on there.  Here the battle host is one more local port — 19000 →
19100 — and the reply to START carries its address:

```
ROS_LOCAL_RPC_V1 {"method": "getReadyForBattleGround"}
  -> {"handled": true, "ok": true,
      "battle": {"action": "enter", "host": "127.0.0.1", "port": 19100,
                 "map": 1001, "tick_rate": 15.0, "matching_seconds": 6.0,
                 "match_seconds": 900.0, "bots": 8}}
```

`client/battle_hook.py` plays the matching screen from that ticket and then
speaks to the battle host directly:

| request | reply |
| --- | --- |
| `ROS_BATTLE_JOIN_V1 {"session", "name", "gid", "map"}` | `{"ok", "you": {entity}, "match": {"map", "spawn", "tick_rate", "bots", ...}}` |
| `ROS_BATTLE_INPUT_V1 {"id", "pos": [x,y,z], "yaw", "seq", "state"}` | a snapshot: `{"tick", "time", "remaining", "finished", "you", "entities": [...], "removed": [...]}` |
| `ROS_BATTLE_LEAVE_V1 {"session"}` | `{"ok"}` |
| `ROS_BATTLE_INFO_V1` | `{"ok", "running", "match", "config"}` — for the command line, no game needed |

One input packet, one snapshot back: that is the whole replication loop, ten
times a second.  Snapshots are absolute (no deltas) and nothing is resent, so
a lost packet costs one frame and the client recovers by itself; an input that
arrives out of order is dropped by its `seq`.

The server owns everything except the player's own body: the client has the
terrain, the collision and the physics, so it sends where it moved and the
server takes it (a step over 60 m is still taken, but logged).  Bots are the
server's alone — they walk between random points so replication can be seen
moving.  A round lasts `match_seconds`; an empty finished round is replaced by
a fresh one on the next START.

Each entity in a snapshot is
`{"id", "kind": "player"|"bot", "name", "team", "pos", "yaw", "hp", "alive",
"state"}`.  A client never sees itself in `entities` (its own `id` is in
`you`).

Settings live in `data/battle.json`: `map_id`, `bots`, `tick_rate`,
`matching_seconds`, `match_seconds`, `spawn`, `spawn_radius`, `bot_radius`,
`bot_speed`.  `map_id` is only the fallback — the hook prefers the map the
lobby itself picked (`player.matchingMapID`).

### Typed values (`pycodec.py`)

JSON has no int dict keys and no tuples, but the game looks supplement dicts up
by int id.  Such values travel as marker objects that the hook turns back into
Python values:

```json
{"__py__": "intdict", "items": [[30001, {}], [2, 5]]}     -> {30001: {}, 2: 5}
{"__py__": "tuple",   "items": [1, 2]}                     -> (1, 2)
```

`encode(value)` makes them automatically (any dict with a non-string key, any
tuple; sets become lists; unknown objects their `repr`), `int_dict(mapping)`
turns JSON-loaded `{"30001": ...}` keys into ints first, `decode` is the
inverse.  Every RPC reply and the lobby props pass through `encode`, so a reply
is always JSON-safe; dicts with string keys are sent unchanged.  Markers can
also be written literally in `rpc_routes.json`.

Store queries are answered inside the game (client/lobby_hook.py,
"Client-data replies") because the goods tables live in the client.

## Bound game calls

`data/rpc_routes.json` currently binds: `buyMallGood`,
`buyMallGoodInAppearanceMall`,
`requestRealNameAuthenCheckBeforeRequsetingPayGoods` (top-up: refused while `topup_packs.json` "enabled" is false, else credits locally),
`queryPayExtDayFirstFlags`, `getMyRosMatchTeamInfo`,
`getAthleteRosMatchTeamBriefData`, `createRosMatchTeam`,
`distributeRKUBraveBookExp`, and quietly acknowledges the calls the lobby makes
on entry.  Bookkeeping calls (analytics, logs, red badges: `saLog…`, `report…`,
`upload…`, `clean…`, `…RedBadge`…) are acknowledged silently by `pyserver.py`
without a route.  Reply formats come from the parameter names captured in
`local_update/logs/rpc_catalog.json` → `callbacks`.

## How an RPC is answered

1. `data/rpc_routes.json` — bound to a feature action (below).
2. `@rpc("name")` Python handlers in `pyserver.py` and `supplement_rpc.py`.
   A handler returns a list of callbacks or a dict
   `{"callbacks": [...], "props": {...}, "tip": "...", "ok": bool, "delay": 0.3}`
   (`props` are merged over the wallet).  If it raises, the reply is
   `handled: true, ok: false` with the error as `tip`.
3. `local_update/server_data/rpc_responses.json` — fixed replies, e.g. captured
   from the online game: `{"reqX": [{"method": "onX", "args": [1, "a"]}]}`.
4. Bookkeeping calls (analytics, red badges) — acknowledged silently, no reply.
5. Unknown → `local_update/server_data/unknown_rpcs.json` (count, last args,
   guessed feature).

Each logged-in character has its own PyServer, so routes and handlers always
act on the character of the session that made the call.

## Features and actions

| feature | actions | data file |
| --- | --- | --- |
| store | `list`, `buy(goods_id, count)` | `store_catalog.json` |
| supply | `list`, `open(box_id, times)` — old test boxes, no RPC bound any more | `supply_boxes.json` |
| supplement | `list`, `query`, `open(supplement_id, times, multi, use_free)`, `props` — the game's supply boxes | `supplement_catalog.py` / `supplement_boxes.json` |
| topup | `list`, `buy(pack_id)`, `props` — OFF unless `"enabled": true` (the one switch): every pay button shows `disabledTip`, nothing credited; on, free local credit. `props` sends `rlTopUpEnabled` once at lobby entry. Chat `/topup <n>` always works | `topup_packs.json` |
| manual | `state` (rlManualState), `sync`, `match`, `event`, `complete_task`, `get_award`, `claim_all`, `keep_season`, `add_exp(exp)`, `buy_premium(task?)`, `claim(level?)`, `status` | `manual.json` (Brave Book 2, activity 100008) |
| platoon | `status`, `create(name, currency?, desc?, check?)`, `leave`, `props` (the platoon button's red dot). The game's RosMatchTeam calls are answered by `PlatoonServer.CALLS` (features/platoon.py): create / name check (diamonds 200 or star diamonds 3000), list / search / detail, apply (review on) or join at once (review off), accept / reject / clear / kick / promote / demote / hand over the lead, quit (lead passes on, last one disbands), members, applies, journal, settings, emblem, daily sign-in, rank tab (rank type 1200), Meet card; `rlPlatoon` pushes to the other members | `platoon.json` |
| depot | `list`, `equip(item_id, slot)`, `unequip(slot)`, `use`, `discard` | — |

Rewards everywhere use `{"currency": "gp", "amount": 100}` or
`{"item": <game item id>, "count": 1, "days": 0}`.  Currencies are the game's
property names: `gp`, `sp`, `freeYuanbao`, `payYuanbao`; prices may also use
`diamond` (free diamonds first).

A route's action result may contain `"props"`: they are merged (encoded) over
the wallet props of the reply.  A route may also set `"delay"`.

Try any action without the game: `tools/account_admin.py action supplement.open supplement_id=1`
(add `--account NAME --server NAME` to pick the character).

## Supply (supplement boxes)

Handled by `supplement_rpc.py` (a route with the same name would win, so the
supply RPCs have no route).  Every reply has `"delay": 0.3`; int-keyed dicts
are `intdict` markers.

| game call | reply callbacks |
| --- | --- |
| `queryAvailableSupplement()` | `onQueryAvailableSupplement({sid: {...}})` (+ supplement props) |
| `setIsUsePreciousTicketDiscount(flag)` | none; the flag is used by the next open |
| `openSupplyBox(sid, ...)` | `onOpenSupplyBox(sid, [propIds], False)` |
| `openMultipleSupplyBox(sid[, n], ...)` | `onMultiOpenSupplyBox(sid, [propIds])` + `onUpdateMultipleOpenTimes` |
| `openFreeSupplyBox(sid, ...)` (name guessed) | `onOpenFreeSupplyBox(sid, [propIds])` |
| failures | `onOpenSupplyBoxFailed` / `onMultiOpenSupplyBoxFailed(sid, tip[, currencyType, price])` (currency + price only for a real shortfall, price > 0) |
| `checkOpenSupplyTimes()`, `getBlackFridayNextSupplementDiscountTs()` | none |
| `queryAvailableOpenSupplyGift(ui)` | `onQueryAvailableOpenSupplyGift({}, {}, {}, {}, {}, {}, 0, 0)` |
| `query2018BlackFridayDiscount()` | `onQuery2018BlackFridayDiscount(0)` |

`onQueryAvailableSupplement` entries hold only plain scalar fields (no nested
client-table records) and are all sent as `{}` when they would not fit one UDP
reply.  A currency reward shows its display item id (`displayItem`, else
200001 gp / 201001 diamond) in the result list; it is not added to the depot.

After a successful open also: `onCurrencyUpdated(id, balance, 0)` for gp (1),
sp (3) and every non-wallet currency the open charged or granted (POINT...), `onYBUpdated(free, pay, 0)` when diamonds
changed, `onUpdateFreeLotteryTimeStampDict(stamps, times)` when the free open
was used, `onUpdateBuySupplementCntDict(weekend, accumulate, received)`, and the
supplement props (`freeLotteryTimesDict`, `supplementFreeLotteryTimeStampDict`,
`multipleOpenTimes`, `weekendBuySupplementCntDict`,
`accumulateBuySupplementCntDict`, `weekendAwardReceivedRecord`,
`hasAlreadyShowSupplyID`), which are also sent at lobby entry.

The open RPCs' argument lists are not known yet: every call to these RPCs is
recorded in `local_update/server_data/supplement_args.json` (count, last
args).  Arg 0 is the supplement id; a second int in 2..10 of
`openMultipleSupplyBox` is taken as the count, otherwise the box's
`multiTimes` is used.

## Binding a button

The game's scripts are encrypted, so the RPC names and argument order behind a
lobby button are learned at runtime:

1. Start the game, open the lobby, click the button (e.g. STORE), try the
   action inside it (buy something), close the game.
2. Run `tools/rpc_report.py --catalog`.  It lists the unanswered calls grouped
   by feature, what the discovery pass found for each lobby button/panel, and
   prints route stubs.
3. Paste the stub into `data/rpc_routes.json`, name the params, and add the
   reply callback the online server would send.  Client callbacks are the
   player's `on...` methods; `local_update/logs/rpc_catalog.json` and
   `rpc_owners` show which player method made the call, which usually names
   its reply.

```json
"routes": {
  "buyMallGoods": {
    "action": "store.buy",
    "params": ["goods_id", "count"],
    "reply": [{"method": "onBuyMallGoodsResult", "args": ["$ok", "$goods_id", "$count"]}],
    "error_reply": [{"method": "onBuyMallGoodsResult", "args": ["$ok", "$goods_id", 0]}],
    "tip": "Purchase complete."
  }
}
```

Tips may use `{name}` placeholders from the result (`"Added {diamonds}"`).
`$name` in reply args reads the action result (`$wallet.gp`, `$rewards`),
`$ok` / `$code` / `$message` describe success, `$argN` is the Nth original
argument; anything else is literal.  Routes are re-read on every call, so edits
apply without restarting.
