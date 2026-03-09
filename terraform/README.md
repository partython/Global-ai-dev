# Priya Global Platform - Infrastructure as Code

Production-grade AWS EKS infrastructure for the Priya Global multi-tenant SaaS platform using Terraform and Kubernetes.

## Overview

This infrastructure deployment includes:

- **Amazon EKS Cluster** (Kubernetes 1.29) with 3 managed node groups
  - General Purpose (t3.xlarge): For microservices
  - AI Workload (c5.2xlarge): For ML/AI services
  - System (t3.large): For monitoring and system pods

- **36 FastAPI Microservices** organized into 4 namespaces
  - priya-core (10 services, ports 9000-9009)
  - priya-channels (7 services, ports 9010-9016)
  - priya-business (7 services, ports 9020-9026)
  - priya-advanced (12 services, ports 9030-9042)

- **Next.js Dashboard** (port 3000)

- **Data Layer**
  - Amazon RDS PostgreSQL 16 (Multi-AZ, encrypted)
  - RDS Proxy for connection pooling
  - Amazon ElastiCache Redis 7 with cluster mode
  - AWS MSK (Managed Streaming for Kafka) 3.7

- **Security & Networking**
  - VPC with public/private subnets across 3 AZs
  - AWS ALB with WAF and TLS
  - Network Policies (zero-trust)
  - IAM Roles for Service Accounts (IRSA)
  - Secrets Manager integration
  - KMS encryption for all services

- **Monitoring & Operations**
  - CloudWatch Logs for all services
  - CloudWatch Alarms for key metrics
  - VPC Flow Logs
  - Prometheus-compatible metrics
  - Application Load Balancer access logs

## Directory Structure

```
terraform/
├── main.tf                          # Root configuration
├── variables.tf                     # Input variables
├── outputs.tf                       # Output values
├── modules/
│   ├── vpc/                        # VPC module
│   ├── eks/                        # EKS cluster module
│   ├── rds/                        # RDS PostgreSQL module
│   ├── elasticache/                # Redis cluster module
│   └── msk/                        # Kafka cluster module
├── environments/
│   ├── production.tfvars           # Production environment variables
│   ├── staging.tfvars              # Staging environment variables
│   └── dev.tfvars                  # Development environment variables
└── k8s/
    ├── namespace.yaml              # Kubernetes namespaces and quotas
    ├── configmap.yaml              # Application configuration
    ├── base-deployment.yaml        # Deployment template example
    ├── services.yaml               # Service definitions
    ├── ingress.yaml                # ALB Ingress configuration
    ├── hpa.yaml                    # Horizontal Pod Autoscaling
    └── network-policy.yaml         # Network policies
```

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **Terraform** >= 1.5.0
3. **AWS CLI** configured with credentials
4. **kubectl** for Kubernetes operations
5. **Helm** (optional, for additional deployments)

## AWS Resource Requirements

### Pre-deployment Setup

1. Create S3 bucket for Terraform state:
   ```bash
   aws s3api create-bucket \
     --bucket priya-global-terraform-state \
     --region ap-south-1 \
     --create-bucket-configuration LocationConstraint=ap-south-1
   ```

2. Create DynamoDB table for state locking:
   ```bash
   aws dynamodb create-table \
     --table-name priya-terraform-locks \
     --attribute-definitions AttributeName=LockID,AttributeType=S \
     --key-schema AttributeName=LockID,KeyType=HASH \
     --billing-mode PAY_PER_REQUEST \
     --region ap-south-1
   ```

3. Create S3 bucket for ALB logs:
   ```bash
   aws s3api create-bucket \
     --bucket priya-global-alb-logs \
     --region ap-south-1 \
     --create-bucket-configuration LocationConstraint=ap-south-1
   ```

4. Create ACM certificate for HTTPS:
   ```bash
   aws acm request-certificate \
     --domain-name api.priya-global.com \
     --subject-alternative-names dashboard.priya-global.com \
     --region ap-south-1
   ```

## Deployment Instructions

### 1. Initialize Terraform

```bash
cd terraform
terraform init
```

### 2. Validate Configuration

```bash
terraform validate
terraform fmt -recursive
```

### 3. Plan Deployment

For production:
```bash
terraform plan -var-file=environments/production.tfvars -out=tfplan
```

For staging:
```bash
terraform plan -var-file=environments/staging.tfvars -out=tfplan
```

### 4. Review Plan Output

Carefully review the plan to ensure all resources match expectations.

### 5. Apply Configuration

```bash
terraform apply tfplan
```

Expected time: 20-30 minutes for full infrastructure creation.

### 6. Configure kubectl

After EKS cluster is created:

```bash
aws eks update-kubeconfig \
  --name priya-global-production \
  --region ap-south-1
```

Verify connection:
```bash
kubectl cluster-info
kubectl get nodes
```

### 7. Deploy Kubernetes Manifests

```bash
# Deploy namespaces and resource quotas
kubectl apply -f k8s/namespace.yaml

# Deploy configuration
kubectl apply -f k8s/configmap.yaml

# Deploy services
kubectl apply -f k8s/services.yaml

# Deploy Ingress
kubectl apply -f k8s/ingress.yaml

# Deploy autoscaling policies
kubectl apply -f k8s/hpa.yaml

# Deploy network policies
kubectl apply -f k8s/network-policy.yaml
```

## Microservices Deployment

Each microservice should follow the pattern in `k8s/base-deployment.yaml`. Example:

```bash
# Deploy API Gateway
kubectl apply -f k8s/base-deployment.yaml
```

For all services, update the deployment manifest with:
- Service name
- Container image
- Port numbers (9000-9042)
- Resource requests/limits
- Namespace

## Configuration Management

### Environment Variables

Update `k8s/configmap.yaml` with actual values:
- `DATABASE_URL`: RDS endpoint (from Terraform outputs)
- `REDIS_URL`: ElastiCache endpoint (from Terraform outputs)
- `KAFKA_BOOTSTRAP_SERVERS`: MSK brokers (from Terraform outputs)
- `SENTRY_DSN`: Error tracking endpoint

### Secrets

Store sensitive data in Kubernetes Secrets:

```bash
kubectl create secret generic priya-secrets \
  --from-literal=JWT_SECRET_KEY=your-secret-key \
  --from-literal=DB_PASSWORD=your-db-password \
  -n priya-core
```

## Terraform Outputs

After successful deployment, retrieve outputs:

```bash
terraform output vpc_id
terraform output eks_cluster_endpoint
terraform output eks_cluster_name
terraform output rds_endpoint
terraform output redis_endpoint
terraform output kafka_bootstrap_brokers
```

## Network Architecture

### VPC Layout (Production)

- **VPC CIDR**: 10.0.0.0/16
- **Public Subnets**: 10.0.0.0/24, 10.0.1.0/24, 10.0.2.0/24 (1 NAT Gateway)
- **Private Subnets**: 10.0.3.0/24, 10.0.4.0/24, 10.0.5.0/24

### Security Groups

- **EKS Cluster SG**: Ingress on 443 from everywhere, egress to VPC
- **EKS Nodes SG**: Ingress from cluster SG, egress to all
- **RDS SG**: Ingress on 5432 from EKS nodes only
- **Redis SG**: Ingress on 6379 from EKS nodes only
- **Kafka SG**: Ingress on 9092/9094 from EKS nodes only

### Network Policies (Kubernetes)

- Default deny all ingress in all namespaces
- Allow ingress only from authorized sources
- Restrict egress to specific ports for each service type
- Allow DNS queries to kube-system

## Scaling & Resource Management

### Node Group Autoscaling

Each node group uses AWS Auto Scaling Groups:

**Production**:
- General: 3-15 nodes
- AI Workload: 2-10 nodes
- System: 2-4 nodes

**Staging**:
- General: 2-6 nodes
- AI Workload: 1-4 nodes
- System: 1-2 nodes

### Pod Autoscaling

HPA policies scale based on:
- CPU Utilization: 65-75%
- Memory Utilization: 75-85%

Key services with HPA:
- api-gateway
- channel-router
- ai-engine
- analytics-service
- batch-processing
- stream-processor

## Monitoring & Logging

### CloudWatch Logs

- EKS Cluster Logs: `/aws/eks/{cluster}/cluster`
- RDS Logs: `/aws/rds/instance/{db}/postgresql`
- Redis Logs: `/aws/elasticache/{cluster}/{log-type}`
- MSK Logs: `/aws/msk/{cluster}/broker`

### CloudWatch Alarms

Set up for:
- EKS node CPU/memory
- RDS CPU/storage
- Redis memory/evictions
- MSK broker disk/CPU
- ALB target health

### Metrics

All services expose metrics on port 9001:
- `GET /metrics` - Prometheus format

## Disaster Recovery

### Backup Strategy

- **RDS**: Automated daily snapshots, 30-day retention
- **Redis**: Snapshot backups enabled
- **Kubernetes State**: ETCD backups via EKS
- **Terraform State**: Versioned in S3 with MFA delete protection

### Recovery Procedures

1. **RDS Restore**:
   ```bash
   aws rds restore-db-instance-from-db-snapshot \
     --db-instance-identifier new-instance-name \
     --db-snapshot-identifier snapshot-id
   ```

2. **Kubernetes Redeploy**:
   ```bash
   kubectl apply -f k8s/
   ```

3. **Scale Back**:
   ```bash
   kubectl autoscale deployment api-gateway \
     --min=3 --max=15 -n priya-core
   ```

## Cost Optimization

### Recommendations

1. **Use Reserved Instances** for predictable workloads
2. **Spot Instances** for non-critical AI workloads
3. **Auto-scaling** based on actual demand
4. **Consolidate** logs with CloudWatch log groups
5. **Review** unused EBS volumes monthly

### Cost Estimation (Production, Monthly)

- EKS Cluster: ~$73 (control plane)
- EC2 Nodes (28 instances): ~$800
- RDS Multi-AZ (r6g.xlarge): ~$600
- ElastiCache Redis (r6g.xlarge): ~$400
- MSK (3x m5.large): ~$400
- Data Transfer: ~$200
- **Total Estimated**: ~$2,500-3,000/month

## Troubleshooting

### EKS Issues

Check node status:
```bash
kubectl get nodes
kubectl describe node <node-name>
kubectl logs -n kube-system pod/<pod-name>
```

### RDS Connection Issues

```bash
# Check security group
aws ec2 describe-security-groups --group-ids sg-xxxxxx

# Test connection
psql -h <rds-endpoint> -U admin -d priyaglobalproduction
```

### Kafka Connection Issues

```bash
# Get bootstrap brokers
aws kafka get-bootstrap-brokers --cluster-arn <cluster-arn>

# Test connection
aws kafka batch-describe-cluster-broker-nodes --cluster-arn <cluster-arn>
```

### Application Logs

```bash
# View pod logs
kubectl logs deployment/api-gateway -n priya-core

# Stream logs
kubectl logs -f deployment/api-gateway -n priya-core

# Previous logs (if crashed)
kubectl logs deployment/api-gateway --previous -n priya-core
```

## Security Considerations

1. **IAM**: Use least privilege principle
2. **RBAC**: Implement Kubernetes RBAC policies
3. **Secrets**: Never commit secrets to git
4. **TLS**: All communication encrypted
5. **WAF**: ALB protected by AWS WAF
6. **Encryption**: At-rest (KMS) and in-transit (TLS)
7. **Network**: VPC isolation, security groups, network policies
8. **Audit**: CloudTrail logging all API calls

## Cleanup

To destroy all infrastructure:

```bash
terraform destroy -var-file=environments/production.tfvars
```

This will:
1. Delete EKS cluster and node groups
2. Remove RDS instance (with final snapshot)
3. Delete Redis cluster
4. Remove Kafka cluster
5. Destroy VPC and related networking

**Warning**: This is destructive and will delete all data not backed up.

## Support & Documentation

- [Terraform AWS Provider Docs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [EKS User Guide](https://docs.aws.amazon.com/eks/latest/userguide/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Priya Global Architecture Docs](./ARCHITECTURE.md)

## License

Proprietary - Priya Global Platform
