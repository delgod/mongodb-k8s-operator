#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
import os

import pytest
from helpers import (
    APP_NAME,
    METADATA,
    UNIT_IDS,
    get_address_of_unit,
    get_leader_id,
    run_mongod_command,
)
from pymongo import MongoClient
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.skipif(
    os.environ.get("PYTEST_SKIP_DEPLOY", False),
    reason="skipping deploy, model expected to be provided.",
)
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest) -> None:
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    resources = {"mongodb-image": METADATA["resources"]["mongodb-image"]["upstream-source"]}
    await ops_test.model.deploy(
        charm, resources=resources, application_name=APP_NAME, num_units=len(UNIT_IDS)
    )

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
    # verify mongod on this unit is responding
    ip_address = await get_address_of_unit(ops_test, unit_id)
    response = MongoClient(ip_address, directConnection=True).admin.command("ping")
    assert response["ok"] == 1


@pytest.mark.abort_on_fail
async def test_application_primary(ops_test: OpsTest):
    """Tests existience of primary and verifies the application is running as a replica set.

    By retrieving information about the primary this test inherently tests password retrieval.
    """

    rs_status = await run_mongod_command(ops_test, "rs.status()")
    assert rs_status, "mongod had no response for 'rs.status()'"

    primary = [
        member["name"] for member in rs_status["members"] if member["stateStr"] == "PRIMARY"
    ][0]

    assert primary, "mongod has no primary on deployment"

    number_of_primaries = 0
    for member in rs_status["members"]:
        if member["stateStr"] == "PRIMARY":
            number_of_primaries += 1

    assert number_of_primaries == 1, "more than one primary in replica set"

    leader_id = await get_leader_id()
    assert (
        primary == f"mongodb-k8s-{leader_id}.mongodb-k8s-endpoints:27017"
    ), "primary not leader on deployment"
