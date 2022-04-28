# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from pathlib import Path

import yaml
from pytest_operator.plugin import OpsTest

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]
logger = logging.getLogger(__name__)


async def get_address_of_unit(ops_test: OpsTest) -> str:
    status = await ops_test.model.get_status()
    return status["applications"][APP_NAME]["units"][f"{APP_NAME}/0"]["address"]


async def get_password(ops_test: OpsTest) -> str:
    action = await ops_test.model.units.get(f"{APP_NAME}/0").run_action("get-admin-password")
    action = await action.wait()
    return action.results["admin-password"]


async def run_mongo_op(ops_test: OpsTest, mongo_op: str):
    address = await get_address_of_unit(ops_test)
    password = await get_password(ops_test)
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
    if ret_code != 0:
        logger.error("code %r; stdout %r; stderr: %r", ret_code, stdout, stderr)
        return None
    return json.loads(stdout)
