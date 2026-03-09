# Priya Global Platform - Deployment Checklist

## Pre-Deployment Phase

### AWS Account Setup
- [ ] AWS Account created and IAM user with appropriate permissions
- [ ] AWS CLI installed and configured
- [ ] Region set to `ap-south-1`
- [ ] AWS credentials exported (or using credential file)

### Infrastructure Preparation
- [ ] S3 bucket created: `priya-global-terraform-state`
- [ ] DynamoDB table created: `priya-terraform-locks`
- [ ] S3 bucket created: `priya-global-alb-logs`
- [ ] ACM certificate requested for:
  - [ ] `api.priya-global.com`
  - [ ] `dashboard.priya-global.com`
- [ ] Domain DNS records prepared (Route53 hosted zone ready)
- [ ] VPN/Bastion access configured (optional for private access)

### Tools Installation
- [ ] Terraform >= 1.5.0 installed and verified
- [ ] kubectl >= 1.29 installed and verified
- [ ] AWS CLI >= 2.0 installed and verified
- [ ] Helm >= 3.12 installed (optional for add-ons)
- [ ] jq installed for JSON processing

### Repository Access
- [ ] Git repository cloned with all code
- [ ] AWS ECR registry created for Docker images
- [ ] Docker images built and pushed to ECR for:
  - [ ] All 36 FastAPI microservices
  - [ ] Next.js dashboard

## Terraform Deployment Phase

### Phase 1: Validation (5 minutes)

```bash
cd terraform/
terraform init
terraform validate
terraform fmt -recursive
```

- [ ] No validation errors
- [ ] Code formatting correct
- [ ] Backend S3 access verified

### Phase 2: Planning (10 minutes)

For production:
```bash
terraform plan -var-file=environments/production.tfvars -out=tfplan
```

- [ ] Plan shows expected resource count (~50-60 resources)
- [ ] No unexpected deletions
- [ ] Correct environment variables (ap-south-1, production, etc.)
- [ ] Plan saved to tfplan file

### Phase 3: Apply (30-40 minutes)

```bash
terraform apply tfplan
```

Monitor progress:
- [ ] VPC creation (2-3 min)
- [ ] EKS cluster creation (12-15 min) - LONGEST STEP
- [ ] Node groups creation (8-10 min)
- [ ] RDS instance creation (5-7 min)
- [ ] Redis cluster creation (3-5 min)
- [ ] MSK cluster creation (8-10 min)
- [ ] Supporting resources (security groups, IAM, etc.)

### Phase 4: Verification (5 minutes)

```bash
# Retrieve all outputs
terraform output -json > cluster-outputs.json

# Key outputs to verify:
terraform output eks_cluster_name
terraform output eks_cluster_endpoint
terraform output rds_endpoint
terraform output redis_endpoint
terraform output kafka_bootstrap_brokers
```

- [ ] VPC created with correct CIDR
- [ ] EKS cluster in ACTIVE state
- [ ] All 3 node groups ACTIVE
- [ ] RDS instance in AVAILABLE state
- [ ] Redis cluster AVAILABLE
- [ ] MSK cluster in ACTIVE state
- [ ] All outputs captured

## Kubernetes Configuration Phase

### Phase 1: Cluster Access (2 minutes)

```bash
aws eks update-kubeconfig \
  --name priya-global-production \
  --region ap-south-1

kubectl cluster-info
kubectl get nodes
```

- [ ] kubectl can connect to cluster
- [ ] Nodes are in Ready state
- [ ] kube-system pods running

### Phase 2: RBAC & Access Control (5 minutes)

```bash
# Create RBAC policy for deployment user
kubectl apply -f k8s/rbac-policy.yaml
```

- [ ] ServiceAccounts created
- [ ] ClusterRoles assigned
- [ ] RBAC policies in place

### Phase 3: Namespaces & Quotas (3 minutes)

```bash
kubectl apply -f k8s/namespace.yaml
```

Verify:
```bash
kubectl get namespaces
kubectl describe ns priya-core
kubectl describe resourcequota -n priya-core
```

- [ ] 6 namespaces created
- [ ] Resource quotas applied
- [ ] Limit ranges configured

### Phase 4: Network Policies (5 minutes)

```bash
kubectl apply -f k8s/network-policy.yaml
```

Verify:
```bash
kubectl get networkpolicies -A
kubectl describe networkpolicy allow-core-communication -n priya-core
```

- [ ] Default deny-all rules applied
- [ ] Ingress policies configured
- [ ] Egress policies configured

### Phase 5: Configuration Management (5 minutes)

Update `k8s/configmap.yaml` with actual values:
```bash
# Update database endpoint
sed -i 's/DATABASE_URL: .*/DATABASE_URL: "postgresql:\/\/admin:password@<RDS_ENDPOINT>:5432\/priyaglobalproduction"/g' k8s/configmap.yaml

# Update Redis endpoint
sed -i 's/REDIS_URL: .*/REDIS_URL: "redis:\/\/<REDIS_ENDPOINT>:6379"/g' k8s/configmap.yaml

# Update Kafka brokers
sed -i 's/KAFKA_BOOTSTRAP_SERVERS: .*/KAFKA_BOOTSTRAP_SERVERS: "<MSK_BROKERS>"/g' k8s/configmap.yaml

kubectl apply -f k8s/configmap.yaml
```

- [ ] ConfigMap created with actual endpoints
- [ ] Sensitive values use Secrets not ConfigMap
- [ ] Configuration verified

### Phase 6: Secrets Management (5 minutes)

```bash
# Create secrets
kubectl create secret generic priya-secrets \
  --from-literal=JWT_SECRET_KEY=<actual-jwt-key> \
  --from-literal=DB_PASSWORD=<actual-db-password> \
  --from-literal=REDIS_AUTH_TOKEN=<actual-redis-token> \
  -n priya-core

# Verify
kubectl describe secret priya-secrets -n priya-core
```

- [ ] Secrets created in all namespaces
- [ ] No secrets in ConfigMaps
- [ ] Secret values verified (not logged)

## Application Deployment Phase

### Phase 1: Services & Ingress (10 minutes)

```bash
kubectl apply -f k8s/services.yaml
kubectl apply -f k8s/ingress.yaml

# Verify
kubectl get services -A
kubectl get ingress -A
```

- [ ] 40+ services created
- [ ] ClusterIP services for internal communication
- [ ] ALB Ingress created
- [ ] ALB status ACTIVE
- [ ] DNS propagated (check Route53)

### Phase 2: Autoscaling Configuration (3 minutes)

```bash
kubectl apply -f k8s/hpa.yaml

# Verify
kubectl get hpa -A
kubectl describe hpa api-gateway-hpa -n priya-core
```

- [ ] HPA policies created
- [ ] Min/max replicas configured
- [ ] Scaling targets verified

### Phase 3: Deploy Microservices (30-60 minutes)

For each microservice:

```bash
# Create deployment manifest using base-deployment.yaml template
# Update: app name, image, port, namespace, resources

kubectl apply -f deployments/api-gateway-deployment.yaml
kubectl apply -f deployments/auth-service-deployment.yaml
# ... repeat for all 36 services

# Monitor rollout
kubectl rollout status deployment/api-gateway -n priya-core
kubectl get pods -n priya-core -l app=api-gateway
```

- [ ] All 36 FastAPI services deployed
- [ ] Dashboard (Next.js) deployed
- [ ] Pods running and ready
- [ ] No crash loops or pending pods

### Phase 4: Health Checks (10 minutes)

```bash
# Check pod health
kubectl get pods -A
kubectl describe pod <pod-name> -n <namespace>

# Check logs for errors
kubectl logs deployment/api-gateway -n priya-core

# Test health endpoints
kubectl exec -it <pod-name> -n priya-core -- curl localhost:9000/health

# Test service communication
kubectl exec -it <pod-name> -n priya-core -- curl auth-service.priya-core:9000/health
```

- [ ] All pods Running and Ready
- [ ] No errors in logs
- [ ] Health endpoints responding
- [ ] Inter-service communication working

### Phase 5: Load Balancer Testing (5 minutes)

```bash
# Get ALB DNS name
kubectl get ingress -n priya-core

# Test API endpoint (via ALB)
curl -v https://api.priya-global.com/health

# Test dashboard (via ALB)
curl -v https://dashboard.priya-global.com/
```

- [ ] ALB DNS name resolved
- [ ] HTTPS working (certificate valid)
- [ ] API returning 200 OK
- [ ] Dashboard accessible

## Post-Deployment Verification

### Infrastructure Verification (15 minutes)

```bash
# RDS
aws rds describe-db-instances --db-instance-identifier priya-global-production

# Redis
aws elasticache describe-cache-clusters --cache-cluster-id priya-global-production

# Kafka
aws kafka list-clusters

# EKS
aws eks describe-cluster --name priya-global-production
```

- [ ] RDS Multi-AZ AVAILABLE
- [ ] Redis in-cluster-maintenance FAILED = FALSE
- [ ] MSK cluster status ACTIVE
- [ ] EKS cluster status ACTIVE

### Monitoring Setup (15 minutes)

```bash
# Verify CloudWatch Logs
aws logs describe-log-groups | grep "priya"

# Create alarms
aws cloudwatch put-metric-alarm --alarm-name priya-rds-cpu-high \
  --alarm-description "Alert when RDS CPU > 80%" \
  --metric-name CPUUtilization \
  --namespace AWS/RDS \
  --statistic Average \
  --period 300 \
  --threshold 80 \
  --comparison-operator GreaterThanThreshold

# Create SNS topic for alerts
aws sns create-topic --name priya-alerts
```

- [ ] CloudWatch Logs created for all services
- [ ] CloudWatch Alarms configured
- [ ] SNS topics for notifications created
- [ ] Dashboards created

### Security Verification (10 minutes)

```bash
# Check security groups
aws ec2 describe-security-groups --filters Name=group-name,Values=priya-*

# Check IAM roles
aws iam list-roles | grep priya

# Check KMS keys
aws kms describe-key --key-id alias/priya-global-production-*

# Check network policies
kubectl get networkpolicies -A
```

- [ ] Security groups have least privilege
- [ ] IAM roles properly scoped
- [ ] KMS keys for encryption
- [ ] Network policies enforced

### Backup Verification (5 minutes)

```bash
# RDS backup
aws rds describe-db-snapshots --db-instance-identifier priya-global-production

# Verify Terraform state backup
aws s3 ls s3://priya-global-terraform-state/

# Check DynamoDB locks table
aws dynamodb scan --table-name priya-terraform-locks
```

- [ ] RDS automated backups enabled
- [ ] First backup completed
- [ ] Terraform state in S3
- [ ] State locking working

## Operational Handoff

### Documentation Review
- [ ] README.md reviewed and updated
- [ ] Architecture documentation complete
- [ ] Runbook for common tasks created
- [ ] Troubleshooting guide prepared

### Team Training
- [ ] Deploy process walkthrough (30 min)
- [ ] Monitoring & alerting (30 min)
- [ ] Incident response procedures (30 min)
- [ ] Backup & recovery procedures (30 min)

### Access Management
- [ ] kubectl access configured for all operators
- [ ] AWS Console access granted
- [ ] CloudWatch dashboard shared
- [ ] Slack/PagerDuty integration setup

## Go-Live Checklist

### Final Validation (1 hour before)
- [ ] All health checks passing
- [ ] Load testing completed
- [ ] DNS fully propagated
- [ ] SSL certificates valid
- [ ] Database replication verified
- [ ] Backups verified
- [ ] Monitoring active

### Cutover Execution
- [ ] Traffic gradually shifted to new infrastructure
- [ ] Old infrastructure kept running as fallback
- [ ] Monitoring alerts active
- [ ] Support team on standby
- [ ] Incident response plan activated

### Post-Go-Live (First 24 hours)
- [ ] Monitor error rates
- [ ] Monitor latency
- [ ] Monitor resource utilization
- [ ] Check database replication lag
- [ ] Review logs for unexpected errors
- [ ] Scale as needed based on actual traffic
- [ ] Customer communication (if any downtime)

## Rollback Plan

If critical issues occur:

```bash
# Destroy new infrastructure
terraform destroy -var-file=environments/production.tfvars

# Route traffic back to old infrastructure
# (update Route53, load balancer, etc.)

# Post-mortem and analysis
```

- [ ] Rollback decision point identified (30 min post-cutover)
- [ ] Rollback procedure documented
- [ ] Old infrastructure still available
- [ ] DNS rollback timing < 2 min

## Sign-Off

- [ ] Infrastructure Owner: _____________ Date: _______
- [ ] Ops Team Lead: __________________ Date: _______
- [ ] Security Lead: ___________________ Date: _______
- [ ] DevOps Engineer: ________________ Date: _______
