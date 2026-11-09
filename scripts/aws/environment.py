"""Private, on-demand AWS environment. Run only with short-lived AWS credentials.

All mutations share a conditional S3 lock. Stop never deletes a database before
both an available encrypted snapshot and a durable recovery record exist.
"""
import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra" / "aws"))
from templates import BUILDERS
from kubernetes import resources as kubernetes_resources

ACCOUNT = "189750306426"
REGION = "ap-northeast-2"


def log(message):
    print(message, flush=True)


def run(arguments, **kwargs):
    # No shell interpolation and no secret values on the command line.
    return subprocess.run(arguments, check=True, text=True, **kwargs)


def wait_until(description, predicate, timeout=1800, interval=15):
    deadline = time.monotonic() + timeout
    next_log = 0
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        if time.monotonic() >= next_log:
            log("Waiting: " + description)
            next_log = time.monotonic() + 45
        time.sleep(interval)
    raise RuntimeError("Timed out: " + description + "; inspect status before retrying.")


class Environment:
    def __init__(self, project="ds2l", region=REGION):
        if region != REGION or not re.fullmatch(r"[a-z][a-z0-9-]{2,20}", project):
            raise ValueError("This environment is configured for Seoul (ap-northeast-2). Invalid region or project.")
        self.project, self.region = project, region
        session = boto3.Session(region_name=region)
        config = Config(retries={"mode": "standard", "max_attempts": 5}, connect_timeout=10, read_timeout=60)
        self.clients = {name: session.client(name, config=config) for name in
                        ["sts", "cloudformation", "s3", "rds", "ec2", "ecs", "eks", "ssm", "secretsmanager", "iam", "service-quotas"]}
        identity = self.clients["sts"].get_caller_identity()
        self.identity_arn = identity["Arn"]
        if identity["Account"] != ACCOUNT:
            raise RuntimeError(f"Expected project account {ACCOUNT}, received {identity['Account']}; do not deploy in the management account.")
        self.foundation = self.outputs("foundation")
        self.bucket = f"{project}-{ACCOUNT}-{region}-data"

    def stack(self, component):
        try:
            return self.clients["cloudformation"].describe_stacks(StackName=f"{self.project}-{component}")["Stacks"][0]
        except ClientError as error:
            if error.response["Error"]["Code"] == "ValidationError" and "does not exist" in error.response["Error"]["Message"]:
                return None
            raise

    def outputs(self, component):
        stack = self.stack(component)
        return {item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])} if stack else {}

    def deploy_stack(self, component, values):
        body = BUILDERS[component]()
        supplied = {"Project": self.project, **values}
        parameters = []
        for key, spec in body["Parameters"].items():
            if key in supplied:
                parameters.append({"ParameterKey": key, "ParameterValue": str(supplied[key])})
            elif "Default" not in spec:
                raise RuntimeError(f"Missing {component} parameter: {key}")
        request = {"StackName": f"{self.project}-{component}", "TemplateBody": json.dumps(body),
                   "Parameters": parameters, "Capabilities": ["CAPABILITY_NAMED_IAM"],
                   "Tags": [{"Key": "Project", "Value": self.project}]}
        if component != "foundation":
            request["RoleARN"] = self.foundation["FormationRole"]
        client = self.clients["cloudformation"]
        current = self.stack(component)
        if current and current["StackStatus"] not in ["CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE"]:
            raise RuntimeError(f"{component}: {current['StackStatus']}; resolve the stack failure before retrying.")
        try:
            if not current:
                request["EnableTerminationProtection"] = component == "foundation"
            (client.update_stack if current else client.create_stack)(**request)
        except ClientError as error:
            if "No updates are to be performed" in error.response["Error"]["Message"]:
                return self.outputs(component)
            raise
        def ready():
            state = self.stack(component)["StackStatus"]
            if state in ["CREATE_COMPLETE", "UPDATE_COMPLETE"]:
                return True
            if "FAILED" in state or "ROLLBACK" in state:
                events = client.describe_stack_events(StackName=request["StackName"])["StackEvents"]
                reasons = [f"{event['LogicalResourceId']}: {event.get('ResourceStatusReason', '')}" for event in events if "FAILED" in event["ResourceStatus"]]
                raise RuntimeError(f"{component} {state}: " + "; ".join(reasons[:5]))
            return False
        wait_until(component + " stack", ready, timeout=5400)
        return self.outputs(component)

    def delete_stack(self, component):
        if component not in ["app", "gpu", "eks", "database"]:
            raise ValueError("Persistent foundation cannot be deleted by lifecycle commands.")
        if not self.stack(component):
            return
        self.clients["cloudformation"].delete_stack(StackName=f"{self.project}-{component}", RoleARN=self.foundation["FormationRole"])
        def deleted():
            current = self.stack(component)
            if current and current["StackStatus"] == "DELETE_FAILED":
                raise RuntimeError(f"{component} deletion failed; inspect CloudFormation events.")
            return current is None
        wait_until(component + " deletion", deleted, timeout=5400)

    def read_control(self, key, optional=False):
        try:
            response = self.clients["s3"].get_object(Bucket=self.bucket, Key="control/" + key + ".json")
            return json.loads(response["Body"].read()), response["ETag"]
        except ClientError as error:
            if optional and error.response["Error"]["Code"] == "NoSuchKey":
                return None, None
            raise

    def write_control(self, key, data, **condition):
        return self.clients["s3"].put_object(Bucket=self.bucket, Key="control/" + key + ".json",
            Body=json.dumps(data).encode(), ContentType="application/json", ServerSideEncryption="AES256", **condition)

    @contextmanager
    def lock(self, action):
        current, etag = self.read_control("lock")
        if current.get("owner"):
            raise RuntimeError(f"Environment is locked by {current['action']} since {current['started']}. Check that run before manually recovering the lock.")
        owner = str(uuid.uuid4())
        result = self.write_control("lock", {"owner": owner, "action": action, "started": datetime.now(timezone.utc).isoformat()}, IfMatch=etag)
        try:
            yield
        finally:
            self.write_control("lock", {"owner": None}, IfMatch=result["ETag"])

    def bootstrap(self):
        ec2 = self.clients["ec2"]
        zones = sorted(item["Location"] for page in ec2.get_paginator("describe_instance_type_offerings").paginate(
            LocationType="availability-zone", Filters=[{"Name": "instance-type", "Values": ["g6.2xlarge"]}]) for item in page["InstanceTypeOfferings"])
        if len(zones) < 2:
            raise RuntimeError("Two available AZs are required; g6.2xlarge offering not found.")
        providers = self.clients["iam"].list_open_id_connect_providers()["OpenIDConnectProviderList"]
        provider = next((item["Arn"] for item in providers if item["Arn"].endswith("/token.actions.githubusercontent.com")), "")
        if ":assumed-role/" not in self.identity_arn:
            raise RuntimeError("Bootstrap using the project's administrator role, not root or long-lived IAM user keys.")
        role_name = self.identity_arn.split(":assumed-role/", 1)[1].split("/", 1)[0]
        operator_role = self.clients["iam"].get_role(RoleName=role_name)["Role"]["Arn"]
        values = {"AzA": zones[0], "AzB": zones[1], "ExistingOidcProviderArn": provider, "OperatorRole": operator_role}
        current = self.stack("foundation")
        if current:
            # Do not reinterpret our own OIDC provider as external on a subsequent bootstrap.
            values.update({item["ParameterKey"]: item["ParameterValue"] for item in current["Parameters"]})
        self.foundation = self.deploy_stack("foundation", values)
        for key, value in [("state", {"ever_started": False, "snapshot": None}), ("images", {}), ("lock", {"owner": None})]:
            existing, _ = self.read_control(key, optional=True)
            if existing is None:
                self.write_control(key, value, IfNoneMatch="*")
        log(json.dumps({"region": self.region, "account": ACCOUNT, "role": self.foundation["GithubRole"], "bucket": self.bucket}))

    def database(self):
        try:
            return self.clients["rds"].describe_db_instances(DBInstanceIdentifier=self.project + "-database")["DBInstances"][0]
        except self.clients["rds"].exceptions.DBInstanceNotFoundFault:
            return None

    def verify_snapshot(self, identifier):
        snapshot = self.clients["rds"].describe_db_snapshots(DBSnapshotIdentifier=identifier)["DBSnapshots"][0]
        if snapshot["Status"] != "available" or not snapshot.get("Encrypted") or snapshot["DBInstanceIdentifier"] != self.project + "-database":
            raise RuntimeError("Recovery snapshot is not available, encrypted, or from this project database.")
        return snapshot

    def snapshot_and_delete_database(self):
        database = self.database()
        if not database:
            state, _ = self.read_control("state")
            if state["ever_started"]:
                if not state.get("snapshot"):
                    raise RuntimeError("Database is missing without a recovery snapshot. Refusing to proceed.")
                self.verify_snapshot(state["snapshot"])
            return
        identifier = self.project + "-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        self.clients["rds"].create_db_snapshot(DBInstanceIdentifier=database["DBInstanceIdentifier"], DBSnapshotIdentifier=identifier,
            Tags=[{"Key": "Project", "Value": self.project}])
        wait_until("encrypted database snapshot", lambda: self.clients["rds"].describe_db_snapshots(
            DBSnapshotIdentifier=identifier)["DBSnapshots"][0]["Status"] == "available", timeout=7200)
        self.verify_snapshot(identifier)
        state, etag = self.read_control("state")
        state.update(snapshot=identifier, ever_started=True, phase="snapshot-preserved", engine=database["EngineVersion"])
        self.write_control("state", state, IfMatch=etag)
        saved, _ = self.read_control("state")
        if saved.get("snapshot") != identifier:
            raise RuntimeError("Snapshot recovery pointer was not persisted; database will not be deleted.")
        # A separate, verified manual snapshot already exists. It is never deleted here.
        self.clients["rds"].delete_db_instance(DBInstanceIdentifier=database["DBInstanceIdentifier"], SkipFinalSnapshot=True,
                                              DeleteAutomatedBackups=True)
        wait_until("database deletion", lambda: self.database() is None, timeout=7200)

    def nodes(self):
        return [instance for page in self.clients["ec2"].get_paginator("describe_instances").paginate(Filters=[
            {"Name": "tag:Project", "Values": [self.project]}, {"Name": "instance-state-name", "Values": ["running"]},
            {"Name": "instance.group-id", "Values": [self.foundation["NodeSecurityGroup"]]}])
                for reservation in page["Reservations"] for instance in reservation["Instances"]]

    def node(self):
        def available():
            identifiers = {item["InstanceId"] for item in self.nodes()}
            managed = self.clients["ssm"].describe_instance_information(Filters=[{"Key": "PingStatus", "Values": ["Online"]}])["InstanceInformationList"]
            return next((item["InstanceId"] for item in managed if item["InstanceId"] in identifiers), None)
        return wait_until("SSM-managed EKS CPU node", available, timeout=900)

    @contextmanager
    def tunnel(self, host, port):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            local_port = listener.getsockname()[1]
        arguments = ["aws", "ssm", "start-session", "--region", self.region, "--target", self.node(),
                     "--document-name", "AWS-StartPortForwardingSessionToRemoteHost", "--parameters",
                     json.dumps({"host": [host], "portNumber": [str(port)], "localPortNumber": [str(local_port)]})]
        process = subprocess.Popen(arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            def ready():
                if process.poll() is not None:
                    raise RuntimeError("SSM tunnel exited. Check Session Manager plugin, IAM and managed node connectivity.")
                try:
                    with socket.create_connection(("127.0.0.1", local_port), timeout=1):
                        return True
                except OSError:
                    return False
            wait_until("private SSM tunnel", ready, timeout=60, interval=1)
            yield local_port
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    def kubeconfig(self):
        run(["aws", "eks", "update-kubeconfig", "--region", self.region, "--name", self.project + "-eks"], stdout=subprocess.DEVNULL)

    def secret(self, key):
        return json.loads(self.clients["secretsmanager"].get_secret_value(SecretId=self.foundation[key])["SecretString"])

    def initialize_database(self):
        import psycopg
        from psycopg import sql
        host = self.outputs("database")["DatabaseHost"]
        admin, app = self.secret("AdminSecret"), self.secret("AppSecret")
        with tempfile.TemporaryDirectory(prefix="ds2l-db-") as directory, self.tunnel(host, 5432) as port:
            certificate = Path(directory) / "rds.pem"
            with urllib.request.urlopen("https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem", timeout=30) as response:
                certificate.write_bytes(response.read())
            with psycopg.connect(host=host, hostaddr="127.0.0.1", port=port, dbname="drivescene", user=admin["username"],
                    password=admin["password"], sslmode="verify-full", sslrootcert=str(certificate), autocommit=True) as connection:
                connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
                exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (app["username"],)).fetchone()
                verb = "ALTER" if exists else "CREATE"
                connection.execute(sql.SQL(verb + " ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                    sql.Identifier(app["username"]), sql.Literal(app["password"])))
                connection.execute(sql.SQL("GRANT CONNECT ON DATABASE drivescene TO {}").format(sql.Identifier(app["username"])))
                connection.execute(sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(sql.Identifier(app["username"])))

    def install_application(self, image):
        self.kubeconfig()
        run(["helm", "repo", "add", "aws-secrets-manager", "https://aws.github.io/secrets-store-csi-driver-provider-aws", "--force-update"])
        run(["helm", "repo", "update", "aws-secrets-manager"])
        run(["helm", "upgrade", "--install", "secrets-provider-aws", "aws-secrets-manager/secrets-store-csi-driver-provider-aws",
             "--version", "3.1.4", "--namespace", "kube-system", "--wait", "--timeout", "10m"])
        resources = kubernetes_resources(self.project, self.region, self.foundation, self.outputs("database")["DatabaseHost"], image)
        for resource in resources:
            run(["kubectl", "apply", "-f", "-"], input=json.dumps(resource))
        run(["kubectl", "-n", "drivescene", "rollout", "status", "deployment/backend", "--timeout=600s"])

    def verify_application_image(self, expected):
        service = self.clients["ecs"].describe_services(cluster=self.foundation["Cluster"], services=[self.project + "-app"])["services"][0]
        task = self.clients["ecs"].describe_task_definition(taskDefinition=service["taskDefinition"])["taskDefinition"]
        ecs_image = next(item["image"] for item in task["containerDefinitions"] if item["name"] == "app")
        deployment = json.loads(run(["kubectl", "-n", "drivescene", "get", "deployment", "backend", "-o", "json"], capture_output=True).stdout)
        eks_image = next(item["image"] for item in deployment["spec"]["template"]["spec"]["containers"] if item["name"] == "app")
        if ecs_image != expected or eks_image != expected:
            raise RuntimeError("ECS and EKS do not both reference the expected image digest; keeping writes blocked.")

    @contextmanager
    def app_connections(self):
        with ExitStack() as context:
            urls = []
            if self.stack("app"):
                service = self.clients["ecs"].describe_services(cluster=self.foundation["Cluster"], services=[self.project + "-app"])["services"][0]
                if service["runningCount"] != 1 or service["pendingCount"] != 0 or len(service["deployments"]) != 1:
                    raise RuntimeError("ECS must have exactly one stable app process before drain; wait for deployment stability.")
                port = context.enter_context(self.tunnel(f"app.{self.project}.internal", 8080))
                urls.append(f"http://127.0.0.1:{port}")
            if self.stack("eks"):
                self.kubeconfig()
                pods = json.loads(run(["kubectl", "-n", "drivescene", "get", "pods", "-l", "app=backend", "-o", "json"], capture_output=True).stdout)
                # Check every process so local active-write counters cannot miss a replica.
                for pod in pods["items"]:
                    if pod["status"].get("phase") == "Succeeded":
                        continue
                    with socket.socket() as listener:
                        listener.bind(("127.0.0.1", 0))
                        local_port = listener.getsockname()[1]
                    process = subprocess.Popen(["kubectl", "-n", "drivescene", "port-forward", "pod/" + pod["metadata"]["name"],
                        f"{local_port}:8080", "--address=127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    context.callback(process.wait, timeout=10)
                    context.callback(process.terminate)
                    base = f"http://127.0.0.1:{local_port}"
                    wait_until("Kubernetes port forwarding", lambda: self.http_ready(base + "/"), timeout=60, interval=1)
                    urls.append(base)
            yield urls

    @staticmethod
    def http_ready(url):
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def operations(self, url, operation=""):
        request = urllib.request.Request(url + "/internal/operations" + operation,
            method="POST" if operation else "GET", headers={"X-Operations-Token": self.secret("OperationsSecret")["token"]})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def drain(self):
        with self.app_connections() as urls:
            if not urls and self.stack("app"):
                raise RuntimeError("Cannot prove the application drained; keeping the database.")
            for url in urls:
                self.operations(url, "/quiesce")
            def idle():
                states = [self.operations(url) for url in urls]
                return all(state["maintenance"] and state["activeWrites"] == 0 and state["runningLabels"] == 0
                           and state["runningRecordings"] == 0 for state in states)
            wait_until("active uploads, edits and model jobs to drain", idle, timeout=7500, interval=10)

    def resume(self):
        with self.app_connections() as urls:
            if not urls:
                raise RuntimeError("No application to resume.")
            for url in urls:
                self.operations(url, "/resume")

    def gpu_start(self, image):
        quota = self.clients["service-quotas"].get_service_quota(ServiceCode="ec2", QuotaCode="L-DB2E81BA")["Quota"]["Value"]
        if quota < 8:
            raise RuntimeError(f"Seoul G/VT On-Demand quota is {quota} vCPU; g6.2xlarge needs at least 8. Approval is required before GPU start.")
        self.deploy_stack("gpu", {**self.foundation, "AiImage": image})
        with self.tunnel(f"ai.{self.project}.internal", 8000) as port:
            wait_until("GPU model readiness", lambda: self.http_ready(f"http://127.0.0.1:{port}/health"), timeout=3600, interval=15)

    def deploy_application_stack(self, image, workers=None):
        if workers is None:
            current = self.stack("app")
            parameters = {item["ParameterKey"]: item["ParameterValue"] for item in current.get("Parameters", [])} if current else {}
            # Legacy deployments did not have this parameter. Fail safe when GPU is off.
            workers = parameters.get("WorkerEnabled", "true" if self.stack("gpu") else "false") == "true"
        self.deploy_stack("app", {**self.foundation, **self.outputs("database"), "AppImage": image,
                                  "WorkerEnabled": "true" if workers else "false"})

    def set_workers(self, enabled):
        current = self.stack("app")
        if not current:
            raise RuntimeError("Application must be running before changing its worker state.")
        image = next(item["ParameterValue"] for item in current["Parameters"] if item["ParameterKey"] == "AppImage")
        self.deploy_application_stack(image, workers=enabled)

    def start(self, with_gpu=True):
        images, _ = self.read_control("images")
        if not images.get("app") or (with_gpu and not images.get("ai")):
            raise RuntimeError("Publish the required application/model image using the release workflow before start.")
        if with_gpu:
            quota = self.clients["service-quotas"].get_service_quota(ServiceCode="ec2", QuotaCode="L-DB2E81BA")["Quota"]["Value"]
            if quota < 8:
                raise RuntimeError("GPU quota not approved. Use start with GPU=false for CPU validation.")
        state, etag = self.read_control("state")
        existing = self.database()
        snapshot = state.get("snapshot") or ""
        if not existing and state["ever_started"] and not snapshot:
            raise RuntimeError("Previous database has no recovery snapshot; refusing to create an empty replacement.")
        if snapshot and not existing:
            self.verify_snapshot(snapshot)
        if not state.get("engine"):
            versions = self.clients["rds"].describe_db_engine_versions(Engine="postgres", DefaultOnly=False)["DBEngineVersions"]
            supported = [item["EngineVersion"] for item in versions if item["EngineVersion"].startswith("16.") and item["Status"] == "available"]
            state["engine"] = max(supported, key=lambda version: tuple(map(int, version.split("."))))
        if not state.get("kubernetes"):
            versions = self.clients["eks"].describe_cluster_versions(includeAll=False)["clusterVersions"]
            standard = [item["clusterVersion"] for item in versions if item["status"].upper().replace("-", "_") == "STANDARD_SUPPORT"]
            state["kubernetes"] = max(standard, key=lambda version: tuple(map(int, version.split("."))))
        state["phase"] = "starting"
        # Mark before creation, so an interrupted start can never silently reset data later.
        state["ever_started"] = True
        self.write_control("state", state, IfMatch=etag)
        self.deploy_stack("database", {**self.foundation, "EngineVersion": state["engine"], "Snapshot": snapshot})
        self.deploy_stack("eks", {**self.foundation, "KubernetesVersion": state["kubernetes"]})
        self.initialize_database()
        if with_gpu:
            self.gpu_start(images["ai"])
        self.deploy_application_stack(images["app"], workers=with_gpu)
        self.install_application(images["app"])
        self.verify_application_image(images["app"])
        self.resume()
        state, etag = self.read_control("state")
        state.update(phase="running", app_image=images["app"], ai_image=images.get("ai") if with_gpu else None)
        self.write_control("state", state, IfMatch=etag)
        self.status()

    def stop(self):
        if self.stack("app") or self.stack("eks"):
            self.drain()
        self.delete_stack("app")
        if self.stack("eks"):
            self.kubeconfig()
            run(["kubectl", "-n", "drivescene", "delete", "deployment", "backend", "--ignore-not-found=true", "--wait=true", "--timeout=300s"])
        self.delete_stack("gpu")
        self.snapshot_and_delete_database()
        self.delete_stack("database")
        self.delete_stack("eks")
        remaining = self.running_resources()
        if any(remaining.values()):
            wait_until("all runtime resources removed", lambda: not any(self.running_resources().values()), timeout=900)
        state, etag = self.read_control("state")
        state["phase"] = "stopped"
        self.write_control("state", state, IfMatch=etag)
        log("Stopped. S3, ECR, secrets and verified database snapshots are retained without automatic expiration.")

    def publish(self, component, image):
        expected = self.foundation["AppRepository" if component == "app" else "AiRepository"]
        if not re.fullmatch(re.escape(expected) + r"@sha256:[0-9a-f]{64}", image):
            raise ValueError("Only an immutable image digest in this project's ECR repository is accepted.")
        images, etag = self.read_control("images")
        previous = images.get(component)
        images[component] = image
        self.write_control("images", images, IfMatch=etag)
        if component == "app" and bool(self.stack("app")) != bool(self.stack("eks")):
            raise RuntimeError("Image recorded, but the environment is only partially running. Repair with start/stop; push will not create missing compute.")
        component_stack = "app" if component == "app" else "gpu"
        if not self.stack(component_stack):
            log("Environment/component is off. Image recorded; no compute resources created.")
            return
        self.drain()
        try:
            if component == "app":
                self.deploy_application_stack(image)
                self.install_application(image)
                self.verify_application_image(image)
            else:
                self.gpu_start(image)
        except Exception:
            if previous:
                log("Deployment failed; restoring the previous image while writes remain blocked.")
                if component == "app":
                    self.deploy_application_stack(previous)
                    self.install_application(previous)
                    self.verify_application_image(previous)
                else:
                    self.gpu_start(previous)
                images[component] = previous
                self.write_control("images", images)
                self.resume()
            raise
        self.resume()
        state, etag = self.read_control("state")
        state[component + "_image"] = image
        self.write_control("state", state, IfMatch=etag)

    def running_resources(self):
        instances = [instance["InstanceId"] for page in self.clients["ec2"].get_paginator("describe_instances").paginate(Filters=[
            {"Name": "tag:Project", "Values": [self.project]},
            {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped", "shutting-down"]}])
            for reservation in page["Reservations"] for instance in reservation["Instances"]]
        tasks = self.clients["ecs"].list_tasks(cluster=self.foundation["Cluster"])["taskArns"] if self.foundation else []
        return {"instances": instances, "tasks": tasks, "database": bool(self.database()), "eks": bool(self.stack("eks"))}

    def status(self):
        result = {"account": ACCOUNT, "region": self.region, "foundation": bool(self.foundation),
                  "resources": self.running_resources(),
                  "stacks": {key: (self.stack(key) or {}).get("StackStatus", "absent") for key in ["app", "gpu", "database", "eks"]},
                  "gpu_vcpu_quota": self.clients["service-quotas"].get_service_quota(ServiceCode="ec2", QuotaCode="L-DB2E81BA")["Quota"]["Value"]}
        if self.foundation:
            result["recovery"], _ = self.read_control("state")
        log(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["bootstrap", "start", "stop", "status", "gpu-start", "gpu-stop", "publish"])
    parser.add_argument("--project", default=os.environ.get("DS2L_PROJECT", "ds2l"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", REGION))
    parser.add_argument("--without-gpu", action="store_true")
    parser.add_argument("--component", choices=["app", "ai"], default="app")
    parser.add_argument("--image")
    args = parser.parse_args()
    environment = Environment(args.project, args.region)
    if args.action == "bootstrap":
        environment.bootstrap()
    elif args.action == "status":
        environment.status()
    else:
        if not environment.foundation:
            raise RuntimeError("Run bootstrap in the project account before lifecycle actions.")
        with environment.lock(args.action):
            if args.action == "start":
                environment.start(with_gpu=not args.without_gpu)
            elif args.action == "stop":
                environment.stop()
            elif args.action == "publish":
                if not args.image:
                    raise ValueError("publish requires --image repository@sha256:digest")
                environment.publish(args.component, args.image)
            elif args.action == "gpu-start":
                images, _ = environment.read_control("images")
                if not images.get("ai") or not environment.stack("app"):
                    raise RuntimeError("Start the application and publish the GPU image first.")
                environment.drain()
                environment.gpu_start(images["ai"])
                environment.set_workers(True)
                environment.resume()
            elif args.action == "gpu-stop":
                environment.drain()
                environment.set_workers(False)
                environment.delete_stack("gpu")
                environment.resume()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never dump SDK/SQL request arguments containing credentials.
        if isinstance(error, (ClientError, RuntimeError, ValueError)):
            log(f"ERROR ({type(error).__name__}): {error}")
        else:
            log(f"ERROR ({type(error).__name__}): operation failed; inspect service events. Sensitive request details suppressed.")
        sys.exit(1)
