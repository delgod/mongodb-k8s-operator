# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest import mock
from unittest.mock import patch

from ops.model import ActiveStatus, ModelError
from ops.pebble import APIError, ExecError, PathError, ProtocolError
from ops.testing import Harness
from pymongo.errors import ConfigurationError, ConnectionFailure, OperationFailure

from charm import MongoDBCharm
from tests.unit.helpers import patch_network_get

PYMONGO_EXCEPTIONS = [
    (ConnectionFailure("error message"), ConnectionFailure),
    (ConfigurationError("error message"), ConfigurationError),
    (OperationFailure("error message"), OperationFailure),
]


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

    @patch("charm.MongoDBCharm._set_keyfile")
    def test_pebble_ready_cannot_retrieve_container(self, set_keyfile):
        """Test verifies behavior when retrieving container results in ModelError in pebble ready.

        Verifies that when a failure to get a container occurs, that that failure is raised and
        that no efforts to set keyFile or add/replan layers are made.
        """
        # presets
        self.harness.set_leader(True)
        mock_container = mock.Mock()
        mock_container.side_effect = ModelError
        self.harness.charm.unit.get_container = mock_container

        with self.assertRaises(ModelError):
            self.harness.charm.on.mongod_pebble_ready.emit(mock_container)

        set_keyfile.assert_not_called()
        mock_container.add_layer.assert_not_called()
        mock_container.replan.assert_not_called()

    @patch("charm.MongoDBCharm._set_keyfile")
    def test_pebble_ready_container_cannot_connect(self, set_keyfile):
        """Test verifies behavior when cannot connect to container in pebble ready function.

        Verifies that when a failure to connect to container results in a deferral and that no
        efforts to set keyFile or add/replan layers are made.
        """
        # presets
        self.harness.set_leader(True)
        mock_container = mock.Mock()
        mock_container.return_value.can_connect.return_value = False
        self.harness.charm.unit.get_container = mock_container

        set_keyfile.assert_not_called()
        mock_container.add_layer.assert_not_called()
        mock_container.replan.assert_not_called()

    @patch("charm.MongoDBCharm._set_keyfile")
    def test_pebble_ready_set_keyfile_failure(self, set_keyfile):
        """Test verifies behavior when setting keyfile fails.

        Verifies that when a failure to set keyfile occurs that there is no attempt to add layers
        or replan the container.
        """
        # presets
        self.harness.set_leader(True)
        mock_container = mock.Mock()
        mock_container.return_value.can_connect.return_value = True
        self.harness.charm.unit.get_container = mock_container

        for exception in [PathError, ProtocolError]:
            set_keyfile.side_effect = exception
            mock_container.add_layer.assert_not_called()
            mock_container.replan.assert_not_called()

    @patch("charm.MongoDBProvider")
    @patch("charm.MongoDBCharm._init_user")
    @patch("charm.MongoDBConnection")
    def test_start_cannot_retrieve_container(self, connection, init_user, provider):
        """Verifies that failures to get container result in a ModelError being raised.

        Further this function verifies that on error no attempts to set up the replica set or
        database users are made.
        """
        # presets
        self.harness.set_leader(True)
        mock_container = mock.Mock()
        mock_container.side_effect = ModelError
        self.harness.charm.unit.get_container = mock_container
        with self.assertRaises(ModelError):
            self.harness.charm.on.start.emit()

        # when cannot retrieve a container we should not set up the replica set or handle users
        connection.return_value.__enter__.return_value.init_replset.assert_not_called()
        init_user.assert_not_called()
        provider.return_value.oversee_users.assert_not_called()

        # verify app data
        self.assertEqual("db_initialised" in self.harness.charm.app_data, False)

    @patch("charm.MongoDBProvider")
    @patch("charm.MongoDBCharm._init_user")
    @patch("charm.MongoDBConnection")
    def test_start_container_cannot_connect(self, connection, init_user, provider):
        """Tests inability to connect results in deferral.

        Verifies that if connection is not possible, that there are no attempts to set up the
        replica set or handle users.
        """
        # presets
        self.harness.set_leader(True)
        mock_container = mock.Mock()
        mock_container.return_value.can_connect.return_value = False
        self.harness.charm.unit.get_container = mock_container

        self.harness.charm.on.start.emit()

        # when cannot connect to container we should not set up the replica set or handle users
        connection.return_value.__enter__.return_value.init_replset.assert_not_called()
        init_user.assert_not_called()
        provider.return_value.oversee_users.assert_not_called()

        # verify app data
        self.assertEqual("db_initialised" in self.harness.charm.app_data, False)

    @patch("charm.MongoDBProvider")
    @patch("charm.MongoDBCharm._init_user")
    @patch("charm.MongoDBConnection")
    def test_start_container_does_not_exist(self, connection, init_user, provider):
        """Tests lack of existence of files on container results in deferral.

        Verifies that if files do not exists, that there are no attempts to set up the replica set
        or handle users.
        """
        # presets
        self.harness.set_leader(True)
        mock_container = mock.Mock()
        mock_container.return_value.can_connect.return_value = True
        mock_container.return_value.exists.return_value = False
        self.harness.charm.unit.get_container = mock_container

        self.harness.charm.on.start.emit()

        # when container does not exist we should not set up the replica set or handle users
        connection.return_value.__enter__.return_value.init_replset.assert_not_called()
        init_user.assert_not_called()
        provider.return_value.oversee_users.assert_not_called()

        # verify app data
        self.assertEqual("db_initialised" in self.harness.charm.app_data, False)

    @patch("charm.MongoDBProvider")
    @patch("charm.MongoDBCharm._init_user")
    @patch("charm.MongoDBConnection")
    def test_start_container_exists_fails(self, connection, init_user, provider):
        """Tests failure in checking file existence on container raises an APIError.

        Verifies that when checking container files raises an API Error, we raise that same error
        and make no attempts to set up the replica set or handle users.
        """
        # presets
        self.harness.set_leader(True)
        mock_container = mock.Mock()
        mock_container.return_value.can_connect.return_value = True
        mock_container.return_value.exists.side_effect = APIError("body", 0, "status", "message")
        self.harness.charm.unit.get_container = mock_container

        with self.assertRaises(APIError):
            self.harness.charm.on.start.emit()

        # when container does not exist we should not set up the replica set or handle users
        connection.return_value.__enter__.return_value.init_replset.assert_not_called()
        init_user.assert_not_called()
        provider.return_value.oversee_users.assert_not_called()

        # verify app data
        self.assertEqual("db_initialised" in self.harness.charm.app_data, False)

    @patch("charm.MongoDBProvider")
    @patch("charm.MongoDBCharm._init_user")
    @patch("charm.MongoDBConnection")
    def test_start_already_initialised(self, connection, init_user, provider):
        """Tests that if the replica set has already been set up that we return.

        Verifies that if the replica set is already set up that no attempts to set it up again are
        made and that there are no attempts to set up users.
        """
        # presets
        self.harness.set_leader(True)

        mock_container = mock.Mock()
        mock_container.return_value.can_connect.return_value = True
        mock_container.return_value.exists.return_value = True
        self.harness.charm.unit.get_container = mock_container

        self.harness.charm.app_data["db_initialised"] = "True"

        self.harness.charm.on.start.emit()

        # when the database has already been initialised we should not set up the replica set or
        # handle users
        connection.return_value.__enter__.return_value.init_replset.assert_not_called()
        init_user.assert_not_called()
        provider.return_value.oversee_users.assert_not_called()

    @patch("charm.MongoDBProvider")
    @patch("charm.MongoDBCharm._init_user")
    @patch("charm.MongoDBConnection")
    def test_start_mongod_not_ready(self, connection, init_user, provider):
        """Tests that if mongod is not ready that we defer and return.

        Verifies that if mongod is not ready that no attempts to set up the replica set and set up
        users are made.
        """
        # presets
        self.harness.set_leader(True)

        mock_container = mock.Mock()
        mock_container.return_value.can_connect.return_value = True
        mock_container.return_value.exists.return_value = True
        self.harness.charm.unit.get_container = mock_container

        connection.return_value.__enter__.return_value.is_ready = False

        self.harness.charm.on.start.emit()

        # when mongod is not ready we should not set up the replica set or handle users
        connection.return_value.__enter__.return_value.init_replset.assert_not_called()
        init_user.assert_not_called()
        provider.return_value.oversee_users.assert_not_called()

        # verify app data
        self.assertEqual("db_initialised" in self.harness.charm.app_data, False)

    @patch("charm.MongoDBProvider")
    @patch("charm.MongoDBCharm._init_user")
    @patch("charm.MongoDBConnection")
    def test_start_mongod_error_initalising_replica_set(self, connection, init_user, provider):
        """Tests that failure to initialise replica set is properly handled.

        Verifies that when there is a failure to initialise replica set that no operations related
        to setting up users are executed.
        """
        # presets
        self.harness.set_leader(True)

        mock_container = mock.Mock()
        mock_container.return_value.can_connect.return_value = True
        mock_container.return_value.exists.return_value = True
        self.harness.charm.unit.get_container = mock_container
        connection.return_value.__enter__.return_value.is_ready = True

        for exception, expected_raise in PYMONGO_EXCEPTIONS:
            connection.return_value.__enter__.return_value.init_replset.side_effect = exception
            self.harness.charm.on.start.emit()

            init_user.assert_not_called()
            provider.return_value.oversee_users.assert_not_called()

            # verify app data
            self.assertEqual("db_initialised" in self.harness.charm.app_data, False)

    @patch("charm.MongoDBProvider")
    @patch("charm.MongoDBCharm._init_user")
    @patch("charm.MongoDBConnection")
    def test_start_mongod_error_initalising_user(self, connection, init_user, provider):
        """Tests that failure to initialise users set is properly handled.

        Verifies that when there is a failure to initialise users that overseeing users is not
        called.
        """
        # presets
        self.harness.set_leader(True)

        mock_container = mock.Mock()
        mock_container.return_value.can_connect.return_value = True
        mock_container.return_value.exists.return_value = True
        self.harness.charm.unit.get_container = mock_container
        connection.return_value.__enter__.return_value.is_ready = True

        init_user.side_effect = ExecError("command", 0, "stdout", "stderr")
        self.harness.charm.on.start.emit()

        provider.return_value.oversee_users.assert_not_called()

        # verify app data
        self.assertEqual("db_initialised" in self.harness.charm.app_data, False)

    @patch("charm.MongoDBProvider")
    @patch("charm.MongoDBCharm._init_user")
    @patch("charm.MongoDBConnection")
    def test_start_mongod_error_overseeing_users(self, connection, init_user, provider):
        """Tests failures related to pymongo are properly handled when overseeing users.

        Verifies that when there is a failure to oversee users that we defer and do not set the
        data base to initialised.
        """
        # presets
        self.harness.set_leader(True)

        mock_container = mock.Mock()
        mock_container.return_value.can_connect.return_value = True
        mock_container.return_value.exists.return_value = True
        self.harness.charm.unit.get_container = mock_container
        connection.return_value.__enter__.return_value.is_ready = True

        for exception, expected_raise in PYMONGO_EXCEPTIONS:
            provider.side_effect = exception
            self.harness.charm.on.start.emit()

            provider.return_value.oversee_users.assert_not_called()

            # verify app data
            self.assertEqual("db_initialised" in self.harness.charm.app_data, False)
