"""
Database tests of the speed calibration: the SQL functions ``select_zone_representative_nodes`` and
``compute_speed_factor`` and their Python caller.

The tests need a test database with the PostGIS and pgRouting extensions (see ``scripts/setup_test_db.sh`` in the
Road Graph Tool). They are skipped unless the environment variable ``DARPINSTANCES_TEST_DB_CONFIG`` holds the path
to a Road Graph Tool config of that database. The tests install the SQL of both projects into the database and
insert (and finally delete) a small fixture with ids from 9000 up, so never point the variable to a database with
real data.

The fixture is defined in metres of the projected SRID, so the travel times can be computed by hand:

    zone 1 (0..400 x 0..400)          zone 2 (1000..1400 x 0..400)      zone 3 (1600..2000 x 0..400)
    n1 centroid, dead end             n5, n6, n7 equal degree           n9 corner, degree 3
    n2 intersection  <- representative    n5 nearest <- representative   n10 corner, nearest <- representative
    n3 one-way node                   n8 motorway only (no candidate)
    n4 outside the circle
    zone 4: no nodes
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

CONFIG_ENV = "DARPINSTANCES_TEST_DB_CONFIG"

pytestmark = pytest.mark.skipif(
    CONFIG_ENV not in os.environ, reason=f"{CONFIG_ENV} is not set (path to the config of a test database)"
)

SRID = 32633
# origin of the fixture coordinates in the projected SRID (on the central meridian of the UTM zone)
X0, Y0 = 500000, 5540000

AREA = 9001
ZONE_TYPE = 9001
DATASET = 9001
OTHER_DATASET = 9002
HIGHWAY_TAG = 9001
RESIDENTIAL_WAY = 9001
MOTORWAY_WAY = 9002

# node: (x, y) in metres
NODES = {
    9001: (200, 200),
    9002: (200, 100),
    9003: (120, 200),
    9004: (350, 350),
    9005: (1150, 200),
    9006: (1280, 200),
    9007: (1200, 310),
    9008: (1200, 210),
    9009: (1620, 20),
    9010: (1650, 380),
}
MOTORWAY_ONLY_NODES = {9008}

RESIDENTIAL_SPEED = 36  # km/h, 10 m/s
MOTORWAY_SPEED = 72  # km/h, 20 m/s

# (from, to, speed, both directions); travel time in seconds in the comment
EDGES = [
    (9001, 9002, RESIDENTIAL_SPEED, True),  # 100 m, 10 s
    (9002, 9003, RESIDENTIAL_SPEED, True),  # 128.06 m, 13 s
    (9003, 9001, RESIDENTIAL_SPEED, False),  # 80 m, 8 s
    (9003, 9004, RESIDENTIAL_SPEED, False),  # 274.59 m, 27 s
    (9004, 9002, RESIDENTIAL_SPEED, False),  # 291.55 m, 29 s
    (9002, 9005, RESIDENTIAL_SPEED, True),  # 955.25 m, 96 s
    (9005, 9006, RESIDENTIAL_SPEED, True),  # 130 m, 13 s
    (9006, 9007, RESIDENTIAL_SPEED, True),  # 136.01 m, 14 s
    (9007, 9009, RESIDENTIAL_SPEED, True),  # 510.39 m, 51 s
    (9009, 9010, RESIDENTIAL_SPEED, True),  # 361.25 m, 36 s
    (9008, 9005, MOTORWAY_SPEED, True),  # 50.99 m, 3 s
    (9008, 9006, MOTORWAY_SPEED, True),  # 80.62 m, 4 s
    (9008, 9007, MOTORWAY_SPEED, True),  # 100 m, 5 s
    (9008, 9009, MOTORWAY_SPEED, True),  # 460.98 m, 23 s
]

# zone: (min x, min y, max x, max y) in metres
ZONES = {
    9001: (0, 0, 400, 400),
    9002: (1000, 0, 1400, 400),
    9003: (1600, 0, 2000, 400),
    9004: (0, 420, 400, 520),
}

# network travel times between the representative nodes:
#   zone 1 (n2) <-> zone 2 (n5): 96 s
#   zone 2 (n5) <-> zone 3 (n10): 3 + 23 + 36 = 62 s (over the motorway node n8)
#   zone 3 (n10) -> zone 1 (n2): 62 + 96 = 158 s
# (id, origin zone, destination zone, origin time, duration in seconds or None, dataset)
TRIPS = [
    (9001, 9001, 9002, "2022-04-01 08:00:00", 192, DATASET),  # used, ratio 2
    (9002, 9001, 9002, "2022-04-01 09:00:00", 240, DATASET),  # used, ratio 2.5
    (9003, 9002, 9003, "2022-04-01 10:00:00", 124, DATASET),  # used, ratio 2
    (9004, 9003, 9001, "2022-04-02 08:00:00", 474, DATASET),  # used, ratio 3
    (9005, 9001, 9001, "2022-04-01 08:00:00", 300, DATASET),  # within one zone
    (9006, 9001, 9002, "2022-04-01 08:00:00", None, DATASET),  # without duration
    (9007, 9001, 9004, "2022-04-01 08:00:00", 300, DATASET),  # zone without nodes
    (9008, 9001, 9002, "2022-04-01 08:00:00", 30, DATASET),  # filtered: shorter than the minimum duration
    (9009, 9002, 9003, "2022-04-01 08:00:00", 1300, DATASET),  # filtered: ratio above the maximum
    (9010, 9001, 9002, "2022-04-01 08:00:00", 9600, OTHER_DATASET),  # not selected
]


def _point(node: int) -> str:
    x, y = NODES[node]
    return f"st_transform(st_setsrid(st_makepoint({X0 + x}, {Y0 + y}), {SRID}), 4326)"


def _line(from_node: int, to_node: int) -> str:
    return f"st_makeline({_point(from_node)}, {_point(to_node)})"


def _rectangle(min_x: float, min_y: float, max_x: float, max_y: float) -> str:
    envelope = f"st_makeenvelope({X0 + min_x}, {Y0 + min_y}, {X0 + max_x}, {Y0 + max_y}, {SRID})"
    return f"st_multi(st_transform({envelope}, 4326))"


def _fixture_statements() -> list[str]:
    statements = [
        f"INSERT INTO areas(id, name, geom) VALUES ({AREA}, 'speed factor test', {_rectangle(-100, -100, 2100, 600)})",
        f"INSERT INTO tags(id, key) VALUES ({HIGHWAY_TAG}, 'highway')",
        f"INSERT INTO zone_type(id, name) VALUES ({ZONE_TYPE}, 'speed factor test')",
        f"INSERT INTO dataset(id, name) VALUES ({DATASET}, 'speed factor test'), ({OTHER_DATASET}, 'other')",
    ]
    for node in NODES:
        statements.append(f"INSERT INTO nodes(id, geom, area) VALUES ({node}, {_point(node)}, {AREA})")
        statements.append(f"INSERT INTO component_data(component_id, node_id, area) VALUES (0, {node}, {AREA})")
    for way, highway, (from_node, to_node) in (
        (RESIDENTIAL_WAY, "residential", (9001, 9010)),
        (MOTORWAY_WAY, "motorway", (9005, 9009)),
    ):
        statements.append(
            f'INSERT INTO ways(id, geom, area, "from", "to", oneway)'
            f" VALUES ({way}, {_line(from_node, to_node)}, {AREA}, {from_node}, {to_node}, false)"
        )
        statements.append(
            f"INSERT INTO ways_tags(way_id, tag_id, tag_value) VALUES ({way}, {HIGHWAY_TAG}, '{highway}')"
        )
    for node in NODES:
        way = MOTORWAY_WAY if node in MOTORWAY_ONLY_NODES else RESIDENTIAL_WAY
        statements.append(
            f'INSERT INTO nodes_ways(id, way_id, node_id, "position", area)'
            f" VALUES ({node}, {way}, {node}, {node - 9000}, {AREA})"
        )
    edge_id = 9000
    for from_node, to_node, speed, both_directions in EDGES:
        directions = [(from_node, to_node)]
        if both_directions:
            directions.append((to_node, from_node))
        for source, target in directions:
            edge_id += 1
            statements.append(
                f'INSERT INTO edges(id, "from", "to", geom, area, speed)'
                f" VALUES ({edge_id}, {source}, {target}, st_multi({_line(source, target)}), {AREA}, {speed})"
            )
    for zone, bounds in ZONES.items():
        statements.append(
            f"INSERT INTO zones(id, name, geom, type) VALUES ({zone}, 'zone {zone}', {_rectangle(*bounds)}, {ZONE_TYPE})"
        )
    for trip, origin, destination, origin_time, duration, dataset in TRIPS:
        destination_time = (
            "NULL" if duration is None else f"timestamp '{origin_time}' + make_interval(secs => {duration})"
        )
        statements.append(
            f"INSERT INTO demand(id, origin, destination, origin_time, destination_time, dataset)"
            f" VALUES ({trip}, {origin}, {destination}, '{origin_time}', {destination_time}, {dataset})"
        )
    return statements


_CLEANUP_STATEMENTS = [
    f"DELETE FROM demand WHERE dataset IN ({DATASET}, {OTHER_DATASET})",
    f"DELETE FROM dataset WHERE id IN ({DATASET}, {OTHER_DATASET})",
    f"DELETE FROM zones WHERE type = {ZONE_TYPE}",
    f"DELETE FROM zone_type WHERE id = {ZONE_TYPE}",
    f"DELETE FROM edges WHERE area = {AREA}",
    f"DELETE FROM component_data WHERE area = {AREA}",
    f"DELETE FROM nodes_ways WHERE area = {AREA}",
    f"DELETE FROM ways_tags WHERE way_id IN ({RESIDENTIAL_WAY}, {MOTORWAY_WAY})",
    f"DELETE FROM ways WHERE area = {AREA}",
    f"DELETE FROM nodes WHERE area = {AREA}",
    f"DELETE FROM tags WHERE id = {HIGHWAY_TAG}",
    f"DELETE FROM areas WHERE id = {AREA}",
]


@pytest.fixture(scope="module")
def db():
    """The database with the SQL of both projects installed and the fixture inserted."""
    from roadgraphtool.config import parse_config_file
    from roadgraphtool.db import db as rgt_db, init_db

    config_path = Path(os.environ[CONFIG_ENV]).resolve()
    install_script = Path(__file__).resolve().parents[1] / "scripts" / "install_sql.py"
    subprocess.run([sys.executable, str(install_script), str(config_path)], check=True)

    init_db(parse_config_file(config_path))
    rgt_db.execute_statements(_CLEANUP_STATEMENTS)
    rgt_db.execute_statements(_fixture_statements())
    yield rgt_db
    rgt_db.execute_statements(_CLEANUP_STATEMENTS)


@pytest.fixture
def cursor(db):
    """A cursor in a transaction that is rolled back after the test."""
    cursor = db.get_new_cursor()
    yield cursor
    cursor.connection.rollback()
    cursor.close()


def _compute_speed_factor(cursor, **arguments) -> dict:
    parameters = {"p_area_id": AREA, "p_area_srid": SRID, "p_demand_dataset_ids": [DATASET], **arguments}
    casts = {"p_area_id": "smallint", "p_demand_dataset_ids": "integer[]", "p_zone_types": "smallint[]"}
    call_arguments = ", ".join(
        f"{name} => CAST(%({name})s AS {casts[name]})" if name in casts else f"{name} => %({name})s"
        for name in parameters
    )
    cursor.execute(f"SELECT * FROM compute_speed_factor({call_arguments})", parameters)
    row = cursor.fetchone()
    return dict(zip((column.name for column in cursor.description), row))


def test_representative_nodes(cursor):
    cursor.execute("CALL create_demand_sampling_edges(%s::smallint)", (AREA,))
    cursor.execute("CALL create_selected_demand(%s::integer[])", ([DATASET],))
    cursor.execute("CALL create_zones_in_area(%s::smallint, %s::smallint[])", (AREA, [ZONE_TYPE]))
    cursor.execute(
        "SELECT zone_id, node_id, in_circle FROM select_zone_representative_nodes(%s::smallint, %s)", (AREA, SRID)
    )

    assert cursor.fetchall() == [
        # the intersection, not the dead end at the centroid (9001) or the node with one incoming edge (9003)
        (9001, 9002, True),
        # the nearest of the nodes with equal degree, not the motorway node near the centroid (9008)
        (9002, 9005, True),
        # no node in the circle: the nearest one, not the one with the higher degree (9009)
        (9003, 9010, False),
        # zone 9004 has no nodes
    ]


def test_speed_factor(cursor):
    result = _compute_speed_factor(cursor, p_zone_types=[ZONE_TYPE])

    # used trips: travel times 96 + 96 + 62 + 158 = 412 s, durations 192 + 240 + 124 + 474 = 1030 s
    assert result["speed_factor"] == pytest.approx(412 / 1030)
    assert result["trips_total"] == 9
    assert result["trips_used"] == 4
    assert result["trips_without_duration"] == 1
    assert result["trips_intra_zone"] == 1
    assert result["trips_zone_without_nodes"] == 1
    assert result["trips_filtered"] == 2
    assert result["zone_pairs"] == 3
    assert result["mean_ratio"] == pytest.approx((2 + 2.5 + 2 + 3) / 4)
    assert result["median_ratio"] == pytest.approx(2.25)


def test_speed_factor_time_window_and_limits(cursor):
    result = _compute_speed_factor(
        cursor,
        p_zone_types=[ZONE_TYPE],
        p_start_time="2022-04-01 00:00:00",
        p_end_time="2022-04-01 23:59:59",
        p_max_ratio=25,
    )

    # without the trip of the next day (9004), with the trip of ratio 1300 / 62 (9009)
    assert result["trips_total"] == 8
    assert result["trips_used"] == 4
    assert result["trips_filtered"] == 1
    assert result["speed_factor"] == pytest.approx((96 + 96 + 62 + 62) / (192 + 240 + 124 + 1300))


def test_speed_factor_can_run_twice_in_one_transaction(cursor):
    first = _compute_speed_factor(cursor, p_zone_types=[ZONE_TYPE])
    second = _compute_speed_factor(cursor, p_zone_types=[ZONE_TYPE])

    assert first == second


def test_edges_without_speed_are_rejected(cursor):
    import psycopg2.errors

    cursor.execute("UPDATE edges SET speed = NULL WHERE id = 9001")

    with pytest.raises(psycopg2.errors.RaiseException, match="have no speed"):
        _compute_speed_factor(cursor, p_zone_types=[ZONE_TYPE])


def test_python_caller(db):
    from darpinstances.instance_generation.speed_calibration import compute_speed_factor

    parameters = {
        "area_id": AREA,
        "srid": SRID,
        "demand_datasets": [DATASET],
        "start_time": None,
        "end_time": None,
        "zone_types": [ZONE_TYPE],
        "ignored_zones": None,
        "min_duration_minutes": 1.0,
        "max_duration_minutes": 180.0,
        "min_ratio": 0.5,
        "max_ratio": 10.0,
    }

    result = compute_speed_factor(parameters)

    assert result["speed_factor"] == pytest.approx(412 / 1030)
    assert result["trips_total"] == 9
    assert result["trips_used"] == 4
    assert isinstance(result["trips_used"], int)
