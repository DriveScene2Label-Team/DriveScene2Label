import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from environment import Environment
from templates import BUILDERS
from kubernetes import resources


class LifecycleSafetyTests(unittest.TestCase):
    def setUp(self):
        self.environment = Environment.__new__(Environment)
        self.environment.project = "ds2l"
        self.environment.region = "ap-northeast-2"
        self.environment.foundation = {"AppRepository": "example/ds2l-app", "AiRepository": "example/ds2l-ai"}
        self.rds = Mock()
        self.environment.clients = {"rds": self.rds}
        self.environment.database = Mock(return_value={"DBInstanceIdentifier": "ds2l-database", "EngineVersion": "16.11"})
        self.environment.read_control = Mock(return_value=({"ever_started": True}, '"etag"'))
        self.environment.write_control = Mock()
        self.environment.verify_snapshot = Mock()

    def test_snapshot_failure_never_deletes_database(self):
        self.rds.create_db_snapshot.side_effect = RuntimeError("snapshot failed")
        with self.assertRaisesRegex(RuntimeError, "snapshot failed"):
            self.environment.snapshot_and_delete_database()
        self.rds.delete_db_instance.assert_not_called()

    @patch("environment.wait_until")
    def test_snapshot_verification_failure_never_deletes_database(self, wait):
        self.environment.verify_snapshot.side_effect = RuntimeError("not encrypted")
        with self.assertRaisesRegex(RuntimeError, "not encrypted"):
            self.environment.snapshot_and_delete_database()
        self.rds.delete_db_instance.assert_not_called()

    @patch("environment.wait_until")
    def test_recovery_record_failure_never_deletes_database(self, wait):
        self.environment.write_control.side_effect = RuntimeError("S3 unavailable")
        with self.assertRaisesRegex(RuntimeError, "S3 unavailable"):
            self.environment.snapshot_and_delete_database()
        self.rds.delete_db_instance.assert_not_called()

    @patch("environment.wait_until")
    def test_readback_mismatch_never_deletes_database(self, wait):
        self.environment.read_control.side_effect = [({"ever_started": True}, '"etag"'), ({"snapshot": "old-snapshot"}, '"etag2"')]
        with self.assertRaisesRegex(RuntimeError, "not persisted"):
            self.environment.snapshot_and_delete_database()
        self.rds.delete_db_instance.assert_not_called()

    @patch("environment.wait_until")
    def test_success_deletes_only_after_verified_durable_recovery(self, wait):
        events, durable = [], {}
        self.environment.verify_snapshot.side_effect = lambda snapshot: events.append("verified")
        def save(key, state, **kwargs):
            durable.update(copy.deepcopy(state))
            events.append("saved")
        self.environment.write_control.side_effect = save
        self.environment.read_control.side_effect = lambda key: (copy.deepcopy(durable), '"etag"')
        self.rds.delete_db_instance.side_effect = lambda **kwargs: events.append("deleted")
        self.environment.snapshot_and_delete_database()
        self.assertEqual(events, ["verified", "saved", "deleted"])
        self.assertTrue(durable["snapshot"].startswith("ds2l-"))
        self.rds.delete_db_snapshot.assert_not_called()

    def test_previous_database_without_snapshot_cannot_be_replaced(self):
        self.environment.database.return_value = None
        self.environment.read_control.side_effect = [({"app": "app-image"}, "etag"), ({"ever_started": True, "snapshot": None}, "etag")]
        self.environment.deploy_stack = Mock()
        with self.assertRaisesRegex(RuntimeError, "empty replacement"):
            self.environment.start(with_gpu=False)
        self.environment.deploy_stack.assert_not_called()

    def test_off_push_records_image_without_creating_compute(self):
        self.environment.read_control.return_value = ({}, "etag")
        self.environment.stack = Mock(return_value=None)
        self.environment.deploy_stack = Mock()
        self.environment.install_application = Mock()
        self.environment.drain = Mock()
        self.environment.publish("app", "example/ds2l-app@sha256:" + "a" * 64)
        self.environment.write_control.assert_called_once()
        self.environment.deploy_stack.assert_not_called()
        self.environment.install_application.assert_not_called()
        self.environment.drain.assert_not_called()

    def test_partial_push_never_creates_missing_compute(self):
        self.environment.read_control.return_value = ({}, "etag")
        self.environment.stack = Mock(side_effect=lambda component: None if component == "app" else {"StackStatus": "CREATE_COMPLETE"})
        self.environment.deploy_stack = Mock()
        with self.assertRaisesRegex(RuntimeError, "partially running"):
            self.environment.publish("app", "example/ds2l-app@sha256:" + "b" * 64)
        self.environment.deploy_stack.assert_not_called()

    def test_foundation_deletion_is_not_an_allowed_lifecycle_operation(self):
        with self.assertRaisesRegex(ValueError, "Persistent foundation"):
            self.environment.delete_stack("foundation")

    def test_cpu_start_and_gpu_stop_keep_pending_jobs_unclaimed(self):
        self.environment.stack = Mock(return_value={"Parameters": [{"ParameterKey": "AppImage", "ParameterValue": "current-image"}]})
        self.environment.outputs = Mock(return_value={"DatabaseHost": "private-database"})
        self.environment.deploy_stack = Mock()
        self.environment.set_workers(False)
        component, parameters = self.environment.deploy_stack.call_args.args
        self.assertEqual(component, "app")
        self.assertEqual(parameters["AppImage"], "current-image")
        self.assertEqual(parameters["WorkerEnabled"], "false")

    @patch("environment.run")
    def test_mismatched_eks_image_is_rejected(self, run):
        import json
        self.environment.foundation["Cluster"] = "ds2l-ecs"
        ecs = Mock()
        self.environment.clients["ecs"] = ecs
        ecs.describe_services.return_value = {"services": [{"taskDefinition": "task-arn"}]}
        ecs.describe_task_definition.return_value = {"taskDefinition": {"containerDefinitions": [{"name": "app", "image": "expected@digest"}]}}
        run.return_value.stdout = json.dumps({"spec": {"template": {"spec": {"containers": [{"name": "app", "image": "other@digest"}]}}}})
        with self.assertRaisesRegex(RuntimeError, "expected image digest"):
            self.environment.verify_application_image("expected@digest")

    def test_snapshot_source_and_encryption_are_required(self):
        environment = Environment.__new__(Environment)
        environment.project = "ds2l"
        environment.clients = {"rds": self.rds}
        for source, encrypted, status in [("other-database", True, "available"), ("ds2l-database", False, "available"), ("ds2l-database", True, "creating")]:
            with self.subTest(source=source, encrypted=encrypted, status=status):
                self.rds.describe_db_snapshots.return_value = {"DBSnapshots": [{"DBInstanceIdentifier": source, "Encrypted": encrypted, "Status": status}]}
                with self.assertRaises(RuntimeError):
                    environment.verify_snapshot("snapshot")


class InfrastructureContractTests(unittest.TestCase):
    def test_public_gateway_requires_invited_team_members_and_secure_sessions(self):
        foundation = BUILDERS["foundation"]()["Resources"]
        self.assertTrue(foundation["TeamUsers"]["Properties"]["AdminCreateUserConfig"]["AllowAdminCreateUserOnly"])
        self.assertEqual(foundation["TeamUsers"]["DeletionPolicy"], "Retain")
        gateway = BUILDERS["web"]()["Resources"]["Gateway"]["Properties"]["PrimaryContainer"]
        settings = {item["Name"]: item["Value"] for item in gateway["Environment"]}
        self.assertEqual(settings["OAUTH2_PROXY_ALLOWED_GROUPS"], "team")
        self.assertEqual(settings["OAUTH2_PROXY_INSECURE_OIDC_SKIP_NONCE"], "false")
        self.assertEqual(settings["OAUTH2_PROXY_CODE_CHALLENGE_METHOD"], "S256")
        self.assertEqual(settings["OAUTH2_PROXY_COOKIE_SECURE"], "true")
        self.assertNotIn("OAUTH2_PROXY_SKIP_AUTH_ROUTES", settings)
        self.assertNotIn("OAUTH2_PROXY_CLIENT_SECRET", settings)
        self.assertNotIn("OAUTH2_PROXY_COOKIE_SECRET", settings)
        self.assertEqual(len(gateway["Secrets"]), 2)

    def test_data_resources_survive_stack_deletion_and_have_no_expiration(self):
        foundation = BUILDERS["foundation"]()["Resources"]
        for key in ["DataBucket", "AdminSecret", "AppSecret", "OperationsSecret", "AppRepository", "AiRepository"]:
            self.assertEqual(foundation[key]["DeletionPolicy"], "Retain")
            self.assertEqual(foundation[key]["UpdateReplacePolicy"], "Retain")
        self.assertNotIn("LifecycleConfiguration", foundation["DataBucket"]["Properties"])
        self.assertNotIn("LifecyclePolicy", foundation["AppRepository"]["Properties"])
        self.assertEqual(BUILDERS["database"]()["Resources"]["Database"]["DeletionPolicy"], "Retain")

    def test_ingress_only_references_security_groups(self):
        for builder in BUILDERS.values():
            for value in builder()["Resources"].values():
                if value["Type"] == "AWS::EC2::SecurityGroupIngress":
                    self.assertIn("SourceSecurityGroupId", value["Properties"])
                    self.assertNotIn("CidrIp", value["Properties"])

    def test_only_ecs_runs_workers_and_eks_uses_secret_references(self):
        foundation = {"DataBucket": "bucket", "AppSecret": "app-secret-arn", "OperationsSecret": "ops-secret-arn"}
        manifest = resources("ds2l", "ap-northeast-2", foundation, "database.internal", "image@sha256:digest")
        deployment = next(item for item in manifest if item["kind"] == "Deployment")
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        env = {item["name"]: item["value"] for item in container["env"]}
        self.assertEqual(container["image"], "image@sha256:digest")
        self.assertEqual(env["AUTO_LABEL_WORKER_ENABLED"], "false")
        self.assertEqual(env["RECORDING_WORKER_ENABLED"], "false")
        self.assertNotIn("DB_PASSWORD", env)
        ecs = BUILDERS["app"]()["Resources"]["Task"]["Properties"]["ContainerDefinitions"][0]
        ecs_env = {item["Name"]: item["Value"] for item in ecs["Environment"]}
        self.assertEqual(ecs_env["AUTO_LABEL_WORKER_ENABLED"], {"Ref": "WorkerEnabled"})
        self.assertEqual(BUILDERS["app"]()["Parameters"]["WorkerEnabled"]["Default"], "false")
        self.assertEqual(ecs_env["RECORDING_WORKER_ENABLED"], "false")


if __name__ == "__main__":
    unittest.main()
