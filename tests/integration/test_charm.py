#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import json
import logging
from pathlib import Path

import pytest
import yaml
from pymongo import MongoClient
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]


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
    status = await ops_test.model.get_status()  # noqa: F821
    address = status["applications"][APP_NAME]["units"][f"{APP_NAME}/0"]["address"]
    response = MongoClient(address, directConnection=True).admin.command("ping")
    assert response["ok"] == 1


@pytest.mark.abort_on_fail
async def test_application_is_up_internally(ops_test: OpsTest):
    status = await ops_test.model.get_status()  # noqa: F821
    address = status["applications"][APP_NAME]["units"][f"{APP_NAME}/0"]["address"]
    action = await ops_test.model.units.get(f"{APP_NAME}/0").run_action("get-admin-password")
    action = await action.wait()
    password = action.results["admin-password"]

    mongo_op = "rs.status()"
    mongo_cmd = (
        f"mongo --quiet --eval 'JSON.stringify({mongo_op})' "
        f"mongodb://operator:{password}@{address}/admin"
    )
    kubectl_cmd = (
        "microk8s",
        "kubectl",
        "run",
        "--rm",
        "-i",
        "-q",
        "--restart=Never",
        "--command",
        f"--namespace={ops_test.model_name}",
        "mongo-test",
        "--image=mongo:4.4",
        "--",
        "sh",
        "-c",
        mongo_cmd,
    )

    ret_code, stdout, stderr = await ops_test.run(*kubectl_cmd)
    logger.info("code %r; stdout %r; stderr: %r", ret_code, stdout, stderr)
    responce_obj = json.loads(stdout)
    primary = [
        member["name"] for member in responce_obj["members"] if member["stateStr"] == "PRIMARY"
    ][0]
    assert primary == "mongodb-k8s-0.mongodb-k8s-endpoints:27017"
