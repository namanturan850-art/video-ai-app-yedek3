"""Per-call AI cost ledger (additive table, schema 11). Estimates, not invoices.

Prices are Anthropic first-party list prices per million tokens. Cache reads
are billed at ~0.1x input, cache writes at ~1.25x input. The ledger never
stores prompts, responses or keys - only counts and the resulting estimate.
"""
from contextlib import closing
from contextvars import ContextVar
import logging
from uuid import uuid4

LOG = logging.getLogger('uvicorn.error.providers')
PRICES = {  # USD per 1M tokens: (input, output)
    'claude-opus-5-5': (4.00, 20.00), 'claude-sonnet-5-5': (2.00, 10.00), 'claude-haiku-5-5': (0.10, 0.50),
    # Possible server-side refusal-fallback models (billed at their own rates).
    'claude-opus-5': (5.00, 25.00), 'claude-opus-4-8': (5.00, 25.00), 'claude-sonnet-5': (2.00, 10.00)}
# The project the current worker thread is spending on (set by job runners).
CURRENT_PROJECT = ContextVar('ai_usage_project', default=None)
STATEMENTS = ('''CREATE TABLE IF NOT EXISTS ai_usage (
        id TEXT PRIMARY KEY, project_id TEXT, provider TEXT NOT NULL, model TEXT NOT NULL,
        purpose TEXT NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
        cache_read_tokens INTEGER NOT NULL, cache_write_tokens INTEGER NOT NULL,
        cost_usd REAL NOT NULL, created_at TEXT NOT NULL)''',
    'CREATE INDEX IF NOT EXISTS ai_usage_project ON ai_usage(project_id,created_at)')


def estimate(model, input_tokens=0, output_tokens=0, cache_read=0, cache_write=0):
    price_in, price_out = PRICES.get(model, PRICES['claude-opus-5-5'])
    return round((input_tokens * price_in + cache_read * price_in * .1 + cache_write * price_in * 1.25
                  + output_tokens * price_out) / 1_000_000, 6)


class UsageLedger:
    def __init__(self, projects):self.projects = projects

    def record(self, *, provider, model, purpose, input_tokens, output_tokens, cache_read=0, cache_write=0, project_id=None):
        from app.projects import now
        project_id = project_id if project_id is not None else CURRENT_PROJECT.get()
        cost = estimate(model, input_tokens, output_tokens, cache_read, cache_write)
        try:
            with self.projects.lock, closing(self.projects._connection()) as connection, connection:
                connection.execute('INSERT INTO ai_usage VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (uuid4().hex, project_id, provider, model, purpose[:60], int(input_tokens), int(output_tokens),
                     int(cache_read), int(cache_write), cost, now()))
        except Exception:  # A ledger failure must never fail the paid call it describes.
            LOG.warning('ai_usage operation=record category=local_storage')
        return cost

    def project_summary(self, project_id):
        with self.projects.lock, closing(self.projects._connection()) as connection:
            rows = connection.execute('SELECT purpose,model,COUNT(*),SUM(input_tokens),SUM(output_tokens),SUM(cost_usd) FROM ai_usage '
                                      'WHERE project_id=? GROUP BY purpose,model ORDER BY purpose', (project_id,)).fetchall()
        items = [{'purpose': r[0], 'model': r[1], 'calls': r[2], 'input_tokens': r[3] or 0, 'output_tokens': r[4] or 0,
                  'cost_usd': round(r[5] or 0, 4)} for r in rows]
        return {'project_id': project_id, 'total_cost_usd': round(sum(i['cost_usd'] for i in items), 4),
                'total_calls': sum(i['calls'] for i in items), 'items': items,
                'note': 'Tahmini maliyet: Anthropic liste fiyatları ve yanıtlardaki token sayılarıyla hesaplanır; fatura değildir.'}
