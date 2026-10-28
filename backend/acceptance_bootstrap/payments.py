import copy
import hashlib
import hmac
import json
import re
from urllib.parse import unquote
from .config import require

MOCK_SECRET = 'sk_test_acceptance_mock_only_never_a_provider_credential'


class MockPaystack:
    """Provider responses only; application settlement/idempotency stays in real code."""
    scenarios = {'success': 'success', 'failed': 'failed', 'pending': 'pending', 'abandoned': 'abandoned', 'wrong_amount': 'success'}

    def __init__(self):
        self.transactions = {}
        self.selected = {}

    def select(self, reference, scenario):
        require(scenario in self.scenarios and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', reference), 'Mock payment scenario rejected.')
        self.selected[reference] = scenario

    def request(self, method, path, payload=None):
        if method == 'POST' and path == '/transaction/initialize':
            require(isinstance(payload, dict), 'Mock initialization payload rejected.')
            ref, amount = payload.get('reference'), payload.get('amount')
            require(isinstance(ref, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', ref)
                    and type(amount) is int and amount > 0 and payload.get('currency') == 'NGN', 'Mock payment input rejected.')
            require(str(payload.get('email', '')).endswith('@example.test'), 'Only synthetic payment contacts are accepted.')
            stored = copy.deepcopy(payload)
            require(ref not in self.transactions or self.transactions[ref] == stored, 'Conflicting mock payment reference rejected.')
            self.transactions.setdefault(ref, stored)
            data = dict(reference=ref, access_code='acceptance_' + ref,
                        authorization_url='http://127.0.0.1/acceptance-mock-checkout/' + ref)
        else:
            require(method == 'GET' and path.startswith('/transaction/verify/'), 'Unmocked provider operation blocked.')
            ref = unquote(path.removeprefix('/transaction/verify/'))
            require(ref in self.transactions, 'Unknown mock payment reference.')
            record = self.transactions[ref]
            scenario = self.selected.get(ref, 'pending')
            data = dict(reference=ref, amount=record['amount'] + (1 if scenario == 'wrong_amount' else 0),
                        currency='NGN', domain='test', status=self.scenarios[scenario],
                        metadata=copy.deepcopy(record.get('metadata', {})), paid_at='2026-12-23T10:00:00Z')
        return dict(status=True, data=data)

    def webhook(self, reference):
        data = self.request('GET', '/transaction/verify/' + reference)['data']
        require(data['status'] == 'success', 'Successful synthetic evidence required for a charge.success webhook.')
        body = json.dumps(dict(event='charge.success', data=data), sort_keys=True, separators=(',', ':')).encode()
        return body, hmac.new(MOCK_SECRET.encode(), body, hashlib.sha512).hexdigest()
