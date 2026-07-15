# Changelog

## Unreleased

### Code

- fixed: solution checker no longer adds `max_pickup_delay` to action max times a second time (it is already included on instance load)
- changed: solution checker now requires reported arrival times to exactly match the schedule recomputed from the travel time matrix (previously a warning with 1 s tolerance)
- fixed: `max_ride_time`, `max_route_duration`, and `return_to_depot` are now loaded from the instance config (previously hard-coded to disabled for YAML instances)
- fixed: solution loader reads dropped requests via the schema key `index` (`id` kept as fallback) and action service time via the schema key `service_duration` (`service_time` kept as fallback)
- added: solution checker CLI exits with code 1 on failure, prints a machine-readable JSON verdict, and supports `--report <file>` and `--max-errors <n>`
- added: pytest suite for the solution checker (`python/tests`)

## v1.1.2

### Code

- added: results filtering based on path regex
- updated: Solution checker update that discovered small inaccuracies in the VGA results
- updated: README updates, ITSC conference presentation slides added

### Dataset

- fixed: Fixed small inaccuracies in the results of the VGA method in selected instances

## v1.1.1

### Dataset

- updated: improved sizing of the NYC 16 hour instance by 4 vehicles
- fixed and added: the results of the insertion heuristic are now available for all 16 hour instances. The previously existing results now use the correct number of vehicles from sizing. 

## v1.1.0

### Code

- fixed: typos, graphics and quality of life improvements
- fixed: vehicle generation now returns the requested number of vehicles and not less
- changed: improved initial vehicle location sampling in instances with long duration (e.g., 16 hours)

### Dataset

- fixed: moved the 16-hour instances to start at 7:00 instead of 18:00, as they were intended to be.
- changed: using the updated sampling of initial vehicle locations in all 16-hour instances.
- changed: the archive structure on Zenodo is now more convenient for selective downloads.

## v1.0.0

Initial public release.