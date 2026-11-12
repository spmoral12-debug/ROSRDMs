"""Roll original Supply reward trees independently of wallet and inventory I/O."""

import json
import time
from pathlib import Path
from random import choices


def _pick(entries, item_key, weight_key, choose):
    weighted = [(entry[item_key], entry[weight_key]) for entry in entries
                if entry.get(weight_key, 0) > 0]
    if not weighted:
        raise ValueError('Supply reward package has no positive weights')
    items, weights = zip(*weighted)
    return choose(items, weights=weights, k=1)[0]


def _expand(item, packages, choose, visited, ancestry=frozenset()):
    if item in ancestry:
        raise ValueError(f'Circular Supply reward package {item}')
    row = packages[str(item)]
    visited.add(item)
    if row['kind'] == 'RandomItem':
        child = _pick(row['entries'], 'item', 'weight', choose)
        return _expand(child, packages, choose, visited, ancestry | {item})
    if row['kind'] == 'GiftBag':
        return [reward for entry in row['entries']
                for reward in _expand(entry['item'], packages, choose, visited, ancestry | {item})]
    return [item]


def roll_supply(banner, packages, misses, choose=choices):
    """Return the items and next counters for one pull from one banner."""
    rules = banner.get('GUARANTEE_LIST', [])
    # Keep each rule's counter tied to its definition if the catalog is reordered.
    def rule_key(rule):
        return ':'.join(map(str, (rule['GUARANTEE_PROP_ID'], rule['PROP_GET_CNT'],
                                  rule.get('QUALITY_CONDITION', 0),
                                  *sorted(rule.get('CHECK_PROP_SET', [])))))

    due = next((rule for rule in rules
                if misses.get(rule_key(rule), 0) >= rule['PROP_GET_CNT']), None)
    if due is not None:
        root = due['GUARANTEE_PROP_ID']
    else:
        entries = banner['SUPPLEMENT_LIST']
        if len(entries) == 1 and 'PROBABILITY' not in entries[0]:
            root = entries[0]['PROP_ID']
        else:
            root = _pick(entries, 'PROP_ID', 'PROBABILITY', choose)

    visited = set()
    rewards = _expand(root, packages, choose, visited)
    quality = max((packages[str(item)].get('quality') or 0 for item in rewards), default=0)
    next_misses = {}
    for rule in rules:
        key = rule_key(rule)
        hit = (rule['GUARANTEE_PROP_ID'] in visited or
               bool(visited.intersection(rule.get('CHECK_PROP_SET', []))) or
               ('QUALITY_CONDITION' in rule and quality >= rule['QUALITY_CONDITION']))
        next_misses[key] = 0 if hit else misses.get(key, 0) + 1
    return rewards, next_misses


def install():
    from backend_server.features import supplement

    feature = supplement.SupplementFeature
    original = feature.action_open
    if getattr(original, '_original_supply_rewards', False):
        return
    path = Path(__file__).with_name('backend_server') / 'data' / 'original_supply_rewards.json'
    export = json.loads(path.read_text(encoding='utf-8'))
    banners, packages = export['banners'], export['packages']

    def action_open(self, data, params):
        sid = supplement.int_param(params, 'supplement_id')
        key = str(sid)
        banner = banners.get(key)
        if banner is None:
            return original(self, data, params)

        catalog = self.catalog()
        state = self._state(data)
        box = self._box(catalog, sid)
        multi = bool(params.get('multi', False))
        multi_times = max(1, int(box.get('multiTimes') or 10))
        times = supplement.int_param(params, 'times', multi_times if multi else 1)
        times = max(1, min(times, supplement.MAX_TIMES))
        use_free = params.get('use_free')
        cost_spec, multi_spec = self._cost_for(box, params.get('currency_id'))
        box_currency = supplement.currency_type(cost_spec.get('currency', 'gp'))
        free = not multi and times == 1 and use_free is not False and self._free_ready_in(state, box, key) == 0
        if use_free and not free:
            raise supplement.SupplementError('free_not_ready', 'The free open is not ready yet.', box_currency, 0)

        # Resolve the complete batch before charging or granting anything.
        pity = state.setdefault('originalSupplyPity', {})
        misses = pity.get(key, {})
        items = []
        for _ in range(times):
            rolled, misses = roll_supply(banner, packages, misses)
            items.extend(rolled)

        touched = {}
        if free:
            cost = {'currency': cost_spec.get('currency', 'gp'), 'amount': 0}
            type_id = box_currency
            used = self._free_used_today(state, key)
            state['lastFree'][key] = self.now()
            state['freeUsed'][key] = used + 1
            state['freeDay'][key] = self._today()
        else:
            price = multi_spec if multi and times == multi_times and multi_spec else cost_spec
            amount = int(price.get('amount', 0))
            if price is cost_spec:
                amount *= times
            cost = {'currency': price.get('currency', cost_spec.get('currency', 'gp')), 'amount': amount}
            type_id = self._charge(data, state, cost['currency'], amount, f'supplement:{sid}')
            if type_id not in supplement.WALLET_TYPES and amount > 0:
                touched[type_id] = int(state['currencies'].get(str(type_id), 0))

        rewards = []
        for item in items:
            self.account.add_item(data, item, 1, 0)
            rewards.append({'item': item, 'count': 1, 'days': 0})
        pity[key] = misses
        state['opened'][key] = int(state['opened'].get(key, 0)) + times
        state['totalOpened'] += times
        if multi:
            state['multipleOpenTimes'][key] = int(state['multipleOpenTimes'].get(key, 0)) + 1
        state['accumulateBuy'][key] = int(state['accumulateBuy'].get(key, 0)) + times
        if time.localtime(self.now()).tm_wday >= 5:
            state['weekendBuy'][key] = int(state['weekendBuy'].get(key, 0)) + times
        state['recent'] = (list(reversed(items)) + list(state['recent']))[:supplement.RECENT_LIMIT]
        self.account.record(data, 'supplement', supplement=sid, times=times, free=free,
                            multi=multi, cost=cost, items=items)
        return {'supplement_id': sid, 'times': times, 'free': free, 'appearance_ids': items,
                'rewards': rewards, 'cost': cost, 'currency_type': int(type_id or 0),
                'wallet': dict(data['wallet']), 'currencies': touched,
                'props': self._props(data, state, catalog)}

    action_open._original_supply_rewards = True
    feature.action_open = action_open
