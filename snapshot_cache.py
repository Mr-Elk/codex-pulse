"""Bounded display cache: restore only after the caller verifies chat identity."""
from collections import OrderedDict
from copy import deepcopy
import time


class SnapshotCache:
    def __init__(self, capacity=32, ttl=120, clock=time.monotonic):
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self.entries = OrderedDict()

    def put(self, identity, snapshot):
        if not identity or not snapshot or not snapshot.get("available"):
            return
        if snapshot.get("thread_id") not in (None, identity):
            return
        self.entries[identity] = (self.clock(), deepcopy(snapshot))
        self.entries.move_to_end(identity)
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)

    def restore(self, identity):
        if identity not in self.entries:
            return None
        at, snapshot = self.entries[identity]
        age = self.clock() - at
        if age < 0 or age > self.ttl:
            del self.entries[identity]
            return None
        self.entries.move_to_end(identity)
        result = deepcopy(snapshot)
        # Cumulative totals can resume immediately. Old speed/pending state is
        # never represented as a current request measurement.
        result.update(from_cache=True, cached_age_seconds=round(age, 1),
                      speed_refreshing=True, request_pending=False,
                      latest_tps_estimate=None, latest_request_seconds_estimate=None,
                      turn_average_tps=None)
        return result
