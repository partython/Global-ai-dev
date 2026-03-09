# Priya Global Platform - Quick Reference Guide

## Essential Commands

### Terraform Commands

```bash
# Initialize backend
terraform init

# Validate configuration
terraform validate

# Format code
terraform fmt -recursive

# Plan changes (production)
terraform plan -var-file=environments/production.tfvars -out=tfplan

# Apply changes
terraform apply tfplan

# Destroy infrastructure (DANGEROUS!)
terraform destroy -var-file=environments/production.tfvars

# Get specific output
terraform output rds_endpoint
terraform output kafka_bootstrap_brokers
terraform output eks_cluster_name

# Save outputs to JSON
terraform output -json > outputs.json
```

### Kubernetes Commands

```bash
# Update kubeconfig
aws eks update-kubeconfig --name priya-global-production --region ap-south-1

# Check cluster info
kubectl cluster-info
kubectl get nodes
kubectl get pods -A

# Apply manifests
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/services.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/network-policy.yaml

# View resources
kubectl get namespaces
kubectl get deployments -n priya-core
kubectl get services -A
kubectl get ingress -A
kubectl get hpa -A
kubectl get networkpolicies -A

# Debug pods
kubectl get pods -n priya-core
kubectl describe pod <pod-name> -n priya-core
kubectl logs deployment/api-gateway -n priya-core
kubectl logs -f deployment/api-gateway -n priya-core

# Scale deployment
kubectl scale deployment api-gateway --replicas=5 -n priya-core

# Port forward
kubectl port-forward svc/api-gateway 9000:9000 -n priya-core

# Exec into pod
kubectl exec -it <pod-name> -n priya-core -- /bin/sh

# Delete resources
kubectl delete deployment api-gateway -n priya-core
kubectl delete service api-gateway -n priya-core
```

### AWS CLI Commands

```bash
# EKS
aws eks describe-cluster --name priya-global-production --region ap-south-1
aws eks list-nodegroups --cluster-name priya-global-production
aws eks describe-nodegroup --cluster-name priya-global-production --nodegroup-name <nodegroup-name>

# RDS
aws rds describe-db-instances --db-instance-identifier priya-global-production
aws rds describe-db-snapshots --db-instance-identifier priya-global-production
aws rds modify-db-instance --db-instance-identifier priya-global-production --apply-immediately

# ElastiCache
aws elasticache describe-cache-clusters --cache-cluster-id priya-global-production
aws elasticache describe-cache-nodes --cache-cluster-id priya-global-production

# MSK
aws kafka list-clusters
aws kafka describe-cluster --cluster-arn <cluster-arn>
aws kafka get-bootstrap-brokers --cluster-arn <cluster-arn>

# CloudWatch
aws logs describe-log-groups | grep priya
aws logs tail /aws/eks/priya-global-production/cluster --follow

# Security Groups
aws ec2 describe-security-groups --filters Name=group-name,Values=priya-*

# VPC
aws ec2 describe-vpcs --filters Name=tag:Name,Values=priya-*
aws ec2 describe-subnets --filters Name=vpc-id,Values=<vpc-id>
```

## File Locations

| File | Purpose |
|------|---------|
| `terraform/main.tf` | Root configuration with module calls |
| `terraform/variables.tf` | Input variables definition |
| `terraform/outputs.tf` | Output values |
| `terraform/modules/vpc/main.tf` | VPC and networking |
| `terraform/modules/eks/main.tf` | EKS cluster and node groups |
| `terraform/modules/rds/main.tf` | PostgreSQL database |
| `terraform/modules/elasticache/main.tf` | Redis cluster |
| `terraform/modules/msk/main.tf` | Kafka cluster |
| `terraform/environments/production.tfvars` | Production settings |
| `terraform/k8s/namespace.yaml` | Namespaces and quotas |
| `terraform/k8s/configmap.yaml` | Application configuration |
| `terraform/k8s/services.yaml` | Service definitions |
| `terraform/k8s/ingress.yaml` | Load balancer config |
| `terraform/k8s/hpa.yaml` | Auto-scaling policies |
| `terraform/k8s/network-policy.yaml` | Network security |

## Port Reference

| Service | Namespace | Port | Type |
|---------|-----------|------|------|
| Dashboard | priya-core | 3000 | HTTP |
| API Gateway | priya-core | 9000 | HTTP |
| Auth Service | priya-core | 9000 | HTTP |
| User Service | priya-core | 9001 | HTTP |
| Tenant Service | priya-core | 9002 | HTTP |
| Organization Service | priya-core | 9003 | HTTP |
| Permission Service | priya-core | 9004 | HTTP |
| Audit Service | priya-core | 9005 | HTTP |
| Notification Service | priya-core | 9006 | HTTP |
| Webhook Service | priya-core | 9007 | HTTP |
| Health Check Service | priya-core | 9008 | HTTP |
| Logging Service | priya-core | 9009 | HTTP |
| Email Service | priya-channels | 9010 | HTTP |
| SMS Service | priya-channels | 9011 | HTTP |
| WhatsApp Service | priya-channels | 9012 | HTTP |
| Push Notification Service | priya-channels | 9013 | HTTP |
| Channel Router | priya-channels | 9014 | HTTP |
| Schedule Service | priya-channels | 9015 | HTTP |
| Template Service | priya-channels | 9016 | HTTP |
| Analytics Service | priya-business | 9020 | HTTP |
| Reporting Service | priya-business | 9021 | HTTP |
| Billing Service | priya-business | 9022 | HTTP |
| Subscription Service | priya-business | 9023 | HTTP |
| Payment Service | priya-business | 9024 | HTTP |
| Usage Service | priya-business | 9025 | HTTP |
| Compliance Service | priya-business | 9026 | HTTP |
| AI Engine | priya-advanced | 9030 | HTTP |
| ML Pipeline | priya-advanced | 9031 | HTTP |
| NLP Service | priya-advanced | 9032 | HTTP |
| Sentiment Service | priya-advanced | 9033 | HTTP |
| Recommendation Service | priya-advanced | 9034 | HTTP |
| Personalization Service | priya-advanced | 9035 | HTTP |
| Data Pipeline | priya-advanced | 9036 | HTTP |
| Batch Processing | priya-advanced | 9037 | HTTP |
| Stream Processor | priya-advanced | 9038 | HTTP |
| Feature Service | priya-advanced | 9039 | HTTP |
| Search Service | priya-advanced | 9040 | HTTP |
| Cache Warmer | priya-advanced | 9041 | HTTP |
| Performance Monitor | priya-advanced | 9042 | HTTP |
| RDS PostgreSQL | Private | 5432 | TCP |
| Redis | Private | 6379 | TCP |
| Kafka | Private | 9092/9094 | TCP |
| Metrics | All | 9001 | HTTP |

## Important Endpoints

| Service | Endpoint | Type |
|---------|----------|------|
| RDS Endpoint | `priya-global-production.xxxxx.rds.amazonaws.com` | PostgreSQL |
| RDS Proxy | `priya-global-production.proxy.xxxxx.rds.amazonaws.com` | PostgreSQL |
| Redis Endpoint | `priya-global-production.xxxxx.cache.amazonaws.com` | Redis |
| Kafka Brokers | `b-1...kafka.amazonaws.com:9092` | Kafka |
| EKS Endpoint | `https://xxxxxxxx.eks.amazonaws.com` | Kubernetes API |
| ALB DNS | `priya-alb-xxxxx.ap-south-1.elb.amazonaws.com` | Load Balancer |
| API URL | `https://api.priya-global.com` | HTTPS |
| Dashboard URL | `https://dashboard.priya-global.com` | HTTPS |

## Namespace Resource Limits (Production)

| Namespace | CPU Request | Memory Request | CPU Limit | Memory Limit | Max Pods |
|-----------|------------|-----------------|-----------|--------------|----------|
| priya-core | 100 | 200Gi | 200 | 400Gi | 500 |
| priya-channels | 100 | 200Gi | 200 | 400Gi | 300 |
| priya-business | 50 | 100Gi | 100 | 200Gi | 200 |
| priya-advanced | 50 | 100Gi | 100 | 200Gi | 200 |
| priya-monitoring | 20 | 50Gi | 50 | 100Gi | 100 |

## HPA Configuration

| Service | Min Replicas | Max Replicas | CPU Target | Memory Target |
|---------|-------------|--------------|-----------|---------------|
| api-gateway | 3 | 15 | 70% | 80% |
| channel-router | 2 | 10 | 65% | 75% |
| ai-engine | 2 | 8 | 75% | 85% |
| email-service | 2 | 6 | 70% | 80% |
| analytics-service | 2 | 8 | 75% | 85% |
| batch-processing | 1 | 5 | 80% | 85% |
| stream-processor | 2 | 8 | 70% | 80% |

## Troubleshooting Quick Links

### Pod Issues
```bash
# Check pod status
kubectl get pods -n priya-core
kubectl describe pod <pod> -n priya-core

# Check logs
kubectl logs <pod> -n priya-core

# Previous logs (if crashed)
kubectl logs <pod> --previous -n priya-core

# Debug node
kubectl describe node <node>
```

### Database Issues
```bash
# Check RDS status
aws rds describe-db-instances --db-instance-identifier priya-global-production

# Check connections
psql -h <endpoint> -U admin -d priyaglobalproduction
```

### Network Issues
```bash
# Check security groups
aws ec2 describe-security-groups --group-ids <sg-id>

# Check network policies
kubectl get networkpolicies -A
kubectl describe networkpolicy <policy> -n <namespace>

# Test connectivity
kubectl exec -it <pod> -n <namespace> -- curl <service>:port/health
```

### Scaling Issues
```bash
# Check HPA status
kubectl get hpa -n priya-core
kubectl describe hpa <hpa-name> -n priya-core

# Check metrics server
kubectl get deployment metrics-server -n kube-system

# Check node scaling
aws ec2 describe-auto-scaling-groups --auto-scaling-group-names <asg-name>
```

## Common Issues & Fixes

| Issue | Symptom | Solution |
|-------|---------|----------|
| Pod CrashLoop | Pod keeps restarting | `kubectl logs <pod>`, check resources |
| Pending Pod | Pod stuck in Pending | Check node availability, resource quotas |
| Connection Refused | Can't reach service | Check security groups, network policies |
| Out of Memory | OOM kills | Increase memory limits, add more nodes |
| High CPU | Slow response | Check application code, increase HPA threshold |
| Database Connection Timeout | DB unreachable | Check security group, RDS proxy status |
| Kafka Connection Error | Producer/consumer fails | Verify broker list, IAM permissions |

## Useful Links

- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest)
- [EKS User Guide](https://docs.aws.amazon.com/eks/)
- [Kubernetes Docs](https://kubernetes.io/docs/)
- [AWS Console](https://console.aws.amazon.com/)

## Key Metrics to Monitor

```
CPU Utilization: Target 70-80%
Memory Utilization: Target 75-85%
Pod Count: Within namespace limits
RDS CPU: < 80%
RDS Storage: > 10% free
Redis Memory: < 80% used
Kafka Lag: < 1 min behind
Error Rate: < 0.1%
Latency P99: < 500ms
```

## Backup Verification

```bash
# RDS snapshots
aws rds describe-db-snapshots --db-instance-identifier priya-global-production

# Redis snapshots
aws elasticache describe-snapshots --cache-cluster-id priya-global-production

# Check Terraform state backups
aws s3 ls s3://priya-global-terraform-state/ --recursive
```

## Emergency Procedures

### If EKS Cluster is Down
1. Check control plane logs: `aws logs tail /aws/eks/priya-global-production/cluster`
2. Check node groups: `aws eks describe-nodegroup --cluster-name priya-global-production`
3. Scale nodes if needed: `aws autoscaling set-desired-capacity`

### If RDS is Down
1. Check RDS status: `aws rds describe-db-instances`
2. Check security group: `aws ec2 describe-security-groups`
3. Restore from snapshot if needed

### If Kafka is Down
1. Check cluster: `aws kafka describe-cluster --cluster-arn`
2. Check broker status: `aws kafka batch-describe-cluster-broker-nodes`
3. Check IAM permissions

### Quick Rollback
```bash
# If deployment fails, scale down
kubectl scale deployment <service> --replicas=0 -n <namespace>

# Then revert to previous version
kubectl rollout undo deployment/<service> -n <namespace>
```

---

Last Updated: 2026-03-06
Status: Production Ready
