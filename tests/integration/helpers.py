# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
import json
import ops
import yaml
from pathlib import Path
from pytest_operator.plugin import OpsTest
import string
import random

from tenacity import (
    retry,
    stop_after_delay,
    stop_after_attempt,
    wait_fixed,
    before_log,
    RetryError,
    Retrying,
)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
ADMIN_USER = "operator"
APP_NAME = METADATA["name"]
UNIT_IDS = [0, 1, 2]
PORT = 27017


async def get_password(ops_test: OpsTest, unit_id: int) -> str:
    """Use the charm action to retrieve the password.
    Return:
        String with the password stored on the peer relation databag.
    """
    action = await ops_test.model.units.get(f"{APP_NAME}/{unit_id}").run_action(
        "get-password"
    )
    password = await action.wait()
    return password.results["password"]


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


async def get_address_of_unit(ops_test: OpsTest, unit_id: int) -> str:
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][APP_NAME]["units"][f"{APP_NAME}/{unit_id}"]["address"]

# retry to give time for server to retrieve request


@retry(
    stop=stop_after_attempt(10),
    wait=wait_fixed(3),
    reraise=True,
)
async def run_mongod_command(ops_test: OpsTest, mongo_op: str) -> str:
    unit_id = 0
    password = await get_password(ops_test, unit_id)
    address = await get_address_of_unit(ops_test, unit_id)
    mongo_cmd = (
        f"mongo --quiet --eval 'JSON.stringify({mongo_op})' "
        f"mongodb://operator:{password}@{address}/admin"
    )
    print(mongo_cmd)

    # randomise container name so that it doesn't connect to an old one
    key = "".join([random.choice(string.ascii_letters) for _ in range(8)])
    key = key.lower()
    container_name = f"mongo-test-{key}"
    print(container_name)

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
        container_name,
        "--image=mongo:4.4",
        "--",
        "sh",
        "-c",
        mongo_cmd,
    )

    ret_code, stdout, stderr = await ops_test.run(*kubectl_cmd)
    print(ret_code, stdout, stderr)
    responce_obj = json.loads(stdout)
    return responce_obj
