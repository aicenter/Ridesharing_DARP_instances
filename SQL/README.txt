DARP instances SQL add-on (demand / zones / trips)

Prerequisite: apply the road-graph-tool database schema first:
  - road-graph-tool/SQL/schema_preamble.sql
  - road-graph-tool/SQL/tables/*.sql (all files, sorted by name)
  - road-graph-tool/SQL/functions/*.sql
  - road-graph-tool/SQL/procedures/*.sql
  (or run road-graph-tool/python/scripts/install_sql.py with your config)

Then apply this repository, in order:
  1. tables/*.sql   — lexicographic order (01_ … 11_)
  2. functions/*.sql
  3. procedures/*.sql

This layout assumes core graph tables (areas, nodes, ways, edges, …) already exist from road-graph-tool.
dataset_id_seq is used only for the dataset table here; areas.id uses areas_id_seq from road-graph-tool.

Optional: procedure generate_area_for_demand (insert computed geometry into areas) is maintained in
road-graph-tool/SQL/Archive/procedure_generate_instance_area.sql if you need that workflow.
