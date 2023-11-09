"""Main file to create a manifest on a specific query."""

import argparse
import json
from typing import List

from dcmw.db import get_database_manager
from dcmw.manifest.manifest_query import check_and_return_query_class
from dcmw.manifest.manifest_tag_selection import fill_manifest, json_serial, write_json_manifest
from dcmw.paths import DATA_DIR
from dcmw.utils.utils_io import get_logger

logger = get_logger()


def main(db_names: List[str], save_dir: str, manifest_name: str, query_name: str) -> None:
    """Creating a manifest file based on some query, which is then queried from all databases in db_names."""

    logger.info(f"Creating manifest file by querying data from databases: {db_names}.")

    manifest = []
    for db_name in db_names:
        # Initialize database manager:
        database_manager = get_database_manager(db_name)

        # Do query
        query_class = check_and_return_query_class(query_name)
        query = query_class(database_manager)
        series = query.execute_query()

        # Make manifest
        manifest.extend(fill_manifest(series, db_name))

    json_manifest = json.dumps(manifest, indent=4, default=json_serial)
    write_json_manifest(json_manifest, save_dir, manifest_name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create manifest file for your deep learning model input.")
    parser.add_argument(
        "--save_dir", type=str, dest="save_dir", help="Directory where manifest file is saved to.", default=DATA_DIR
    )
    parser.add_argument("--name", type=str, dest="name", help="Name of manifest file, with extension.", required=True)
    parser.add_argument(
        "--db_names", type=str, nargs="+", dest="db_names", help="Names of database to do query in.", required=True
    )
    parser.add_argument(
        "--query_name",
        type=str,
        required=True,
        help="Name of the class which contains your query. Query " "should be written in manifest_query.py.",
    )
    args = parser.parse_args()

    main(args.db_names, args.save_dir, args.name, args.query_name)
