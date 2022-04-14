# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import ops
import yaml
from pathlib import Path
from pymongo import MongoClient
from typing import List
from pytest_operator.plugin import OpsTest
from subprocess import Popen, PIPE

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
ADMIN_USER = "operator"
APP_NAME = METADATA["name"]
UNIT_IDS = [0, 1, 2]
PORT = 27017


class PasswordRetrievalError(Exception):
    """Raised when unable to retrieve password."""
    pass


@property
def replica_set_client(ops: OpsTest, direct=False):
    """TODO."""
    hostnames = [f"{APP_NAME}-{unit_id}.{APP_NAME}-endpoints" for unit_id in UNIT_IDS]

    hosts = ",".join(hostnames)
    uri = (
        f"mongodb://{ADMIN_USER}:"
        f"{mongodb_password}@"
        f"{hosts}/admin?"
        f"replicaSet={APP_NAME}"
    )
    print("connecting with uri: %s", uri)
    return MongoClient(
        uri,
        directConnection=direct,
        connect=False,
        serverSelectionTimeoutMS=1000,
        connectTimeoutMS=2000,
    )


def mongodb_password(unit_name) -> str:
    unit_details = yaml.safe_load(
        Popen("juju show-unit mongodb/0", stdout=PIPE).stdout.read().decode('utf-8'))

    if not unit_details:
        raise PasswordRetrievalError

    try:
        return unit_details['unit_name']['relation-info']['application-data']['admin_password']
    except KeyError:
        raise PasswordRetrievalError


async def find_leader_unit(ops_test: OpsTest) -> ops.model.Unit:
    """Helper function identifies the leader unit.
    Returns:
        leader unit
    """
    leader_unit = None
    for unit in ops_test.model.applications[APP_NAME].units:
        if await unit.is_leader_from_status():
            leader_unit = unit

    return leader_unit
