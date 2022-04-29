# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from pymongo.errors import ConfigurationError, ConnectionFailure, OperationFailure
from tenacity import RetryError

from lib.charms.mongodb_libs.v0.mongodb import MongoDBConfiguration, MongoDBConnection

MONGO_CONFIG = {
    "replset": "mongo-k8s",
    "database": "admin",
    "username": "operator",
    "password": "password",
    "hosts": set(["1.1.1.1", "2.2.2.2"]),
}

PYMONGO_EXCEPTIONS = [
    (ConnectionFailure("error message"), ConnectionFailure),
    (ConfigurationError("error message"), ConfigurationError),
    (OperationFailure("error message"), OperationFailure),
]


class TestMongoServer(unittest.TestCase):
    # def mongodb_config(self) -> MongoDBConfiguration:
    #     """TODO."""
    #     return MongoDBConfiguration(
    #         replset="mongo-k8s",
    #         database="admin",
    #         username="operator",
    #         password="password",
    #         hosts=set(["1.1.1.1", "2.2.2.2"])
    #     )

    @patch("lib.charms.mongodb_libs.v0.mongodb.MongoClient")
    @patch("lib.charms.mongodb_libs.v0.mongodb.MongoDBConfiguration")
    def test_is_ready_error_handling(self, config, mock_client):
        """Test on failure to check ready of replica returns False.

        Test also verifies that when an exception is raised we still close the client connection.
        """

        for exception, expected_raise in PYMONGO_EXCEPTIONS:
            with MongoDBConnection(config) as mongo:
                mock_client.admin.command.side_effect = exception

                #  verify ready is false when an error occurs
                ready = mongo.is_ready
                self.assertEqual(ready, False)

                # verify we close connection
                (mock_client.close).assert_called()
