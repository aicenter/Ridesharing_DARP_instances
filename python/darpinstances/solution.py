from typing import List, Optional, Set

from darpinstances.vehicle_plan import VehiclePlan


class Solution:
    def __init__(self, vehicle_plans: List[VehiclePlan], cost: int, dropped_requests=Optional[Set[int]]):
        """
        Constructor
        :param vehicle_plans: List of vehicle plans
        :param cost: Total cost
        :param dropped_requests: Set of dropped requests' indices
        """
        self.vehicle_plans = vehicle_plans
        self.cost = cost
        if dropped_requests is None:
            self.dropped_requests = []
        else:
            self.dropped_requests = dropped_requests

    def __str__(self):
        return 'solution: cost {}.\nPlans: {}.' \
            .format(self.cost, '\n'.join([str(p) for p in self.vehicle_plans]))
