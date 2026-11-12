"""Check all configured Manual level rewards against a temporary account database."""

from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend_server.account import Account
from backend_server.database import Database
from backend_server.features.manual import ManualFeature
import profile_controls  # Apply the same account and Manual hooks as the server.


def audit():
    with TemporaryDirectory() as folder:
        db = Database(Path(folder) / 'manual-audit.db')
        try:
            user = db.create_account('manual-audit')
            character = db.ensure_character(user['id'], 10501)
            account = Account(db, character['gid'])
            manual = ManualFeature(account)
            awards = {award for row in manual.level_awards() for award in row if award}
            expected = Counter()
            for award in awards:
                row = manual.award_row(award)
                assert row is not None and isinstance(row.get('props', {}), dict), award
                expected.update({int(item): count for item, count in row.get('props', {}).items()})

            with account.edit() as data:
                data['wallet']['freeYuanbao'] = 50000
                manual.action_state(data, {})
                manual.action_add_exp(data, {'exp': manual.levels()[-1]})
                manual.action_buy_premium(data, {})
                expected_data = deepcopy(data)
                currencies = manual.catalog()['currency_items']
                for item, count in expected.items():
                    if str(item) in currencies:
                        account.credit(expected_data, currencies[str(item)], count, 'manual audit')
                    else:
                        account.add_item(expected_data, item, count)
                response = manual.action_claim_all(data, {})
                assert response['ok']
                assert set(data['manual']['claimed']) == awards

            saved = account.load()
            for item in ('1110336', '1111336', '1112336'):
                assert saved['depot'][item]['count'] >= 1, item
            for field in ('wallet', 'currencies', 'depot'):
                assert saved.get(field) == expected_data.get(field), field
            assert set(saved['manual']['claimed']) == awards
            with account.edit() as data:
                manual.action_claim_all(data, {})
            after_repeat = account.load()
            for field in ('wallet', 'currencies', 'depot'):
                assert after_repeat.get(field) == saved.get(field), field
            return len(awards), len(expected)
        finally:
            db.close()


if __name__ == '__main__':
    awards, items = audit()
    print(f'Verified {awards} level rewards across {items} item and currency IDs. Repeat claim made no grants.')
