import argparse
import copy
import json
import logging
import os
import os.path
import sys
from datetime import timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Tuple, Set, Optional, Dict, List

import pandas as pd

import darpinstances.experiments
import darpinstances.inout
import darpinstances.instance
from darpinstances.cordeau_benchmark import load as load_cordeau
from darpinstances.inout import check_file_exists
from darpinstances.instance import DARPInstance, TravelTimeProvider
from darpinstances.instance_objects import Request, Action, ActionType
from darpinstances.solution import VehiclePlan, Solution
from darpinstances.utils import TimeLoader


class Failure(Enum):
    PLAN_DEPARTURE_TIME = auto()
    ARRIVAL_TIME_MISMATCH = auto()
    DEPARTURE_TIME = auto()
    VEHICLE_REUSED = auto()
    OPERATION_WINDOW = auto()
    PRECEDENCE = auto()
    MAX_TIME = auto()
    CAPACITY = auto()
    WHEELCHAIR_CAPACITY = auto()
    CHILD_SEAT_CAPACITY = auto()
    EQUIPMENT = auto()
    REQUIRED_VEHICLE = auto()
    DRIVER_PAUSE = auto()
    MAX_DRIVE_TIME = auto()
    MAX_RIDE_TIME = auto()
    MAX_TRAVEL_DELAY = auto()
    ARRIVAL_DEADLINE = auto()
    ARRIVAL_TOO_EARLY = auto()
    EXCLUSIVE_RIDE = auto()
    MAX_WALKING_DISTANCE = auto()
    MAX_ROUTE_DURATION = auto()
    PLAN_COST = auto()
    SOLUTION_COST = auto()
    REQUEST_SERVED_TWICE = auto()
    REQUEST_NOT_SERVED = auto()


class SolutionChecker:
    def __init__(self, max_error_count: int = 10):
        self.error_count = 0
        self.max_error_count = max_error_count

    def _increment_error(self):
        self.error_count += 1
        if self.error_count > self.max_error_count:
            raise RuntimeError(f"Error count ({self.error_count}) exceeded maximum allowed errors ({self.max_error_count})")

    def check_plan(
        self,
        plan: VehiclePlan,
        plan_counter: int,
        instance: DARPInstance,
        used_vehicles: set,
        failures: Dict[Failure, int],
        fleet_sizing: bool = False,
    ) -> Tuple[int, bool, Set[Request]]:
        plan_ok = True

        def fail(failure: Failure, message: str):
            nonlocal plan_ok
            logging.warning(message)
            failures[failure] += 1
            plan_ok = False
            self._increment_error()

        config = instance.darp_instance_config
        vehicle = plan.vehicle
        cost_weights = config.cost_weights
        # allocator-style accounting counts passenger components once per
        # request and measures delay from the pickup departure (see CostWeights)
        per_request_accounting = getattr(cost_weights, "accounting", "per_traveller") == "per_request"

        if config.start_time and plan.departure_time < config.start_time:
            fail(
                Failure.PLAN_DEPARTURE_TIME,
                "[{}. plan]: departure time {} is smaller then the instance start time ({})".format(
                    plan_counter, plan.departure_time, config.start_time
                ),
            )

        time = plan.departure_time
        previous_action: Optional[Action] = None
        onboard_requests = set()
        departure_times = dict()
        vehicle_index = vehicle.index if vehicle is not None else plan_counter
        travel_time_provider = instance.travel_time_provider
        distance_provider = instance.distance_provider
        served_requests = set()
        vehicle_configurations = (
            copy.deepcopy(vehicle.configurations)
            if vehicle is not None
            else []
        )
        used_equipment = []
        min_pause_length = config.min_pause_length * 60
        max_pause_interval = config.max_pause_interval * 60
        driving_start = time

        # typed resource loads for the multi-seat demand model: a standard
        # passenger holds a regular seat, a wheelchair user holds a wheelchair
        # slot, a child in a child seat holds a regular seat AND a child seat unit
        seat_load = 0
        wheelchair_load = 0
        child_seat_load = 0

        # per-vehicle driver rules, in seconds
        total_drive_seconds = 0.0
        continuous_drive_seconds = 0.0

        # components of the generalized weighted cost model
        travel_time_total = 0.0
        distance_total = 0.0
        ride_time_total = 0.0
        passenger_delay_total = 0.0
        earliness_total = 0.0

        if not fleet_sizing and not config.virtual_vehicles:
            if vehicle_index in used_vehicles:
                fail(Failure.VEHICLE_REUSED, "[{}. plan]: Vehicle {} already used".format(plan_counter, vehicle_index))
            used_vehicles.add(vehicle_index)

        operation_start = vehicle.operation_start if vehicle is not None else None
        operation_end = vehicle.operation_end if vehicle is not None else None

        # operation time check
        if not fleet_sizing and vehicle is not None:
            if (operation_start and (plan.departure_time < operation_start)):
                fail(
                    Failure.OPERATION_WINDOW,
                    "{} plan starts at {}. operation starts at {}, plan should not start before operation".format(
                        plan_counter, plan.departure_time, operation_start
                    ),
                )
            if (operation_end and (plan.arrival_time > operation_end)):
                fail(
                    Failure.OPERATION_WINDOW,
                    "{} plan ends at {}. operation ends at {}, plan should not end after operation".format(
                        plan_counter, plan.arrival_time, operation_end
                    ),
                )

        travel_time_divider = config.travel_time_divider

        for action_index, action_data in enumerate(plan.actions):
            action = action_data.action

            request = action.request
            is_drop_off = action.action_type == ActionType.DROP_OFF
            is_pickup = action.action_type == ActionType.PICKUP
            demand = request.demand

            # onboard check; exclusive-ride conflicts are evaluated against the
            # onboard set BEFORE this action is applied
            if is_pickup:
                if request.exclusive and onboard_requests:
                    fail(
                        Failure.EXCLUSIVE_RIDE,
                        "[{}. plan] Exclusive request {} picked up while other requests are onboard.".format(
                            plan_counter, request.index
                        ),
                    )
                elif any(onboard.exclusive for onboard in onboard_requests):
                    fail(
                        Failure.EXCLUSIVE_RIDE,
                        "[{}. plan] Request {} picked up while an exclusive request is onboard.".format(
                            plan_counter, request.index
                        ),
                    )
                onboard_requests.add(request)
            else:
                if request in onboard_requests:
                    onboard_requests.remove(request)
                    served_requests.add(request)
                else:
                    fail(
                        Failure.PRECEDENCE,
                        "[{}. plan] Request {} dropped off while not being picked up first.".format(
                            plan_counter, request.index
                        ),
                    )

            leg_from_node = None
            if previous_action:
                travel_time = travel_time_provider.get_travel_time(previous_action.node, action_data.action.node)
                leg_from_node = previous_action.node
            else:
                if fleet_sizing or vehicle is None:
                    travel_time = 0
                elif config.virtual_vehicles:
                    travel_time = vehicle.time_to_start
                else:
                    travel_time = travel_time_provider.get_travel_time(
                        vehicle.initial_position, action_data.action.node
                    )
                    leg_from_node = vehicle.initial_position
            # adjust travel time if the provider is not in seconds
            travel_time = travel_time / travel_time_divider

            if distance_provider is not None and leg_from_node is not None:
                distance_total += distance_provider.get_travel_time(leg_from_node, action_data.action.node)

            total_drive_seconds += travel_time
            continuous_drive_seconds += travel_time

            time += timedelta(seconds=int(travel_time))
            arrival_time = time

            # per-vehicle continuous drive limit: checked on arrival, before any
            # pause at this stop can reset the counter
            if (
                not fleet_sizing
                and vehicle is not None
                and vehicle.max_drive_time_without_pause is not None
                and continuous_drive_seconds > vehicle.max_drive_time_without_pause
            ):
                fail(
                    Failure.DRIVER_PAUSE,
                    "[{}. plan] Continuous drive time {} s exceeds the vehicle limit {} s at request {}.".format(
                        plan_counter, continuous_drive_seconds, vehicle.max_drive_time_without_pause, request.index
                    ),
                )

            # arrival time check: the reported arrival must exactly match the schedule recomputed
            # from the travel time matrix, otherwise a falsified schedule could mask violations
            if action_data.arrival_time is not None:
                if action_data.arrival_time != time:
                    fail(
                        Failure.ARRIVAL_TIME_MISMATCH,
                        f"[{plan_counter}. plan, {action_index + 1}. Action] Arrival time mismatch (expected {time}, "
                        f"was {action_data.arrival_time}) when handling request {action_data.action.request.index}",
                    )

            # max time check. Note that max_pickup_delay is already included in the action max
            # time, it is added to both max pickup time and max drop off time on instance load.
            # A max time of None means the constraint is disabled for this request.
            max_time = action_data.action.max_time
            if max_time is not None and time > max_time:
                fail(
                    Failure.MAX_TIME,
                    "[{}. plan, {}. Action] Action max time exceeded ({} > {}) when handling request {}.".format(
                        plan_counter, action_index, time, action_data.action.max_time, action_data.action.request.index
                    ),
                )

            # capacity checks over the three typed resources; the regular seat
            # check is skipped for vehicles with legacy slot configurations, as
            # their capacity is expressed by the configurations instead
            if is_pickup:
                if not fleet_sizing and vehicle is not None:
                    if not vehicle_configurations and seat_load + demand.seats_needed > vehicle.capacity:
                        fail(
                            Failure.CAPACITY,
                            "[{}. plan] Seat capacity exceeded when handling request {}: {} occupied + {} needed > {}".format(
                                plan_counter, request.index, seat_load, demand.seats_needed, vehicle.capacity
                            ),
                        )
                    if demand.wheelchairs and wheelchair_load + demand.wheelchairs > vehicle.wheelchair_slots:
                        fail(
                            Failure.WHEELCHAIR_CAPACITY,
                            "[{}. plan] Wheelchair slots exceeded when handling request {}: {} occupied + {} needed > {}".format(
                                plan_counter, request.index, wheelchair_load, demand.wheelchairs, vehicle.wheelchair_slots
                            ),
                        )
                    if demand.children_in_seat and child_seat_load + demand.children_in_seat > vehicle.child_seats:
                        fail(
                            Failure.CHILD_SEAT_CAPACITY,
                            "[{}. plan] Child seats exceeded when handling request {}: {} occupied + {} needed > {}".format(
                                plan_counter, request.index, child_seat_load, demand.children_in_seat, vehicle.child_seats
                            ),
                        )
                seat_load += demand.seats_needed
                wheelchair_load += demand.wheelchairs
                child_seat_load += demand.children_in_seat
            else:
                seat_load -= demand.seats_needed
                wheelchair_load -= demand.wheelchairs
                child_seat_load -= demand.children_in_seat

            # legacy slot-configuration equipment check (integer equipment types
            # consuming vehicle configuration slots)
            if not fleet_sizing:
                matching_configurations = [configuration for configuration in vehicle_configurations if
                                          any(num in used_equipment for num in configuration)]
                available_configurations = copy.deepcopy(vehicle_configurations) if not used_equipment else copy.deepcopy(
                    matching_configurations
                )
                for configuration in available_configurations:
                    for item in used_equipment:
                        if item in configuration:
                            configuration.remove(item)

                equipment = action_data.action.request.equipment
                if equipment != 0:
                    if is_pickup:
                        if not any(equipment in configuration for configuration in available_configurations):
                            fail(
                                Failure.EQUIPMENT,
                                "Request {}, Equipment {} not available in vehicle equipment list. Vehicle: {}".format(
                                    action_data.action.request.index,
                                    equipment,
                                    vehicle_index
                                ),
                            )
                        used_equipment.append(equipment)
                    elif is_drop_off:
                        used_equipment.remove(equipment)

            # named equipment flags: the vehicle must carry a superset of the
            # request's required equipment (not consumed, unlike configurations)
            if is_pickup and request.required_equipment and vehicle is not None:
                if not request.required_equipment.issubset(vehicle.equipment):
                    fail(
                        Failure.EQUIPMENT,
                        "[{}. plan] Request {} requires equipment {} but vehicle {} only has {}.".format(
                            plan_counter, request.index, sorted(request.required_equipment),
                            vehicle_index, sorted(vehicle.equipment)
                        ),
                    )

            # walking distance: a static per-request check, validated at pickup
            if is_pickup and request.constraints.max_walking_distance is not None:
                walk_limit = request.constraints.max_walking_distance
                if request.walk_to_origin > walk_limit or request.walk_from_destination > walk_limit:
                    fail(
                        Failure.MAX_WALKING_DISTANCE,
                        "[{}. plan] Request {} walking distance ({} m to origin, {} m from destination) exceeds {} m.".format(
                            plan_counter, request.index, request.walk_to_origin,
                            request.walk_from_destination, walk_limit
                        ),
                    )

            travel_time_total += travel_time

            # passenger delay cost component: drop-off delay versus the ideal
            # direct ride starting at the desired pickup time. Under per-request
            # accounting the delay is measured from the pickup DEPARTURE (the
            # rider's own boarding service time is not delay) and counted once
            # per request instead of per traveller.
            if is_drop_off:
                min_drop_off_time = request.pickup_action.min_time + timedelta(
                    seconds=request.min_travel_time
                )
                drop_off_delay_seconds = (time - min_drop_off_time).total_seconds()
                if per_request_accounting:
                    passenger_delay_total += drop_off_delay_seconds - request.pickup_action.service_time
                else:
                    passenger_delay_total += drop_off_delay_seconds * demand.total_travellers

            # vehicle id check
            if not fleet_sizing and action_data.action.request.required_vehicle_id is not None:
                if action_data.action.request.required_vehicle_id != vehicle_index:
                    fail(
                        Failure.REQUIRED_VEHICLE,
                        "Request {} is not for vehicle {}.".format(action_data.action.request.index, vehicle_index),
                    )

            # waiting to min time
            if action.action_type == ActionType.PICKUP and time < action_data.action.min_time:
                pause_duration = action_data.action.min_time - time
                time = action_data.action.min_time
                if not fleet_sizing and (pause_duration > timedelta(seconds=min_pause_length)):
                    driving_start = time

            # legacy instance-level pause rule (configured in minutes, wall time
            # since the last qualifying pause)
            if not fleet_sizing and (max_pause_interval and time - driving_start > timedelta(seconds=max_pause_interval)):
                fail(
                    Failure.DRIVER_PAUSE,
                    "in Request {} driver is active {} min, max is {}.".format(
                        action_data.action.request.index,
                        time - driving_start,
                        max_pause_interval
                        ),
                )

            # per-request checks anchored to the actual pickup: ride time,
            # travel delay, and the required arrival time (with its symmetric
            # earliness bound). The ride is measured from the pickup departure
            # (after service) to the drop-off arrival.
            if is_drop_off and request.index in departure_times:
                ride_time = time - departure_times[request.index]
                ride_seconds = ride_time.total_seconds()

                max_ride_time = request.constraints.max_ride_time
                if not request.constraints.resolved and max_ride_time is None and config.max_ride_time:
                    # legacy instances without per-request constraints fall back
                    # to the instance-level limit; for resolved constraints None
                    # means the constraint is disabled for this request
                    max_ride_time = config.max_ride_time
                if max_ride_time is not None and ride_seconds > max_ride_time:
                    fail(
                        Failure.MAX_RIDE_TIME,
                        "[{}. plan] Max ride time exceeded for request {}: ride time was {} s while max ride time is {} s".format(
                            plan_counter, request.index, ride_seconds, max_ride_time
                        ),
                    )

                max_travel_delay = request.constraints.max_travel_delay
                if max_travel_delay is not None and ride_seconds - request.min_travel_time > max_travel_delay:
                    fail(
                        Failure.MAX_TRAVEL_DELAY,
                        "[{}. plan] Max travel delay exceeded for request {}: ride time {} s exceeds the minimum {} s by more than {} s".format(
                            plan_counter, request.index, ride_seconds, request.min_travel_time, max_travel_delay
                        ),
                    )

                required_arrival = request.constraints.required_arrival_time
                if required_arrival is not None:
                    if time > required_arrival:
                        fail(
                            Failure.ARRIVAL_DEADLINE,
                            "[{}. plan] Request {} arrived at {} after the required arrival time {}.".format(
                                plan_counter, request.index, time, required_arrival
                            ),
                        )
                    else:
                        earliness = (required_arrival - time).total_seconds()
                        # the earliness bound defaults to the travel delay
                        # budget; resolved instances may override it per request
                        # via the max_earliness column (None = unbounded)
                        if request.constraints.resolved:
                            max_earliness = request.constraints.max_earliness
                        else:
                            max_earliness = max_travel_delay
                        if max_earliness is not None and earliness > max_earliness:
                            fail(
                                Failure.ARRIVAL_TOO_EARLY,
                                "[{}. plan] Request {} arrived {} s before the required arrival time {}, more than {} s early.".format(
                                    plan_counter, request.index, earliness, required_arrival, max_earliness
                                ),
                            )
                        earliness_total += earliness

                if per_request_accounting:
                    ride_time_total += ride_seconds
                else:
                    ride_time_total += ride_seconds * demand.total_travellers

            # service time
            time += timedelta(seconds=int(action_data.action.service_time))

            # departure time check.
            # We can departure after the current time, but not before
            if action_data.departure_time < time:
                fail(
                    Failure.DEPARTURE_TIME,
                    "[{}. plan, {}. action] Departure time mismatch (was {}, must be higher than current time {}) when handling request {}".format(
                        plan_counter, action_index + 1, action_data.departure_time, time, action_data.action.request.index
                                  ),
                )

            # per-vehicle driver pause: idle time at this stop (waiting, service,
            # and any extra slack before the reported departure) resets the
            # continuous drive counter when it reaches the vehicle's minimum pause
            if vehicle is not None and vehicle.min_pause is not None:
                idle_seconds = (action_data.departure_time - arrival_time).total_seconds()
                if idle_seconds >= vehicle.min_pause:
                    continuous_drive_seconds = 0.0

            time = action_data.departure_time

            # per-stop operation window: every departure must fit the window
            # (arrivals precede departures, so they are covered by this check)
            if not fleet_sizing and operation_end is not None and time > operation_end:
                fail(
                    Failure.OPERATION_WINDOW,
                    "[{}. plan] Departure at {} is after the vehicle operation end {} when handling request {}.".format(
                        plan_counter, time, operation_end, request.index
                    ),
                )

            #  max ride time check - pickup
            if is_pickup:
                departure_times[request.index] = time

            previous_action = action_data.action

        # return to init position; the instance-level setting can be overridden
        # per vehicle. A vehicle may also declare cost_return_to_depot: the leg
        # is then priced (travel time, distance, plan duration) without being
        # constraint-checked — the return is physical but not required by any
        # constraint.
        return_to_depot = config.return_to_depot
        if vehicle is not None and vehicle.return_to_depot is not None:
            return_to_depot = vehicle.return_to_depot
        include_return_leg = return_to_depot or (
            vehicle is not None and getattr(vehicle, "cost_return_to_depot", False)
        )
        if (
            not fleet_sizing
            and vehicle is not None
            and previous_action
            and include_return_leg
        ):
            travel_time_to_depot = travel_time_provider.get_travel_time(
                previous_action.node, vehicle.initial_position
            )
            travel_time_to_depot = travel_time_to_depot / travel_time_divider
            travel_time_total += travel_time_to_depot
            if distance_provider is not None:
                distance_total += distance_provider.get_travel_time(
                    previous_action.node, vehicle.initial_position
                )
            time += timedelta(seconds=int(travel_time_to_depot))

            if return_to_depot:
                # the constrained return leg counts toward the driver rules and
                # must fit the operation window
                total_drive_seconds += travel_time_to_depot
                continuous_drive_seconds += travel_time_to_depot
                if operation_end is not None and time > operation_end:
                    fail(
                        Failure.OPERATION_WINDOW,
                        "[{}. plan] Depot return at {} is after the vehicle operation end {}.".format(
                            plan_counter, time, operation_end
                        ),
                    )
                if (
                    vehicle.max_drive_time_without_pause is not None
                    and continuous_drive_seconds > vehicle.max_drive_time_without_pause
                ):
                    fail(
                        Failure.DRIVER_PAUSE,
                        "[{}. plan] Continuous drive time {} s exceeds the vehicle limit {} s on the depot return leg.".format(
                            plan_counter, continuous_drive_seconds, vehicle.max_drive_time_without_pause
                        ),
                    )

        # per-vehicle total drive time
        if (
            not fleet_sizing
            and vehicle is not None
            and vehicle.max_drive_time is not None
            and total_drive_seconds > vehicle.max_drive_time
        ):
            fail(
                Failure.MAX_DRIVE_TIME,
                "[{}. plan] Total drive time {} s exceeds the vehicle limit {} s.".format(
                    plan_counter, total_drive_seconds, vehicle.max_drive_time
                ),
            )

        # max route time check
        max_route_duration = config.max_route_duration
        if (
            not fleet_sizing
            and max_route_duration
            and time - plan.departure_time > timedelta(seconds=int(max_route_duration))
        ):
            fail(
                Failure.MAX_ROUTE_DURATION,
                "[{}. plan] Total max route duration exceeded: Duration is {} but maximum allowed route duration is {}".format(
                    plan_counter,
                    time - plan.departure_time,
                    max_route_duration
                    ),
            )

        # generalized weighted cost; the default weights reproduce the legacy
        # cost exactly (total travel time + weighted drop-off delay + capital cost)
        plan_duration_seconds = (time - plan.departure_time).total_seconds() if plan.actions else 0.0
        cost = (
            cost_weights.travel_time_weight * travel_time_total
            + cost_weights.distance_weight * distance_total
            + cost_weights.ride_time_weight * ride_time_total
            + cost_weights.passenger_delay_weight * passenger_delay_total
            + cost_weights.earliness_weight * earliness_total
            + cost_weights.plan_duration_weight * plan_duration_seconds
        )
        if plan.actions:
            cost += cost_weights.fixed_plan_cost
        # legacy behavior: the capital cost applies to every plan in the solution
        cost += cost_weights.vehicle_capital_cost

        # cost check
        if plan.cost is not None and abs(cost - plan.cost) > 1:
            fail(
                Failure.PLAN_COST,
                "{} plan cost mismatch. expected: {}, computed: {}".format(plan_counter, plan.cost, cost),
            )

        if plan_ok:
            logging.debug("[{}. plan] with {} actions OK".format(plan_counter, len(plan.actions)))
        else:
            logging.warning("[{}. plan] with {} actions NOT OK".format(plan_counter, len(plan.actions)))

        return cost, plan_ok, served_requests

    def check_solution(
        self, instance: DARPInstance, solution: Solution, fleet_sizing: bool = False
    ) -> Tuple[bool, Dict[Failure, int]]:
        failures = {failure: 0 for failure in Failure}

        if not solution.feasible:
            logging.info("Solution is infeasible")
            return True, failures

        used_vehicles = set()
        solution_ok = True
        served_requests = set()
        total_cost = 0.0

        plan_counter = 1

        for plan in solution.vehicle_plans:
            cost, plan_ok, plan_served_requests = self.check_plan(
                plan, plan_counter, instance, used_vehicles, failures, fleet_sizing=fleet_sizing
            )
            total_cost += cost
            if not plan_ok:
                solution_ok = False

            # served_requests.update(plan_served_requests)
            for request in plan_served_requests:
                if request in served_requests:
                    logging.warning("Request {} served twice.".format(request.index))
                    failures[Failure.REQUEST_SERVED_TWICE] += 1
                    solution_ok = False
                    self._increment_error()
                else:
                    served_requests.add(request)

            plan_counter += 1

        # all request served check
        for request in instance.requests:
            if request not in served_requests and request.index not in solution.dropped_requests:
                logging.warning("Request {} not served while not being in dropped requests list.".format(request.index))
                failures[Failure.REQUEST_NOT_SERVED] += 1
                solution_ok = False
                self._increment_error()

        # total cost check
        if solution.cost is not None:
            if abs(total_cost - solution.cost) > 1:
                logging.warning(
                    "Solution cost not computed correctly. Solution cost: {}, total cost of all plans: {}".format(
                        solution.cost, total_cost
                    )
                )
                failures[Failure.SOLUTION_COST] += 1
                solution_ok = False
                self._increment_error()

        if solution_ok:
            logging.info("Solution OK")
        else:
            logging.warning("Solution NOT OK")

        return solution_ok, failures

    def check_all_solutions(
        self,
        root_paths: List[Path],
        log_all=True,
        area_index_in_path: Optional[int] = -5,
        fleet_sizing: bool = False,
    ) -> pd.DataFrame:
        logging.info('Checking solutions in the following root paths: \n%s', '\n'.join((str(path) for path in root_paths)))

        dirs = []

        for root_path in root_paths:
            for file in root_path.rglob("*"):
                if file.name == "config.yaml-solution.json" or file.name == "fsd_chains.csv":
                    dirs.append((file.parent, file))

        dir_df = pd.DataFrame(dirs, columns=["root", "solution path"])
        logging.info("%d solutions found", len(dir_df))

        # sort by area
        if area_index_in_path is not None:
            dir_df['area'] = dir_df['root'].apply(lambda path: Path(path).parts[-5])
            dir_df.sort_values(by=['area'], inplace=True)
        else:
            dir_df['area'] = None

        stats = []
        last_instance_path = None
        last_instance = None
        travel_time_provider = None
        last_area = None
        columns = ['solution path', 'ok']
        for root, solution_path, area in zip(dir_df['root'], dir_df['solution path'], dir_df['area']):
            config_path = os.path.join(root, "config.yaml")
            experiment_config = darpinstances.experiments.load_experiment_config(config_path)
            instance_path = Path(experiment_config['instance'])
            if instance_path == last_instance_path:
                instance = last_instance
            else:
                if area is not None and last_area == area:
                    instance, _, time_loader = darpinstances.solution_checker.load_instance(
                        instance_path,
                        last_instance.travel_time_provider,
                        fleet_sizing=fleet_sizing,
                    )
                else:
                    instance, _, time_loader = darpinstances.solution_checker.load_instance(
                        instance_path, fleet_sizing=fleet_sizing
                    )

            effective_fleet_sizing = fleet_sizing or instance.darp_instance_config.is_fleet_sizing

            solution = darpinstances.solution.load_solution(
                solution_path, instance, time_loader, fleet_sizing=effective_fleet_sizing
            )

            ok, failures = self.check_solution(instance, solution, fleet_sizing=effective_fleet_sizing)
            sol_record = [solution_path, ok]
            sol_record.extend([count for _, count in failures.items()])
            stats.append(sol_record)
            if len(columns) == 2:
                columns.extend(failures.keys())

            last_instance_path = instance_path
            last_instance = instance
            last_area = area

        stat_df = pd.DataFrame(stats)
        stat_df.columns = columns

        logging.info("Checked %d solutions", len(stats))
        if log_all:
            pd.set_option('display.max_colwidth', None)
            pd.set_option('display.max_rows', None)
            logging.info("Stats: \n%s", stat_df)

            stats_er = stat_df[stat_df['ok'] == False]
            if len(stats_er) > 0:
                logging.error("Found %d errors", len(stats_er))
                logging.error("Error solutions: \n%s", stats_er)

        return stat_df


def load_data(
    solution_file_path: Path,
    instance_path: Optional[Path],
    demand_file_name: Optional[str] = None,
    fleet_sizing: bool = False,
) -> Tuple[DARPInstance, Solution, bool]:
    check_file_exists(solution_file_path)
    solution_dir_path = solution_file_path.parent
    os.chdir(solution_dir_path)

    if instance_path is None:
        experiment_config_path = solution_dir_path / "config.yaml"
        experiment_config = darpinstances.experiments.load_experiment_config(experiment_config_path)
        instance_path = Path(experiment_config['instance'])

    instance, _, time_loader = load_instance(
        instance_path, demand_file_name=demand_file_name, fleet_sizing=fleet_sizing
    )
    effective_fleet_sizing = fleet_sizing or instance.darp_instance_config.is_fleet_sizing

    solution = darpinstances.solution.load_solution(
        solution_file_path, instance, time_loader, fleet_sizing=effective_fleet_sizing
    )

    return instance, solution, effective_fleet_sizing

    # uncoment the following line to read the Cordeau & Laport solution files  # solution = darpbenchmark.cordeau_benchmark.load_cordeau_solution(cordeau_solution_path, vehicle_map, request_map)


def load_instance(
    instance_path: Path,
    travel_time_provider: Optional[TravelTimeProvider] = None,
    demand_file_name: Optional[str] = None,
    fleet_sizing: bool = False,
) -> Tuple[DARPInstance, TravelTimeProvider, TimeLoader]:
    if instance_path.suffix == '.yaml':
        instance, time_loader = darpinstances.instance.load_instance(
            instance_path, travel_time_provider, demand_file_name, fleet_sizing=fleet_sizing
        )
        travel_time_provider = instance.travel_time_provider
    else:
        instance = load_cordeau(instance_path)
        if fleet_sizing:
            instance.vehicles = []
        travel_time_provider = darpinstances.instance.EuclideanTravelTimeProvider(60)
        time_loader = TimeLoader()  # Default TimeLoader for Cordeau instances
    return instance, travel_time_provider, time_loader


def build_verdict(
    ok: bool,
    plans_checked: int,
    failures: Dict[Failure, int],
    error_count: int,
    aborted: bool = False,
) -> Dict:
    """Machine-readable check result, printed as one JSON line by the CLI."""
    return {
        "ok": bool(ok) and not aborted,
        "plans_checked": plans_checked,
        "failures": {failure.name: count for failure, count in failures.items() if count > 0},
        "error_count": error_count,
        "aborted": aborted,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Script for checking DARP solutions')
    parser.add_argument('solution', type=Path, help='Path to solution file (JSON)')
    parser.add_argument('-i', '--instance', type=str, help='Path to instance config file (YAML)', required=False)
    parser.add_argument(
        '--fleet-sizing',
        action='store_true',
        help=(
            'Fleet-sizing mode: do not load vehicles from instance and ignore vehicle-related constraints. '
            'Also enabled when the instance config sets problem: fleet-sizing. '
            'Passing this flag forces fleet-sizing even if problem in YAML is DARP.'
        ),
    )
    parser.add_argument(
        '--report', type=Path, required=False, help='Write the JSON verdict to this file in addition to stdout'
    )
    parser.add_argument(
        '--max-errors',
        type=int,
        default=10,
        help='Abort the check after this many accumulated errors (default: 10)',
    )

    args = parser.parse_args(argv)

    solution_file_path = args.solution
    logging.info("Checking solution: %s", solution_file_path)
    check_file_exists(solution_file_path)

    if args.instance:
        instance_path = Path(args.instance)
        logging.info("Instance path provided as argument: %s", instance_path)
    else:
        # if instance path is not provided, try to load it from the experiment config
        exp_config_path = solution_file_path.parent / "config.yaml"
        logging.info("Instance path not provided, trying to load it from the experiment config: %s", exp_config_path)
        check_file_exists(exp_config_path)
        experiment_config = darpinstances.experiments.load_experiment_config(exp_config_path)
        instance_path = Path(experiment_config['instance'])
        logging.info("Instance path loaded from the experiment config: %s", instance_path)
        os.chdir(solution_file_path.parent)

    check_file_exists(instance_path)

    instance, solution, fleet_sizing = load_data(
        solution_file_path, instance_path, fleet_sizing=args.fleet_sizing
    )
    solution_checker = SolutionChecker(max_error_count=args.max_errors)

    ok = False
    aborted = False
    failures: Dict[Failure, int] = {failure: 0 for failure in Failure}
    try:
        ok, failures = solution_checker.check_solution(instance, solution, fleet_sizing=fleet_sizing)
    except RuntimeError as ex:
        # the error limit was exceeded; the solution is invalid even though the check is incomplete
        logging.error("Check aborted: %s", ex)
        aborted = True

    verdict = build_verdict(
        ok, len(solution.vehicle_plans), failures, solution_checker.error_count, aborted
    )
    print(json.dumps(verdict))
    if args.report:
        with open(args.report, 'w', encoding='utf-8') as report_file:
            json.dump(verdict, report_file, indent=2)

    return 0 if verdict["ok"] else 1


if __name__ == '__main__':
    sys.exit(main())
