#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
from datetime import datetime

from pathlib import Path
import yaml
import ops
from pytest_operator.plugin import OpsTest
from tenacity import RetryError, Retrying, stop_after_attempt, wait_exponential

from tests.integration.helpers import get_password

PORT = 27017
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]


class ProcessError(Exception):
    """Raised when a process fails."""


async def mongo_tls_command(ops_test: OpsTest) -> str:
    """Generates a command which verifies TLS status."""
    replica_set_hosts = [unit.public_address for unit in ops_test.model.applications[APP_NAME].units]
    password = await get_password(ops_test, APP_NAME)
    hosts = ",".join(replica_set_hosts)
    replica_set_uri = f"mongodb://admin:" f"{password}@" f"{hosts}/admin?replicaSet={APP_NAME}"

    return (
        f"mongo '{replica_set_uri}'  --eval 'rs.status()'"
        f" --tls --tlsCAFile /etc/mongodb/external-ca.crt"
        f" --tlsCertificateKeyFile /etc/mongodb/external-cert.pem"
    )


async def check_tls(ops_test: OpsTest, unit: ops.model.Unit, enabled: bool) -> bool:
    """Returns whether TLS is enabled on the specific PostgreSQL instance.

    Args:
        ops_test: The ops test framework instance.
        unit: The unit to be checked.
        enabled: check if TLS is enabled/disabled

    Returns:
        Whether TLS is enabled/disabled.
    """
    try:
        for attempt in Retrying(
            stop=stop_after_attempt(10), wait=wait_exponential(multiplier=1, min=2, max=30)
        ):
            with attempt:
                return_code = await run_tls_check(ops_test, unit)
                tls_enabled = return_code == 0
                if enabled != tls_enabled:
                    raise ValueError(
                        f"TLS is{' not' if not tls_enabled else ''} enabled on {unit.name}"
                    )
                return True
    except RetryError:
        return False

def parse_hostname(hostname:str) -> str:
    """Parses a hostname to the corresponding enpoint version."""
    return hostname.replace("/","-") + ".mongodb-k8s-endpoints"


async def run_tls_check(ops_test: OpsTest, unit: ops.model.Unit) -> int:
    """Returns the return code of the TLS check."""
    hosts = [parse_hostname(unit.name) for unit in ops_test.model.applications[APP_NAME].units]
    hosts = ",".join(hosts)
    password = await get_password(ops_test, unit_id=0)
    mongo_uri = f"mongodb://operator:{password}@{hosts}/admin?"

    mongo_cmd = (f"/usr/bin/mongosh {mongo_uri} --eval 'rs.status()'"
        f" --tls --tlsCAFile /etc/mongodb/external-ca.crt"
        f" --tlsCertificateKeyFile /etc/mongodb/external-cert.pem"
    )

    complete_command = f"ssh --container mongod {unit.name} {mongo_cmd}"
    ret_code, _, _ = await ops_test.juju(*complete_command.split())

    return ret_code
    

async def time_file_created(ops_test: OpsTest, unit_name: str, path: str) -> int:
    """Returns the unix timestamp of when a file was created on a specified unit."""
    time_cmd = f"run --unit {unit_name} --  ls -l --time-style=full-iso {path} "
    return_code, ls_output, _ = await ops_test.juju(*time_cmd.split())

    if return_code != 0:
        raise ProcessError(
            "Expected time command %s to succeed instead it failed: %s", time_cmd, return_code
        )

    return process_ls_time(ls_output)


async def time_process_started(ops_test: OpsTest, unit_name: str, process_name: str) -> int:
    """Retrieves the time that a given process started according to systemd."""
    time_cmd = (
        f"run --unit {unit_name} --  systemctl show {process_name} --property=ActiveEnterTimestamp"
    )
    return_code, systemctl_output, _ = await ops_test.juju(*time_cmd.split())

    if return_code != 0:
        raise ProcessError(
            "Expected time command %s to succeed instead it failed: %s", time_cmd, return_code
        )

    return process_systemctl_time(systemctl_output)


def process_ls_time(ls_output):
    """Parse time representation as returned by the 'ls' command."""
    time_as_str = "T".join(ls_output.split("\n")[0].split(" ")[5:7])
    # further strip down additional milliseconds
    time_as_str = time_as_str[0:-3]
    d = datetime.strptime(time_as_str, "%Y-%m-%dT%H:%M:%S.%f")
    return d


def process_systemctl_time(systemctl_output):
    """Parse time representation as returned by the 'systemctl' command."""
    "ActiveEnterTimestamp=Thu 2022-09-22 10:00:00 UTC"
    time_as_str = "T".join(systemctl_output.split("=")[1].split(" ")[1:3])
    d = datetime.strptime(time_as_str, "%Y-%m-%dT%H:%M:%S")
    return d
