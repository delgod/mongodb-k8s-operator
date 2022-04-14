#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
from pathlib import Path

import pytest
import yaml
from pymongo import MongoClient
from pytest_operator.plugin import OpsTest
from helpers import pull_content_from_unit_file

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
UNIT_IDS = [0, 1, 2]


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
    unit = ops_test.model.applications[f"{APP_NAME}"].units[unit_id]

    # verify mongod on this unit is responding
    logger.info("querying address: %s", unit.public_address)
    response = MongoClient(unit.public_address, directConnection=True).admin.command("ping")
    assert response["ok"] == 1


@pytest.mark.parametrize("unit_id", UNIT_IDS)
async def test_config_files_are_correct(ops_test: OpsTest, unit_id: int) -> None:
    """Tests that mongo.conf as expected content."""
    # Get the expected contents from files.
    with open("tests/data/mongod.conf") as file:
        expected_mongodb_conf = file.read()

    # Pull the configuration files from MongoDB instance.
    unit = ops_test.model.applications[f"{APP_NAME}"].units[unit_id]

    # Check that the conf settings are as expected.
    unit_mongodb_conf_data = await pull_content_from_unit_file(unit, "/etc/mongod.conf")
    expected_mongodb_conf = update_bind_ip(expected_mongodb_conf, unit.public_address)
    assert expected_mongodb_conf == unit_mongodb_conf_data
