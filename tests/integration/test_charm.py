#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


from helpers import (
    METADATA,
    APP_NAME,
    PORT,
    UNIT_IDS,
    find_leader_unit,
    replica_set_client
)
import logging

import pytest
from pymongo import MongoClient
from pytest_operator.plugin import OpsTest
from pymongo.errors import ServerSelectionTimeoutError
logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest) -> None:
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    resources = {"mongodb-image": METADATA["resources"]["mongodb-image"]["upstream-source"]}
    await ops_test.model.deploy(charm, resources=resources, application_name=APP_NAME, num_units=len(UNIT_IDS))

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    assert len(ops_test.model.applications[APP_NAME].units) == len(UNIT_IDS)


@pytest.mark.abort_on_fail
@pytest.mark.parametrize("unit_id", UNIT_IDS)
async def test_application_is_up(ops_test: OpsTest, unit_id: int) -> None:
    """Verifies that each unit of the MongoDB application has mongod running."""
    # aquire unit address
    status = await ops_test.model.get_status()  # noqa: F821
    ip_address = status["applications"][APP_NAME]["units"][f"{APP_NAME}/{unit_id}"]["address"]

    # verify mongod on this unit is responding
    response = MongoClient(ip_address, directConnection=True).admin.command("ping")
    assert response["ok"] == 1


async def test_unit_is_running_as_replica_set(ops_test: OpsTest) -> None:
    """Verify we can connect to all units with the replica set flag."""
    # connect to all units
    client = replica_set_client(ops_test)

    # check mongo replica set is ready
    try:
        client.server_info()
    except ServerSelectionTimeoutError:
        assert False, "server is not ready"

    # close connection
    client.close()

#
# async def test_leader_is_primary_on_deployment(ops_test: OpsTest) -> None:
#     """Tests that right after deployment that the primary unit is the leader."""
#     # grab leader unit
#     leader_unit = await find_leader_unit(ops_test)
#     print("This is the leader unit ", vars(leader_unit))
#
#     # verify that we have a leader
#     assert leader_unit is not None, "No unit is leader"
#
#     # use unit id to grab ip address
#     status = await ops_test.model.get_status()  # noqa: F821
#     unit_id = leader_unit["entity_id"].split("/")[1]
#     leader_ip = status["applications"][APP_NAME]["units"][f"{APP_NAME}/{unit_id}"]["address"]
#
#     # identify primary replica
#     unit_ips = [status["applications"][APP_NAME]["units"]
#                 [f"{APP_NAME}/{unit_id}"]["address"] for unit_id in UNIT_IDS]
#     print("these are the unit ips ", unit_ips)
#     primary_ip = primary_replica(unit_ips)
#
#     # verify primary status
#     assert leader_ip == primary_ip, "Leader is not primary"
