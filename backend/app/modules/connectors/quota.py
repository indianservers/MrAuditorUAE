"""Atomic rolling organization budgets and leased concurrency across Celery workers."""

import uuid

from app.modules.connectors.runtime import digest
from app.modules.connectors.zoho import ConnectorError

ACQUIRE = """
local now=redis.call('TIME'); local t=tonumber(now[1])+tonumber(now[2])/1000000
redis.call('ZREMRANGEBYSCORE',KEYS[1],'-inf',t-86400)
redis.call('ZREMRANGEBYSCORE',KEYS[2],'-inf',t)
local minute=redis.call('ZCOUNT',KEYS[1],t-60,'+inf')
if minute>=tonumber(ARGV[1]) then return {0,60} end
if tonumber(ARGV[2])>0 and redis.call('ZCARD',KEYS[1])>=tonumber(ARGV[2]) then return {0,3600} end
if redis.call('ZCARD',KEYS[2])>=tonumber(ARGV[3]) then return {0,5} end
redis.call('ZADD',KEYS[1],t,ARGV[4]);redis.call('EXPIRE',KEYS[1],86460)
redis.call('ZADD',KEYS[2],t+120,ARGV[4]);redis.call('EXPIRE',KEYS[2],180)
return {1,0}
"""


class QuotaDeferred(ConnectorError):
    def __init__(self, retry_after):
        self.retry_after = retry_after
        super().__init__(f"Organization API budget exhausted; retry after {retry_after} seconds using the saved checkpoint")


class OrganizationQuota:
    def __init__(self, redis, provider, company, client_id, per_minute=60, per_day=10000, concurrency=2):
        self.redis = redis
        self.key = "connector-quota:" + digest([provider, company])
        self.limits = per_minute, per_day, concurrency

    async def acquire(self):
        lease = str(uuid.uuid4())
        accepted, wait = await self.redis.eval(ACQUIRE, 2, self.key, self.key + ":leases", *self.limits, lease)
        if not accepted:
            raise QuotaDeferred(int(wait))
        return lease

    async def release(self, lease):
        await self.redis.zrem(self.key + ":leases", lease)
