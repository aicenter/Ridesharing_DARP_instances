import logging
import sys
from pathlib import Path
from typing import Iterable

from roadgraphtool.config import parse_config_file, set_logging
from roadgraphtool.db import db, init_db
from roadgraphtool.sql_install import install_sql as install_rgt_sql


def _iter_sql_files(sql_dir: Path) -> Iterable[Path]:
    tables_dir = sql_dir / "tables"
    functions_dir = sql_dir / "functions"
    procedures_dir = sql_dir / "procedures"

    yield from sorted(tables_dir.glob("*.sql"))
    yield from sorted(functions_dir.rglob("*.sql"))
    yield from sorted(procedures_dir.rglob("*.sql"))


def _install_rgt_sql(config) -> None:
    install_rgt_sql(config=config, db=db, include_tests=True)


def _execute_sql_file(repo_root: Path, sql_file: Path, schema: str) -> None:
    rel = str(sql_file)
    try:
        rel = str(sql_file.relative_to(repo_root))
    except ValueError:
        pass
    logging.info("Executing %s", rel)
    db.execute_script(sql_file, schema=schema)


def main() -> int:
    args = sys.argv
    if len(args) < 2:
        logging.error("You have to provide a path to the road-graph-tool YAML config file as an argument.")
        return -1
    config_path = Path(args[1])

    config = parse_config_file(config_path)
    init_db(config)
    set_logging(config)

    schema = getattr(config, "schema", "public")

    repo_root = Path(__file__).resolve().parents[2]
    sql_dir = repo_root / "SQL"
    if not sql_dir.exists():
        raise FileNotFoundError(f"SQL directory not found at '{sql_dir}'.")

    # Ensure road-graph-tool SQL elements are installed first.
    _install_rgt_sql(config)

    for sql_file in _iter_sql_files(sql_dir):
        _execute_sql_file(repo_root, sql_file, schema=schema)

    logging.info("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

