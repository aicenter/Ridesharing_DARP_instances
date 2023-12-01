# Changelog

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