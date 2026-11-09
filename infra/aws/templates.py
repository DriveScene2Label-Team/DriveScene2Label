"""Render ordinary CloudFormation JSON without CDK or another provisioning framework."""
import argparse
import json
from pathlib import Path


def ref(key):
    return {"Ref": key}


def att(key, attribute="Arn"):
    return {"Fn::GetAtt": [key, attribute]}


def join(*parts):
    return {"Fn::Join": ["", list(parts)]}


def name(suffix):
    return join(ref("Project"), "-", suffix)


def arn(service, resource, account=None, region=None):
    return join("arn:", ref("AWS::Partition"), ":", service, ":",
                ref("AWS::Region") if region is None else region, ":",
                ref("AWS::AccountId") if account is None else account, ":", resource)


def tags():
    return [{"Key": "Project", "Value": ref("Project")}]


def statement(actions, resources, **extra):
    return {"Effect": "Allow", "Action": actions, "Resource": resources, **extra}


def policy(statements):
    return {"Version": "2012-10-17", "Statement": statements}


def trust(service, actions=None):
    return policy([{"Effect": "Allow", "Principal": {"Service": service},
                    "Action": actions or ["sts:AssumeRole"]}])


def resource(kind, properties, why, must=None, **extra):
    return {"Type": "AWS::" + kind, "Properties": properties,
            "Metadata": {"com.aws.cloudformation.Context": {"why": why, "must": must or []}}, **extra}


def template(description, parameters=None):
    return {"AWSTemplateFormatVersion": "2010-09-09", "Description": description,
            "Metadata": {"AWSToolsMetrics": {"AWSAgentToolkit": "aws-cloudformation@3"},
                         "com.aws.cloudformation.Context": {"ref": ["docs/aws-ecs-cicd.md"]}},
            "Parameters": {"Project": {"Type": "String", "Default": "ds2l",
                                      "AllowedPattern": "[a-z][a-z0-9-]{2,20}"}, **(parameters or {})},
            "Resources": {}, "Outputs": {}}


def parameters(*names):
    return {key: {"Type": "String"} for key in names}


def output(template_body, key, value):
    template_body["Outputs"][key] = {"Value": value, "Description": key}


def foundation():
    body = template("Persistent private data, network and deployment identities; never deleted by stop.",
                    {**parameters("AzA", "AzB", "OperatorRole"),
                     "ExistingOidcProviderArn": {"Type": "String", "Default": ""},
                     "OidcSubject": {"Type": "String", "Default":
                         "repo:DriveScene2Label-Team@354304315/DriveScene2Label@1388746280:environment:production"}})
    body["Conditions"] = {"CreateOidc": {"Fn::Equals": [ref("ExistingOidcProviderArn"), ""]}}
    resources = body["Resources"]
    resources["Vpc"] = resource("EC2::VPC", {
        "CidrBlock": "10.42.0.0/16", "EnableDnsHostnames": True, "EnableDnsSupport": True, "Tags": tags()},
        "Shared network survives compute shutdown.")
    resources["Gateway"] = resource("EC2::InternetGateway", {"Tags": tags()}, "Outbound package and model downloads.")
    resources["GatewayAttachment"] = resource("EC2::VPCGatewayAttachment",
        {"VpcId": ref("Vpc"), "InternetGatewayId": ref("Gateway")}, "Attach the shared outbound gateway.")
    resources["PublicRoutes"] = resource("EC2::RouteTable", {"VpcId": ref("Vpc"), "Tags": tags()}, "No recurring NAT gateway.")
    resources["InternetRoute"] = resource("EC2::Route", {
        "RouteTableId": ref("PublicRoutes"), "DestinationCidrBlock": "0.0.0.0/0", "GatewayId": ref("Gateway")},
        "Public IPs provide egress; security groups forbid public application ingress.",
        DependsOn="GatewayAttachment")
    for suffix, az, cidr, public in [
        ("PublicA", "AzA", "10.42.0.0/24", True), ("PublicB", "AzB", "10.42.1.0/24", True),
        ("PrivateA", "AzA", "10.42.10.0/24", False), ("PrivateB", "AzB", "10.42.11.0/24", False)]:
        resources[suffix] = resource("EC2::Subnet", {
            "VpcId": ref("Vpc"), "AvailabilityZone": ref(az), "CidrBlock": cidr,
            "MapPublicIpOnLaunch": public, "Tags": tags()}, "Application egress subnet." if public else "Isolated database subnet.")
        if public:
            resources[suffix + "Route"] = resource("EC2::SubnetRouteTableAssociation", {
                "SubnetId": ref(suffix), "RouteTableId": ref("PublicRoutes")}, "Outbound route association.")
    for suffix in ["Node", "App", "Gpu", "Database"]:
        resources[suffix + "SecurityGroup"] = resource("EC2::SecurityGroup", {
            "VpcId": ref("Vpc"), "GroupDescription": suffix + " private application traffic", "Tags": tags()},
            "Only named application security groups can reach service ports.", ["No public application or database ingress."])
    for key, target, source, port in [
        ("AppFromNode", "App", "Node", 8080), ("GpuFromApp", "Gpu", "App", 8000),
        ("GpuFromNode", "Gpu", "Node", 8000), ("DatabaseFromApp", "Database", "App", 5432),
        ("DatabaseFromNode", "Database", "Node", 5432)]:
        resources[key] = resource("EC2::SecurityGroupIngress", {
            "GroupId": ref(target + "SecurityGroup"), "SourceSecurityGroupId": ref(source + "SecurityGroup"),
            "IpProtocol": "tcp", "FromPort": port, "ToPort": port}, "Allow only the required internal service connection.")
    resources["NodePeerTraffic"] = resource("EC2::SecurityGroupIngress", {
        "GroupId": ref("NodeSecurityGroup"), "SourceSecurityGroupId": ref("NodeSecurityGroup"), "IpProtocol": "-1"},
        "Kubernetes pod and node traffic inside the node group.")
    resources["DatabaseSubnets"] = resource("RDS::DBSubnetGroup", {
        "DBSubnetGroupDescription": "Private database subnets", "SubnetIds": [ref("PrivateA"), ref("PrivateB")], "Tags": tags()},
        "Database stays private in both restore and initial-create paths.")
    resources["DatabaseParameters"] = resource("RDS::DBParameterGroup", {
        "Family": "postgres16", "Description": "Require TLS", "Parameters": {"rds.force_ssl": "1"}, "Tags": tags()},
        "Match PostgreSQL 16 integration tests and require encrypted connections.")
    resources["DataBucket"] = resource("S3::Bucket", {
        "BucketName": join(ref("Project"), "-", ref("AWS::AccountId"), "-", ref("AWS::Region"), "-data"),
        "PublicAccessBlockConfiguration": {key: True for key in
            ["BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets"]},
        "BucketEncryption": {"ServerSideEncryptionConfiguration": [{"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]},
        "VersioningConfiguration": {"Status": "Enabled"}, "Tags": tags()},
        "Original uploads and versioned lifecycle state outlive compute.", ["No automatic data expiry."],
        DeletionPolicy="Retain", UpdateReplacePolicy="Retain")
    resources["DataBucketPolicy"] = resource("S3::BucketPolicy", {
        "Bucket": ref("DataBucket"), "PolicyDocument": policy([{
            "Effect": "Deny", "Principal": "*", "Action": "s3:*",
            "Resource": [att("DataBucket"), join(att("DataBucket"), "/*")],
            "Condition": {"Bool": {"aws:SecureTransport": "false"}}}])}, "Refuse unencrypted S3 transport.")
    for key, username in [("AdminSecret", "ds2l_owner"), ("AppSecret", "ds2l_app"), ("OperationsSecret", None)]:
        resources[key] = resource("SecretsManager::Secret", {
            "Name": name(key.lower()), "GenerateSecretString": {
                "SecretStringTemplate": json.dumps({"username": username}) if username else "{}",
                "GenerateStringKey": "password" if username else "token", "PasswordLength": 40, "ExcludePunctuation": True},
            "Tags": tags()}, "Credentials remain available when the database is restored.",
            ["Never write secret values to logs or workflow variables."], DeletionPolicy="Retain", UpdateReplacePolicy="Retain")
    for component in ["App", "Ai"]:
        resources[component + "Repository"] = resource("ECR::Repository", {
            "RepositoryName": name(component.lower()), "ImageTagMutability": "IMMUTABLE",
            "EncryptionConfiguration": {"EncryptionType": "AES256"}, "Tags": tags()},
            "Immutable images survive environment shutdown.", ["No automatic image deletion."],
            DeletionPolicy="Retain", UpdateReplacePolicy="Retain")
        resources[component + "Logs"] = resource("Logs::LogGroup", {
            "LogGroupName": join("/drivescene/", ref("Project"), "/", component.lower()), "RetentionInDays": 30},
            "Retain diagnostic logs independently of compute.", DeletionPolicy="Retain", UpdateReplacePolicy="Retain")
    resources["Cluster"] = resource("ECS::Cluster", {"ClusterName": name("ecs"), "Tags": tags()},
        "Empty ECS control plane persists without running tasks.")
    resources["Namespace"] = resource("ServiceDiscovery::PrivateDnsNamespace", {
        "Name": join(ref("Project"), ".internal"), "Vpc": ref("Vpc"), "Tags": tags()},
        "Stable private names shared by ECS and EKS.")
    resources["AppDiscovery"] = resource("ServiceDiscovery::Service", {
        "Name": "app", "NamespaceId": ref("Namespace"),
        "DnsConfig": {"DnsRecords": [{"Type": "A", "TTL": 10}], "RoutingPolicy": "MULTIVALUE"},
        "HealthCheckCustomConfig": {"FailureThreshold": 1}}, "Private discovery for the Fargate application.")
    resources["AiDiscovery"] = resource("ServiceDiscovery::Service", {
        "Name": "ai", "NamespaceId": ref("Namespace"),
        "DnsConfig": {"DnsRecords": [{"Type": "A", "TTL": 10}], "RoutingPolicy": "MULTIVALUE"}},
        "Cloud Map owns the private DNS zone; register the disposable GPU through its service.",
        ["Do not write Route 53 records directly in the Cloud Map managed zone."])

    def role(key, principal, managed=(), statements=(), actions=None):
        props = {"RoleName": name(key.lower()), "AssumeRolePolicyDocument": trust(principal, actions), "Tags": tags()}
        if principal == "ecs-tasks.amazonaws.com":
            props["AssumeRolePolicyDocument"]["Statement"][0]["Condition"] = {
                "StringEquals": {"aws:SourceAccount": ref("AWS::AccountId")},
                "ArnLike": {"aws:SourceArn": arn("ecs", "*")}}
        if managed:
            props["ManagedPolicyArns"] = [arn("iam", "policy/" + item, account="aws", region="") for item in managed]
        if statements:
            props["Policies"] = [{"PolicyName": "project-resources", "PolicyDocument": policy(list(statements))}]
        resources[key] = resource("IAM::Role", props, "Separate service and application permissions.")
    uploads = join(att("DataBucket"), "/uploads/*")
    role("AppRole", "ecs-tasks.amazonaws.com", statements=[
        statement(["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], uploads)])
    role("AiRole", "ecs-tasks.amazonaws.com", statements=[statement(["s3:GetObject"], uploads)])
    role("ExecutionRole", "ecs-tasks.amazonaws.com", ["service-role/AmazonECSTaskExecutionRolePolicy"], [
        statement(["secretsmanager:GetSecretValue"], [ref("AppSecret"), ref("OperationsSecret")])])
    resources["TeamUsers"] = resource("Cognito::UserPool", {
        "UserPoolName": name("team"), "UserPoolTier": "ESSENTIALS", "DeletionProtection": "ACTIVE",
        "AdminCreateUserConfig": {"AllowAdminCreateUserOnly": True}, "UsernameConfiguration": {"CaseSensitive": False},
        "Policies": {"PasswordPolicy": {"MinimumLength": 14, "RequireLowercase": True, "RequireUppercase": True,
                    "RequireNumbers": True, "RequireSymbols": True, "TemporaryPasswordValidityDays": 7}},
        "MfaConfiguration": "OPTIONAL", "EnabledMfas": ["SOFTWARE_TOKEN_MFA"],
        "UserPoolTags": {"Project": ref("Project")}},
        "Only administrator-created team accounts can access the public site.",
        DeletionPolicy="Retain", UpdateReplacePolicy="Retain")
    resources["TeamGroup"] = resource("Cognito::UserPoolGroup", {
        "UserPoolId": ref("TeamUsers"), "GroupName": "team", "Description": "Authorized DriveScene2Label team members"},
        "A valid account also needs explicit team membership.")
    resources["LoginDomain"] = resource("Cognito::UserPoolDomain", {
        "UserPoolId": ref("TeamUsers"), "Domain": join(ref("Project"), "-", ref("AWS::AccountId"), "-seoul"),
        "ManagedLoginVersion": 2}, "AWS-hosted HTTPS login; no purchased domain is required.")
    resources["WebSecret"] = resource("SecretsManager::Secret", {
        "Name": name("websecret"), "Tags": tags(), "GenerateSecretString": {
            "SecretStringTemplate": '{"client_secret":"not-configured"}', "GenerateStringKey": "cookie_secret",
            "PasswordLength": 32, "ExcludePunctuation": True}},
        "Session signing key and confidential OAuth client secret never enter Git or logs.",
        DeletionPolicy="Retain", UpdateReplacePolicy="Retain")
    role("WebExecutionRole", "ecs-tasks.amazonaws.com", ["service-role/AmazonECSTaskExecutionRolePolicy"], [
        statement(["secretsmanager:GetSecretValue"], ref("WebSecret"))])
    role("WebInfrastructureRole", "ecs.amazonaws.com", ["service-role/AmazonECSInfrastructureRoleforExpressGatewayServices"])
    role("WebTaskRole", "ecs-tasks.amazonaws.com")
    role("GpuHostRole", "ec2.amazonaws.com",
         ["service-role/AmazonEC2ContainerServiceforEC2Role", "AmazonSSMManagedInstanceCore"])
    resources["GpuProfile"] = resource("IAM::InstanceProfile", {"Roles": [ref("GpuHostRole")]},
        "GPU host credentials come from an instance profile.")
    role("EksControlRole", "eks.amazonaws.com", ["AmazonEKSClusterPolicy"])
    role("EksNodeRole", "ec2.amazonaws.com",
         ["AmazonEKSWorkerNodePolicy", "AmazonEKS_CNI_Policy", "AmazonEC2ContainerRegistryPullOnly", "AmazonSSMManagedInstanceCore"])
    role("EksAppRole", "pods.eks.amazonaws.com", statements=[
        statement(["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], uploads),
        statement(["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"], [ref("AppSecret"), ref("OperationsSecret")])],
        actions=["sts:AssumeRole", "sts:TagSession"])
    resources["EksAppRole"]["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]["Condition"] = {
        "StringEquals": {"aws:RequestTag/kubernetes-namespace": "drivescene",
                         "aws:RequestTag/kubernetes-service-account": "backend"}}
    # CloudFormation YAML/JSON is infrastructure, not runtime source. Keep provisioning separate from SDK task permissions.
    runtime_roles = [att(key) for key in ["AppRole", "AiRole", "ExecutionRole", "GpuHostRole", "EksControlRole", "EksNodeRole", "EksAppRole",
                                        "WebExecutionRole", "WebInfrastructureRole", "WebTaskRole"]]
    role("FormationRole", "cloudformation.amazonaws.com", statements=[
        statement(["ec2:Describe*", "ec2:RunInstances", "ec2:TerminateInstances", "ec2:CreateTags", "ec2:DeleteTags",
                   "ec2:CreateLaunchTemplate", "ec2:DeleteLaunchTemplate", "ec2:CreateLaunchTemplateVersion",
                   "ec2:DeleteLaunchTemplateVersions", "ec2:ModifyLaunchTemplate", "ec2:AuthorizeSecurityGroupIngress",
                   "ec2:RevokeSecurityGroupIngress", "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup"], "*", Condition={"StringEquals": {"aws:RequestedRegion": ref("AWS::Region")}}),
        statement(["ecs:CreateService", "ecs:UpdateService", "ecs:DeleteService", "ecs:DescribeServices",
                   "ecs:DescribeTaskDefinition", "ecs:RegisterTaskDefinition", "ecs:DeregisterTaskDefinition",
                   "ecs:TagResource", "ecs:UntagResource", "ecs:ListTagsForResource", "ecs:CreateExpressGatewayService",
                   "ecs:UpdateExpressGatewayService", "ecs:DeleteExpressGatewayService", "ecs:DescribeExpressGatewayService",
                   "ecs:ListServiceDeployments", "ecs:DescribeServiceDeployments", "ecs:DescribeServiceRevisions"], "*",
                  Condition={"StringEquals": {"aws:RequestedRegion": ref("AWS::Region")}}),
        statement(["eks:CreateCluster", "eks:DeleteCluster", "eks:DescribeCluster", "eks:UpdateClusterConfig",
                   "eks:UpdateClusterVersion", "eks:DescribeUpdate", "eks:TagResource", "eks:UntagResource",
                   "eks:ListTagsForResource", "eks:CreateNodegroup", "eks:DeleteNodegroup", "eks:DescribeNodegroup",
                   "eks:UpdateNodegroupConfig", "eks:UpdateNodegroupVersion", "eks:CreateAccessEntry",
                   "eks:DeleteAccessEntry", "eks:DescribeAccessEntry", "eks:UpdateAccessEntry",
                   "eks:AssociateAccessPolicy", "eks:DisassociateAccessPolicy", "eks:ListAssociatedAccessPolicies",
                   "eks:CreateAddon", "eks:UpdateAddon", "eks:DeleteAddon", "eks:DescribeAddon",
                   "eks:CreatePodIdentityAssociation", "eks:DeletePodIdentityAssociation",
                   "eks:DescribePodIdentityAssociation", "eks:UpdatePodIdentityAssociation"],
                  [arn("eks", join("cluster/", name("*"))),
                   arn("eks", join("nodegroup/", name("*"), "/*")), arn("eks", join("addon/", name("*"), "/*")),
                   arn("eks", join("access-entry/", name("*"), "/*")), arn("eks", join("podidentityassociation/", name("*"), "/*"))]),
        statement(["rds:CreateDBInstance", "rds:RestoreDBInstanceFromDBSnapshot", "rds:DescribeDBInstances",
                   "rds:ModifyDBInstance", "rds:AddTagsToResource", "rds:RemoveTagsFromResource", "rds:ListTagsForResource"],
                  [arn("rds", join("db:", name("*"))), arn("rds", join("snapshot:", name("*"))),
                   arn("rds", "subgrp:*"), arn("rds", "pg:*")]),
        statement(["iam:PassRole", "iam:GetRole", "iam:ListAttachedRolePolicies", "iam:ListRolePolicies", "iam:GetRolePolicy"], runtime_roles),
        statement(["iam:GetInstanceProfile"], att("GpuProfile")),
        statement(["iam:GetRole"], [arn("iam", f"role/aws-service-role/{service}/*", region="")
                  for service in ["eks.amazonaws.com", "eks-nodegroup.amazonaws.com", "ecs.amazonaws.com", "rds.amazonaws.com", "autoscaling.amazonaws.com"]]),
        # IAM resolves a role that does not exist yet without its eventual service-linked path.
        statement(["iam:GetRole"], [arn("iam", "role/" + role_name, region="") for role_name in [
            "AWSServiceRoleForAmazonEKS", "AWSServiceRoleForAmazonEKSNodegroup", "AWSServiceRoleForECS",
            "AWSServiceRoleForRDS", "AWSServiceRoleForAutoScaling"]]),
        statement(["iam:CreateServiceLinkedRole"], "*",
                  Condition={"StringEquals": {"iam:AWSServiceName": ["eks.amazonaws.com", "eks-nodegroup.amazonaws.com", "ecs.amazonaws.com", "rds.amazonaws.com", "autoscaling.amazonaws.com"]}}),
        statement(["secretsmanager:GetSecretValue"], ref("AdminSecret")),
        statement(["cognito-idp:CreateUserPoolClient", "cognito-idp:DescribeUserPoolClient", "cognito-idp:UpdateUserPoolClient",
                   "cognito-idp:DeleteUserPoolClient", "cognito-idp:CreateManagedLoginBranding", "cognito-idp:DescribeManagedLoginBranding",
                   "cognito-idp:UpdateManagedLoginBranding", "cognito-idp:DeleteManagedLoginBranding"], att("TeamUsers")),
        statement(["ssm:GetParameters", "ssm:GetParameter"], arn("ssm", "parameter/aws/service/ecs/optimized-ami/*", account="")),
        statement(["servicediscovery:GetService", "servicediscovery:GetNamespace", "servicediscovery:ListInstances"], "*"),
        statement(["servicediscovery:RegisterInstance", "servicediscovery:DeregisterInstance", "servicediscovery:GetInstance"], att("AiDiscovery")),
        statement(["servicediscovery:GetOperation"], "*", Condition={"StringEquals": {"aws:RequestedRegion": ref("AWS::Region")}})
    ])
    resources["GithubProvider"] = resource("IAM::OIDCProvider", {
        "Url": "https://token.actions.githubusercontent.com", "ClientIdList": ["sts.amazonaws.com"]},
        "GitHub exchanges short-lived OIDC tokens; no access keys.", Condition="CreateOidc")
    github_trust = policy([{"Effect": "Allow", "Principal": {"Federated": {
        "Fn::If": ["CreateOidc", ref("GithubProvider"), ref("ExistingOidcProviderArn")]}},
        "Action": "sts:AssumeRoleWithWebIdentity", "Condition": {"StringEquals": {
            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com", "token.actions.githubusercontent.com:sub": ref("OidcSubject")}}}])
    github_permissions = [
        statement(["cloudformation:CreateStack", "cloudformation:UpdateStack", "cloudformation:DeleteStack",
                   "cloudformation:DescribeStacks", "cloudformation:DescribeStackEvents", "cloudformation:DescribeStackResources",
                   "cloudformation:GetTemplate"], arn("cloudformation", join("stack/", name("*"), "/*"))),
        statement(["cloudformation:ValidateTemplate"], "*"),
        statement(["iam:PassRole"], [att("FormationRole"), att("EksAppRole")]),
        statement(["ecr:GetAuthorizationToken"], "*"),
        statement(["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload",
                   "ecr:PutImage", "ecr:DescribeImages", "ecr:DescribeRepositories", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                  [att("AppRepository"), att("AiRepository")]),
        statement(["s3:GetObject", "s3:PutObject"], join(att("DataBucket"), "/control/*")),
        statement(["s3:ListBucket"], att("DataBucket"), Condition={"StringLike": {"s3:prefix": "control/*"}}),
        statement(["secretsmanager:GetSecretValue"], [ref("AdminSecret"), ref("AppSecret"), ref("OperationsSecret")]),
        statement(["secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue"], ref("WebSecret")),
        statement(["cognito-idp:DescribeUserPoolClient", "cognito-idp:UpdateUserPoolClient"], att("TeamUsers")),
        statement(["ecs:UpdateService"], arn("ecs", join("service/", name("ecs"), "/", name("web")))),
        statement(["elasticloadbalancing:ModifyLoadBalancerAttributes"],
                  arn("elasticloadbalancing", "loadbalancer/app/ecs-express-gateway-alb-*/*")),
        statement(["ec2:DescribeInstances", "ec2:DescribeAvailabilityZones", "ec2:DescribeInstanceTypeOfferings",
                   "ec2:DescribeInstanceTypes", "eks:DescribeCluster", "eks:DescribeClusterVersions",
                   "eks:DescribeAddonVersions", "eks:DescribeNodegroup", "eks:ListNodegroups",
                   "eks:ListPodIdentityAssociations", "eks:DescribePodIdentityAssociation",
                   "ecs:ListTasks", "ecs:DescribeTasks", "ecs:DescribeServices", "ecs:DescribeTaskDefinition",
                   "ecs:ListServiceDeployments", "ecs:DescribeServiceDeployments",
                   "rds:DescribeDBInstances", "rds:DescribeDBSnapshots", "rds:DescribeDBEngineVersions",
                   "rds:DescribeOrderableDBInstanceOptions", "rds:ListTagsForResource", "ssm:DescribeInstanceInformation",
                   "servicequotas:GetServiceQuota", "elasticloadbalancing:DescribeLoadBalancers", "elasticloadbalancing:DescribeTags"], "*",
                  Condition={"StringEquals": {"aws:RequestedRegion": ref("AWS::Region")}}),
        statement(["rds:CreateDBSnapshot", "rds:DeleteDBInstance", "rds:AddTagsToResource"],
                  [arn("rds", join("db:", name("database"))), arn("rds", join("snapshot:", name("*")))]),
        statement(["ssm:StartSession"], arn("ec2", "instance/*"),
                  Condition={"StringEquals": {"ssm:resourceTag/Project": ref("Project")}}),
        statement(["ssm:StartSession"], arn("ssm", "document/AWS-StartPortForwardingSessionToRemoteHost", account="")),
        statement(["ssm:TerminateSession", "ssm:ResumeSession"], arn("ssm", "session/*"))
    ]
    resources["GithubRole"] = resource("IAM::Role", {
        "RoleName": name("github"), "AssumeRolePolicyDocument": github_trust, "MaxSessionDuration": 14400,
        "Policies": [{"PolicyName": "project-orchestration", "PolicyDocument": policy(github_permissions)}], "Tags": tags()},
        "Only this repository's protected production environment may orchestrate project stacks; the managed gateway timeout covers full mini import.",
        ["GitHub production environment permits release-version only."])
    for key in ["Vpc", "PublicA", "PublicB", "PrivateA", "PrivateB", "NodeSecurityGroup", "AppSecurityGroup",
                "GpuSecurityGroup", "DatabaseSecurityGroup", "DatabaseSubnets", "DatabaseParameters",
                "DataBucket", "AdminSecret", "AppSecret", "OperationsSecret", "Cluster", "AppDiscovery", "AiDiscovery", "AppLogs", "AiLogs", "TeamUsers", "WebSecret", "LoginDomain"]:
        output(body, key, ref(key))
    for key in ["AppRole", "AiRole", "ExecutionRole", "EksControlRole", "EksNodeRole", "EksAppRole", "FormationRole", "GithubRole",
                "WebExecutionRole", "WebInfrastructureRole", "WebTaskRole"]:
        output(body, key, att(key))
    output(body, "GpuProfile", ref("GpuProfile"))
    output(body, "OperatorRole", ref("OperatorRole"))
    output(body, "AppDiscovery", att("AppDiscovery"))
    output(body, "HostedZone", att("Namespace", "HostedZoneId"))
    for component in ["App", "Ai"]:
        output(body, component + "Repository", att(component + "Repository", "RepositoryUri"))
    return body


def database():
    body = template("Private PostgreSQL; stop verifies a durable snapshot before explicit deletion.",
        {**parameters("DatabaseSubnets", "DatabaseParameters", "DatabaseSecurityGroup", "AdminSecret", "EngineVersion"),
         "Snapshot": {"Type": "String", "Default": ""}})
    body["Conditions"] = {"Restore": {"Fn::Not": [{"Fn::Equals": [ref("Snapshot"), ""]}]}}
    initial = lambda value: {"Fn::If": ["Restore", ref("AWS::NoValue"), value]}
    body["Resources"]["Database"] = resource("RDS::DBInstance", {
        "DBInstanceIdentifier": name("database"), "Engine": "postgres", "EngineVersion": ref("EngineVersion"),
        "DBInstanceClass": "db.t4g.small", "AllocatedStorage": "20", "StorageType": "gp3",
        "StorageEncrypted": True, "MultiAZ": False, "PubliclyAccessible": False, "DeletionProtection": False,
        "BackupRetentionPeriod": 7, "AutoMinorVersionUpgrade": False,
        "DBSubnetGroupName": ref("DatabaseSubnets"), "DBParameterGroupName": ref("DatabaseParameters"),
        "VPCSecurityGroups": [ref("DatabaseSecurityGroup")], "DBName": initial("drivescene"),
        "MasterUsername": initial(join("{{resolve:secretsmanager:", ref("AdminSecret"), ":SecretString:username}}")),
        "MasterUserPassword": initial(join("{{resolve:secretsmanager:", ref("AdminSecret"), ":SecretString:password}}")),
        "DBSnapshotIdentifier": {"Fn::If": ["Restore", ref("Snapshot"), ref("AWS::NoValue")]}, "Tags": tags()},
        "Retain on accidental stack deletion; the stop command separately checks snapshot availability before deleting the DB.",
        ["No automatic snapshot deletion.", "Never delete without a verified snapshot and saved recovery manifest."],
        DeletionPolicy="Retain", UpdateReplacePolicy="Retain")
    output(body, "DatabaseId", ref("Database"))
    output(body, "DatabaseHost", att("Database", "Endpoint.Address"))
    return body


def eks():
    body = template("Disposable EKS control plane and one CPU node; all durable data is external.",
        parameters("PublicA", "PublicB", "NodeSecurityGroup", "EksControlRole", "EksNodeRole", "EksAppRole", "GithubRole", "OperatorRole", "KubernetesVersion"))
    resources = body["Resources"]
    resources["Eks"] = resource("EKS::Cluster", {
        "Name": name("eks"), "Version": ref("KubernetesVersion"), "RoleArn": ref("EksControlRole"),
        "AccessConfig": {"AuthenticationMode": "API", "BootstrapClusterCreatorAdminPermissions": False},
        "ResourcesVpcConfig": {"SubnetIds": [ref("PublicA"), ref("PublicB")], "EndpointPublicAccess": True,
                              "EndpointPrivateAccess": True}, "Tags": tags()},
        "IAM-authenticated control plane for CI; application services have no public ingress.")
    resources["Access"] = resource("EKS::AccessEntry", {
        "ClusterName": ref("Eks"), "PrincipalArn": ref("GithubRole"), "Type": "STANDARD",
        "AccessPolicies": [{"PolicyArn": arn("eks", "cluster-access-policy/AmazonEKSClusterAdminPolicy", account="aws", region=""),
                            "AccessScope": {"Type": "cluster"}}]},
        "The deployment role installs cluster add-ons and application manifests only on this cluster.")
    resources["OperatorAccess"] = resource("EKS::AccessEntry", {
        "ClusterName": ref("Eks"), "PrincipalArn": ref("OperatorRole"), "Type": "STANDARD",
        "AccessPolicies": [{"PolicyArn": arn("eks", "cluster-access-policy/AmazonEKSClusterAdminPolicy", account="aws", region=""),
                            "AccessScope": {"Type": "cluster"}}]},
        "The existing project administrator can validate through kubectl port forwarding.")
    for key, group, source, port in [
        ("ApiFromNodes", att("Eks", "ClusterSecurityGroupId"), ref("NodeSecurityGroup"), 443),
        ("KubeletFromControl", ref("NodeSecurityGroup"), att("Eks", "ClusterSecurityGroupId"), 10250)]:
        resources[key] = resource("EC2::SecurityGroupIngress", {"GroupId": group, "SourceSecurityGroupId": source,
            "IpProtocol": "tcp", "FromPort": port, "ToPort": port}, "Required node/control-plane communication.")
    resources["LaunchTemplate"] = resource("EC2::LaunchTemplate", {"LaunchTemplateData": {
        "MetadataOptions": {"HttpTokens": "required", "HttpPutResponseHopLimit": 2},
        "CreditSpecification": {"CpuCredits": "standard"},
        "SecurityGroupIds": [ref("NodeSecurityGroup")],
        "BlockDeviceMappings": [{"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 80, "VolumeType": "gp3", "Encrypted": True, "DeleteOnTermination": True}}],
        "TagSpecifications": [{"ResourceType": "instance", "Tags": tags()}, {"ResourceType": "volume", "Tags": tags()}],
        "UserData": {"Fn::Base64": "MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=\"DS2L\"\n\n--DS2L\nContent-Type: text/x-shellscript; charset=\"us-ascii\"\n\n#!/bin/bash\nset -eu\ndnf install -y amazon-ssm-agent\nsystemctl enable --now amazon-ssm-agent\n--DS2L--\n"}}},
        "CPU credits capped; encrypted disks contain only caches and container layers.")
    resources["Nodes"] = resource("EKS::Nodegroup", {
        "ClusterName": ref("Eks"), "NodegroupName": "cpu", "NodeRole": ref("EksNodeRole"),
        "Subnets": [ref("PublicA"), ref("PublicB")], "InstanceTypes": ["t3.large"], "AmiType": "AL2023_x86_64_STANDARD",
        "CapacityType": "ON_DEMAND", "ScalingConfig": {"MinSize": 1, "DesiredSize": 1, "MaxSize": 1},
        "LaunchTemplate": {"Id": ref("LaunchTemplate"), "Version": att("LaunchTemplate", "LatestVersionNumber")},
        "Tags": {"Project": ref("Project")}}, "One node for private validation; no always-on GPU in EKS.",
        DependsOn=["ApiFromNodes", "KubeletFromControl"])
    for key, addon in [("Cni", "vpc-cni"), ("Dns", "coredns"), ("Proxy", "kube-proxy"), ("PodIdentity", "eks-pod-identity-agent")]:
        resources[key] = resource("EKS::Addon", {"ClusterName": ref("Eks"), "AddonName": addon,
            "ResolveConflicts": "OVERWRITE"}, "EKS selects a version compatible with the pinned cluster version.", DependsOn="Nodes")
    resources["AppIdentity"] = resource("EKS::PodIdentityAssociation", {
        "ClusterName": ref("Eks"), "Namespace": "drivescene", "ServiceAccount": "backend", "RoleArn": ref("EksAppRole")},
        "Only the backend pod obtains S3 and application-secret permissions.")
    output(body, "EksCluster", ref("Eks"))
    return body


def gpu():
    body = template("Disposable ECS GPU host with stable private DNS; caches may be downloaded again.",
        {**parameters("Cluster", "PublicA", "GpuSecurityGroup", "GpuProfile", "AiDiscovery", "AiImage", "AiRole", "ExecutionRole", "AiLogs", "DataBucket"),
         "GpuAmi": {"Type": "AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>",
                    "Default": "/aws/service/ecs/optimized-ami/amazon-linux-2023/gpu/recommended/image_id"}})
    resources = body["Resources"]
    resources["Host"] = resource("EC2::Instance", {
        "ImageId": ref("GpuAmi"), "InstanceType": "g6.2xlarge", "IamInstanceProfile": ref("GpuProfile"),
        "SubnetId": ref("PublicA"), "SecurityGroupIds": [ref("GpuSecurityGroup")],
        "MetadataOptions": {"HttpTokens": "required", "HttpPutResponseHopLimit": 2},
        "BlockDeviceMappings": [{"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 150, "VolumeType": "gp3", "Encrypted": True, "DeleteOnTermination": True}}],
        "UserData": {"Fn::Base64": join("#!/bin/bash\nset -eu\nmkdir -p /etc/ecs /models /uploads /results\n",
            "printf 'ECS_CLUSTER=", ref("Cluster"), "\\nECS_ENABLE_GPU_SUPPORT=true\\nECS_ENABLE_TASK_IAM_ROLE_NETWORK_HOST=true\\n' >> /etc/ecs/ecs.config\n")},
        "Tags": tags()}, "Host networking permits outbound model downloads without a NAT gateway.",
        ["Root disk contains caches only; uploads are durable in S3."])
    resources["AiDns"] = resource("ServiceDiscovery::Instance", {
        "ServiceId": ref("AiDiscovery"), "InstanceId": ref("Host"),
        "InstanceAttributes": {"AWS_INSTANCE_IPV4": att("Host", "PrivateIp"), "AWS_INSTANCE_PORT": "8000"}},
        "Register the current GPU host in Cloud Map and deregister it when the GPU stack is removed.",
        ["The stable private model URL must resolve to the current GPU host only."])
    resources["Task"] = resource("ECS::TaskDefinition", {
        "Family": name("ai"), "NetworkMode": "host", "RequiresCompatibilities": ["EC2"],
        "RuntimePlatform": {"CpuArchitecture": "X86_64", "OperatingSystemFamily": "LINUX"},
        "TaskRoleArn": ref("AiRole"), "ExecutionRoleArn": ref("ExecutionRole"),
        "Volumes": [{"Name": value, "Host": {"SourcePath": "/" + value}} for value in ["models", "uploads", "results"]],
        "ContainerDefinitions": [{
            "Name": "ai", "Image": ref("AiImage"), "Essential": True, "Memory": 28672, "Cpu": 7168,
            "ResourceRequirements": [{"Type": "GPU", "Value": "1"}],
            "PortMappings": [{"ContainerPort": 8000, "HostPort": 8000}],
            "MountPoints": [{"SourceVolume": value, "ContainerPath": "/" + value, "ReadOnly": False} for value in ["models", "uploads", "results"]],
            "Environment": [{"Name": key, "Value": value} for key, value in {
                "UPLOAD_ROOT": "/uploads", "UPLOAD_S3_BUCKET": ref("DataBucket"), "AWS_DEFAULT_REGION": ref("AWS::Region"),
                "VESPA_EXECUTOR": "local", "VESPA_OUTPUT_ROOT": "/results", "VESPA_TIMEOUT_SECONDS": "7200", "VESPA_NUM_THREADS": "1"}.items()],
            "HealthCheck": {"Command": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/livez',timeout=5)"],
                            "Interval": 30, "Timeout": 10, "Retries": 5, "StartPeriod": 300},
            "LogConfiguration": {"LogDriver": "awslogs", "Options": {
                "awslogs-group": ref("AiLogs"), "awslogs-region": ref("AWS::Region"), "awslogs-stream-prefix": "ai"}}}]},
        "Single model process, one GPU, liveness separate from model readiness.")
    resources["Service"] = resource("ECS::Service", {
        "ServiceName": name("ai"), "Cluster": ref("Cluster"), "TaskDefinition": ref("Task"), "LaunchType": "EC2",
        "DesiredCount": 1, "DeploymentConfiguration": {"MinimumHealthyPercent": 0, "MaximumPercent": 100,
            "DeploymentCircuitBreaker": {"Enable": True, "Rollback": True}}, "Tags": tags()},
        "GPU updates are manual and require drained work; a single GPU cannot provide surge capacity.", DependsOn="Host")
    output(body, "GpuInstance", ref("Host"))
    output(body, "AiService", att("Service", "Name"))
    return body


def app():
    body = template("Private Fargate application; shares data with EKS and is the only automatic-label worker.",
        {**parameters("Cluster", "PublicA", "PublicB", "AppSecurityGroup", "AppDiscovery", "AppImage",
                   "AppRole", "ExecutionRole", "AppSecret", "OperationsSecret", "AppLogs", "DataBucket", "DatabaseHost"),
         "WorkerEnabled": {"Type": "String", "Default": "false", "AllowedValues": ["true", "false"]}})
    body["Resources"]["Task"] = resource("ECS::TaskDefinition", {
        "Family": name("app"), "NetworkMode": "awsvpc", "RequiresCompatibilities": ["FARGATE"], "Cpu": "1024", "Memory": "2048",
        "EphemeralStorage": {"SizeInGiB": 40},
        "RuntimePlatform": {"CpuArchitecture": "X86_64", "OperatingSystemFamily": "LINUX"},
        "TaskRoleArn": ref("AppRole"), "ExecutionRoleArn": ref("ExecutionRole"),
        "ContainerDefinitions": [{
            "Name": "app", "Image": ref("AppImage"), "Essential": True, "PortMappings": [{"ContainerPort": 8080}],
            "Environment": [{"Name": key, "Value": value} for key, value in {
                "SERVER_ADDRESS": "0.0.0.0", "SERVER_PORT": "8080",
                "DB_URL": join("jdbc:postgresql://", ref("DatabaseHost"), ":5432/drivescene?sslmode=verify-full&sslrootcert=/app/rds-ca.pem"),
                "AWS_REGION": ref("AWS::Region"), "UPLOAD_S3_BUCKET": ref("DataBucket"), "UPLOAD_ROOT": "/uploads",
                "AI_SERVER_BASE_URL": join("http://ai.", ref("Project"), ".internal:8000"),
                "AUTO_LABEL_WORKER_ENABLED": ref("WorkerEnabled"), "RECORDING_WORKER_ENABLED": "false", "NUSCENES_IMPORT_ENABLED": "false"}.items()],
            "Secrets": [{"Name": key, "ValueFrom": join(ref(secret), ":", field, "::")} for key, secret, field in [
                ("DB_USERNAME", "AppSecret", "username"), ("DB_PASSWORD", "AppSecret", "password"), ("OPERATIONS_TOKEN", "OperationsSecret", "token")]],
            "HealthCheck": {"Command": ["CMD-SHELL", "curl --fail --silent http://127.0.0.1:8080/ >/dev/null"],
                            "Interval": 30, "Timeout": 5, "Retries": 5, "StartPeriod": 120},
            "LogConfiguration": {"LogDriver": "awslogs", "Options": {
                "awslogs-group": ref("AppLogs"), "awslogs-region": ref("AWS::Region"), "awslogs-stream-prefix": "app"}}}]},
        "Same image digest as EKS, without exposing a public application port; temporary space holds multipart data, ZIP and expanded mini together.")
    body["Resources"]["Service"] = resource("ECS::Service", {
        "ServiceName": name("app"), "Cluster": ref("Cluster"), "TaskDefinition": ref("Task"),
        "LaunchType": "FARGATE", "DesiredCount": 1,
        "NetworkConfiguration": {"AwsvpcConfiguration": {"Subnets": [ref("PublicA"), ref("PublicB")],
            "SecurityGroups": [ref("AppSecurityGroup")], "AssignPublicIp": "ENABLED"}},
        "ServiceRegistries": [{"RegistryArn": ref("AppDiscovery")}],
        "DeploymentConfiguration": {"MinimumHealthyPercent": 100, "MaximumPercent": 200,
            "DeploymentCircuitBreaker": {"Enable": True, "Rollback": True}}, "Tags": tags()},
        "Public address is egress-only; SSM through the EKS node is the operator's access path.")
    output(body, "AppService", att("Service", "Name"))
    return body


def web():
    body = template("Public HTTPS gateway with mandatory Cognito team login; backend and database remain private.",
        parameters("Cluster", "PublicA", "PublicB", "AppSecurityGroup", "AppLogs", "TeamUsers", "WebSecret",
                   "WebExecutionRole", "WebInfrastructureRole", "WebTaskRole"))
    resources = body["Resources"]
    resources["Client"] = resource("Cognito::UserPoolClient", {
        "UserPoolId": ref("TeamUsers"), "ClientName": name("web"), "GenerateSecret": True,
        "SupportedIdentityProviders": ["COGNITO"], "AllowedOAuthFlowsUserPoolClient": True,
        "AllowedOAuthFlows": ["code"], "AllowedOAuthScopes": ["openid"],
        "CallbackURLs": ["https://localhost/oauth2/callback"], "LogoutURLs": ["https://localhost/"],
        "AccessTokenValidity": 60, "IdTokenValidity": 60, "RefreshTokenValidity": 1,
        "TokenValidityUnits": {"AccessToken": "minutes", "IdToken": "minutes", "RefreshToken": "days"},
        "EnableTokenRevocation": True, "PreventUserExistenceErrors": "ENABLED",
        "ExplicitAuthFlows": ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"]},
        "Callback is set to the generated HTTPS endpoint by web-start before login becomes usable.")
    resources["Branding"] = resource("Cognito::ManagedLoginBranding", {
        "UserPoolId": ref("TeamUsers"), "ClientId": ref("Client"), "UseCognitoProvidedValues": True},
        "Managed login needs branding even when default styling is used.")
    resources["Gateway"] = resource("ECS::ExpressGatewayService", {
        "Cluster": ref("Cluster"), "ServiceName": name("web"), "Cpu": "256", "Memory": "512",
        "ExecutionRoleArn": ref("WebExecutionRole"), "InfrastructureRoleArn": ref("WebInfrastructureRole"),
        "TaskRoleArn": ref("WebTaskRole"), "HealthCheckPath": "/ping",
        "NetworkConfiguration": {"Subnets": [ref("PublicA"), ref("PublicB")]},
        "ScalingTarget": {"MinTaskCount": 1, "MaxTaskCount": 1}, "Tags": tags(),
        "PrimaryContainer": {
            "Image": "quay.io/oauth2-proxy/oauth2-proxy@sha256:8498b0d0ef0a7b29686414000a08aee467f02d0299c9ed1e006a8f33fc017916",
            "ContainerPort": 4180,
            "AwsLogsConfiguration": {"LogGroup": ref("AppLogs"), "LogStreamPrefix": "web"},
            "Environment": [{"Name": key, "Value": value} for key, value in {
                "OAUTH2_PROXY_HTTP_ADDRESS": "0.0.0.0:4180", "OAUTH2_PROXY_PROVIDER": "oidc",
                "OAUTH2_PROXY_CLIENT_ID": ref("Client"),
                "OAUTH2_PROXY_OIDC_ISSUER_URL": join("https://cognito-idp.", ref("AWS::Region"), ".amazonaws.com/", ref("TeamUsers")),
                "OAUTH2_PROXY_UPSTREAMS": join("http://app.", ref("Project"), ".internal:8080/"),
                "OAUTH2_PROXY_REVERSE_PROXY": "true", "OAUTH2_PROXY_EMAIL_DOMAINS": "*",
                "OAUTH2_PROXY_OIDC_EMAIL_CLAIM": "cognito:username", "OAUTH2_PROXY_OIDC_GROUPS_CLAIM": "cognito:groups",
                "OAUTH2_PROXY_ALLOWED_GROUPS": "team", "OAUTH2_PROXY_SCOPE": "openid",
                "OAUTH2_PROXY_SKIP_CLAIMS_FROM_PROFILE_URL": "true", "OAUTH2_PROXY_CODE_CHALLENGE_METHOD": "S256",
                "OAUTH2_PROXY_INSECURE_OIDC_SKIP_NONCE": "false", "OAUTH2_PROXY_SKIP_PROVIDER_BUTTON": "true",
                "OAUTH2_PROXY_COOKIE_NAME": "__Host-ds2l", "OAUTH2_PROXY_COOKIE_SECURE": "true",
                "OAUTH2_PROXY_COOKIE_HTTPONLY": "true", "OAUTH2_PROXY_COOKIE_SAMESITE": "lax",
                "OAUTH2_PROXY_COOKIE_EXPIRE": "8h", "OAUTH2_PROXY_COOKIE_REFRESH": "30m",
                "OAUTH2_PROXY_PASS_ACCESS_TOKEN": "false", "OAUTH2_PROXY_PASS_BASIC_AUTH": "false",
                "OAUTH2_PROXY_PROXY_TIMEOUT": "600s", "OAUTH2_PROXY_REQUEST_LOGGING": "false"}.items()],
            "Secrets": [{"Name": key, "ValueFrom": join(ref("WebSecret"), ":", field, "::")} for key, field in [
                ("OAUTH2_PROXY_CLIENT_SECRET", "client_secret"), ("OAUTH2_PROXY_COOKIE_SECRET", "cookie_secret")]]}},
        "Every application request requires a signed login session and team membership; /ping exposes no application data.")
    resources["AppFromWeb"] = resource("EC2::SecurityGroupIngress", {
        "GroupId": ref("AppSecurityGroup"), "SourceSecurityGroupId": {"Fn::Select": [1, {"Fn::Split": ["/",
            {"Fn::Select": [0, att("Gateway", "ECSManagedResourceArns.ServiceSecurityGroups")]}]}]},
        "IpProtocol": "tcp", "FromPort": 8080, "ToPort": 8080}, "Only the authenticated gateway can reach the private backend.")
    output(body, "Endpoint", att("Gateway", "Endpoint"))
    output(body, "WebService", att("Gateway", "ServiceArn"))
    output(body, "WebClient", ref("Client"))
    output(body, "LoadBalancer", att("Gateway", "ECSManagedResourceArns.IngressPath.LoadBalancerArn"))
    return body


BUILDERS = {"foundation": foundation, "database": database, "eks": eks, "gpu": gpu, "app": app, "web": web}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="build/cloudformation")
    args = parser.parse_args()
    destination = Path(args.output)
    destination.mkdir(parents=True, exist_ok=True)
    for key, builder in BUILDERS.items():
        (destination / (key + ".json")).write_text(json.dumps(builder(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
