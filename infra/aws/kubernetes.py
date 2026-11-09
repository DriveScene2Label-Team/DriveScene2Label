"""Kubernetes resources containing secret references, never secret values."""
import json


def resources(project, region, foundation, database_host, image):
    namespace = "drivescene"
    metadata = lambda name: {"name": name, "namespace": namespace}
    env = {
        "SERVER_PORT": "8080", "SERVER_ADDRESS": "0.0.0.0",
        "DB_URL": f"jdbc:postgresql://{database_host}:5432/drivescene?sslmode=verify-full&sslrootcert=/app/rds-ca.pem",
        "SPRING_CONFIG_IMPORT": "configtree:/mnt/secrets/",
        "AWS_REGION": region, "AWS_EC2_METADATA_DISABLED": "true",
        "UPLOAD_S3_BUCKET": foundation["DataBucket"], "UPLOAD_ROOT": "/uploads",
        "AI_SERVER_BASE_URL": f"http://ai.{project}.internal:8000",
        "AUTO_LABEL_WORKER_ENABLED": "false", "RECORDING_WORKER_ENABLED": "false",
        "NUSCENES_IMPORT_ENABLED": "false",
    }
    objects = [
        {"objectName": foundation["AppSecret"], "objectType": "secretsmanager", "jmesPath": [
            {"path": "username", "objectAlias": "DB_USERNAME"}, {"path": "password", "objectAlias": "DB_PASSWORD"}]},
        {"objectName": foundation["OperationsSecret"], "objectType": "secretsmanager", "jmesPath": [
            {"path": "token", "objectAlias": "OPERATIONS_TOKEN"}]},
    ]
    return [
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}},
        {"apiVersion": "v1", "kind": "ServiceAccount", "metadata": metadata("backend")},
        {"apiVersion": "secrets-store.csi.x-k8s.io/v1", "kind": "SecretProviderClass", "metadata": metadata("backend"),
         "spec": {"provider": "aws", "parameters": {"region": region, "usePodIdentity": "true", "objects": json.dumps(objects)}}},
        {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": metadata("backend"), "spec": {
            "replicas": 1, "selector": {"matchLabels": {"app": "backend"}},
            "strategy": {"type": "Recreate"},
            "template": {"metadata": {"labels": {"app": "backend"}}, "spec": {
                "serviceAccountName": "backend", "terminationGracePeriodSeconds": 120,
                "securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "runAsGroup": 10001, "fsGroup": 10001},
                "containers": [{"name": "app", "image": image,
                    "env": [{"name": key, "value": value} for key, value in env.items()],
                    "ports": [{"containerPort": 8080}],
                    "resources": {"requests": {"cpu": "500m", "memory": "1Gi"}, "limits": {"cpu": "1", "memory": "2Gi"}},
                    "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                    "startupProbe": {"httpGet": {"path": "/", "port": 8080}, "failureThreshold": 60, "periodSeconds": 5},
                    "readinessProbe": {"httpGet": {"path": "/", "port": 8080}, "periodSeconds": 10},
                    "livenessProbe": {"httpGet": {"path": "/", "port": 8080}, "periodSeconds": 30},
                    "volumeMounts": [{"name": "credentials", "mountPath": "/mnt/secrets", "readOnly": True},
                                     {"name": "uploads", "mountPath": "/uploads"}]}],
                "volumes": [{"name": "credentials", "csi": {"driver": "secrets-store.csi.k8s.io", "readOnly": True,
                            "volumeAttributes": {"secretProviderClass": "backend"}}}, {"name": "uploads", "emptyDir": {}}]}}}},
        {"apiVersion": "v1", "kind": "Service", "metadata": metadata("backend"), "spec": {
            "type": "ClusterIP", "selector": {"app": "backend"}, "ports": [{"port": 8080, "targetPort": 8080}]}},
    ]
