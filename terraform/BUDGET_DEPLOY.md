# Priya Global — Budget Deployment Guide ($150-200/month)

## What This Deploys

A fully functional Priya Global platform on AWS at minimal cost.

| Component | Budget | Full Production |
|-----------|--------|-----------------|
| EKS Control Plane | $73/mo | $73/mo |
| EC2 Nodes | 2x t3.small = $30/mo | 28 instances = $800/mo |
| Database | db.t4g.micro = $12/mo | r6g.xlarge Multi-AZ = $600/mo |
| Message Queue | SQS = $1/mo | MSK Kafka 3-broker = $400/mo |
| Cache | Redis pod in-cluster = $0 | ElastiCache r6g.xlarge = $400/mo |
| NAT Gateway | $45/mo | $45/mo |
| ALB | $25/mo | $25/mo |
| **Total** | **~$196/mo** | **~$2,500-3,000/mo** |

## What's Different from Production

- **SQS replaces Kafka**: Same message durability (7-day retention, dead letter queue), but no consumer groups or stream processing. Fine for <1000 messages/day.
- **In-cluster Redis replaces ElastiCache**: Single Redis pod with 256MB memory. No automatic failover, but has persistent storage.
- **No RDS Proxy**: Direct database connections. Works fine with <50 concurrent connections.
- **Single AZ**: If ap-south-1a has an outage, you're down. Production uses 3 AZs.
- **2 nodes**: All 38 services share 2 t3.small nodes (4 vCPU, 4GB RAM total). Services run with tight resource limits.

## Prerequisites

1. AWS CLI configured: `aws configure --region ap-south-1`
2. Terraform >= 1.5.0: `terraform --version`
3. kubectl installed
4. S3 bucket for Terraform state (one-time setup):

```bash
aws s3api create-bucket \
  --bucket priya-global-terraform-state \
  --region ap-south-1 \
  --create-bucket-configuration LocationConstraint=ap-south-1

aws dynamodb create-table \
  --table-name priya-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-south-1
```

## Deploy

```bash
cd terraform

# Initialize
terraform init

# Preview what will be created
terraform plan -var-file=environments/budget.tfvars -out=tfplan

# Deploy (takes ~15-20 minutes, EKS cluster is the longest)
terraform apply tfplan

# Configure kubectl
$(terraform output -raw configure_kubectl_command)

# Verify cluster
kubectl get nodes
```

## Post-Deploy: Set Up In-Cluster Services

```bash
# Create Redis authentication secret (REQUIRED before deploying Redis)
kubectl create namespace priya-infra --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic redis-auth -n priya-infra \
  --from-literal=password=$(openssl rand -base64 32)

# Deploy Redis (since we're not using ElastiCache)
kubectl apply -f k8s/redis-budget.yaml

# Deploy network policies (includes priya-infra zero-trust rules)
kubectl apply -f k8s/network-policy.yaml

# Deploy namespaces
kubectl apply -f k8s/namespace.yaml

# Deploy configmap (update DATABASE_URL from terraform output first)
kubectl apply -f k8s/configmap.yaml

# Deploy services
kubectl apply -f k8s/services.yaml

# Deploy ingress (ALB)
kubectl apply -f k8s/ingress.yaml
```

## Verify

```bash
# Check all pods are running
kubectl get pods -A

# Check Redis is healthy
kubectl exec -n priya-infra deploy/redis -- redis-cli ping

# Check RDS connectivity
terraform output rds_endpoint

# Check SQS queues are created
aws sqs list-queues --queue-name-prefix priya-global
```

## Scaling Up

When you outgrow the budget tier:

1. **Add more nodes**: Edit `general_node_group_config.desired_size` in budget.tfvars
2. **Switch to Kafka**: Set `enable_msk = true` and run `terraform apply`
3. **Switch to ElastiCache**: Set `enable_elasticache = true` and remove redis-budget.yaml
4. **Go Multi-AZ**: Change to `availability_zones = ["ap-south-1a", "ap-south-1b"]`
5. **Full production**: Switch to `production.tfvars`

## Save Even More ($150/mo)

Set `enable_nat_gateway = false` in budget.tfvars to save $45/mo. Nodes will use public subnets with public IPs. Less secure but functional for early-stage testing.

## Cleanup

```bash
terraform destroy -var-file=environments/budget.tfvars
```
