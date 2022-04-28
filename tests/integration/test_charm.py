#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import pytest
from helpers import APP_NAME, METADATA, get_address_of_unit, run_mongo_op
from pymongo import MongoClient
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    resources = {"mongodb-image": METADATA["resources"]["mongodb-image"]["upstream-source"]}
    await ops_test.model.deploy(charm, resources=resources, application_name=APP_NAME)

    # issuing dummy update_status just to trigger an event
    await ops_test.model.set_config({"update-status-hook-interval": "10s"})

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )
    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"

    # effectively disable the update status from firing
    await ops_test.model.set_config({"update-status-hook-interval": "60m"})


@pytest.mark.abort_on_fail
async def test_application_is_up(ops_test: OpsTest):
    address = await get_address_of_unit(ops_test)
    response = MongoClient(address, directConnection=True).admin.command("ping")
    assert response["ok"] == 1


@pytest.mark.abort_on_fail
async def test_application_is_up_internally(ops_test: OpsTest):
    response_obj = await run_mongo_op(ops_test, "rs.status()")
    primary = [
        member["name"] for member in response_obj["members"] if member["stateStr"] == "PRIMARY"
    ][0]
    assert primary == "mongodb-k8s-0.mongodb-k8s-endpoints:27017"
