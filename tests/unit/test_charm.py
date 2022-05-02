# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from ops.model import ActiveStatus, WaitingStatus
from ops.testing import Harness

from charm import MongoDBCharm
from tests.unit.helpers import patch_network_get
from unittest.mock import patch
import unittest


class TestCharm(unittest.TestCase):
    @patch_network_get(private_address="1.1.1.1")
    def setUp(self):
        self.harness = Harness(MongoDBCharm)
        mongo_resource = {
            "registrypath": "mongo:4.4",
        }
        self.harness.add_oci_resource("mongodb-image", mongo_resource)
        self.harness.begin()
        self.harness.add_relation("database-peers", "mongodb-peers")
        self.harness.set_leader(True)
        self.charm = self.harness.charm
        self.addCleanup(self.harness.cleanup)

    def test_mongod_pebble_ready(self):
        # Expected plan after Pebble ready with default config
        expected_plan = {
            "services": {
                "mongod": {
                    "user": "mongodb",
                    "group": "mongodb",
                    "override": "replace",
                    "summary": "mongod",
                    "command": (
                        "mongod --bind_ip_all --auth "
                        "--replSet=mongodb-k8s "
                        "--clusterAuthMode=keyFile "
                        "--keyFile=/etc/mongodb/keyFile"
                    ),
                    "startup": "enabled",
                }
            },
        }
        # Get the mongod container from the model
        container = self.harness.model.unit.get_container("mongod")
        self.harness.set_can_connect(container, True)
        # Emit the PebbleReadyEvent carrying the mongod container
        self.harness.charm.on.mongod_pebble_ready.emit(container)
        # Get the plan now we've run PebbleReady
        updated_plan = self.harness.get_container_pebble_plan("mongod").to_dict()
        # Check we've got the plan we expected
        assert expected_plan == updated_plan
        # Check the service was started
        service = self.harness.model.unit.get_container("mongod").get_service("mongod")
        assert service.is_running()
        # Ensure we set an ActiveStatus with no message
        assert self.harness.model.unit.status == ActiveStatus()

    # @patch("lib.charms.mongodb_libs.v0.mongodb.MongoClient")
    # def test_start_mongo_failure(self, mongodb_client):
    #     """Test verifies operation of start hook when ready check fails."""
    #
    #     # presets
    #     self.harness.set_leader(True)
    #     container = harness.model.unit.get_container("mongod")
    #     harness.set_can_connect(container, True)
    #     harness.set_exists(container, True)
    #
    #     self.harness.charm.on.start.emit()
    #
    #     # failure is mongodb ready
    #     mongodb_client.is_replica_ready.assert_called()
    #
    #     # mongodb_client.init_replset.assert_not_called()
    #     # mongodb_client.init_user.assert_not_called()
    #     # mongodb_client.oversee_users.assert_not_called()
    #     #
    #     # # verify app data
