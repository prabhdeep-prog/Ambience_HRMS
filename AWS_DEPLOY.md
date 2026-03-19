# Horilla HRMS — Complete AWS Deployment Guide
# ECS Fargate + ECR + NeonDB + ElastiCache Redis + S3

---

## Architecture Overview

```
Internet
   │
   ▼
Application Load Balancer (ALB)  ← HTTPS :443
   │
   ├── /  ──────────────► ECS Service: web       (Gunicorn, 2+ tasks)
   │
   └── Internal only ──► ECS Service: worker     (Celery, 2 tasks)
                    └──► ECS Service: beat        (Celery Beat, 1 task — NEVER scale)

ECS tasks share:
  - NeonDB (PostgreSQL)        ← external, serverless
  - ElastiCache Redis          ← cache + celery broker
  - S3 Bucket                  ← media files + static assets
  - Secrets Manager            ← all secrets (DATABASE_URL, SECRET_KEY …)
  - CloudWatch Logs            ← centralised logging
```

---

## Prerequisites

```bash
# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip && sudo ./aws/install

# Configure credentials
aws configure
# AWS Access Key ID: <your key>
# AWS Secret Access Key: <your secret>
# Default region: us-east-1
# Default output format: json

# Verify
aws sts get-caller-identity
```

---

## 1. Set Shell Variables (run once — used in all commands below)

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export APP_NAME=horilla-hrms
export ECR_REPO=${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}
export IMAGE_TAG=$(git rev-parse --short HEAD)   # e.g. "a3f8c2d"

echo "Account : $AWS_ACCOUNT_ID"
echo "ECR URL : $ECR_REPO"
echo "Tag     : $IMAGE_TAG"
```

---

## 2. Amazon ECR — Create Repository & Push Image

### 2a. Create ECR repository
```bash
aws ecr create-repository \
    --repository-name ${APP_NAME} \
    --region ${AWS_REGION} \
    --image-scanning-configuration scanOnPush=true \
    --image-tag-mutability MUTABLE
```

### 2b. Login Docker to ECR
```bash
aws ecr get-login-password --region ${AWS_REGION} \
    | docker login --username AWS --password-stdin \
      ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
```

### 2c. Build the production image
```bash
docker build \
    --platform linux/amd64 \
    --target runtime \
    -t ${APP_NAME}:${IMAGE_TAG} \
    -t ${APP_NAME}:latest \
    .
```

### 2d. Tag and push to ECR
```bash
docker tag ${APP_NAME}:${IMAGE_TAG} ${ECR_REPO}:${IMAGE_TAG}
docker tag ${APP_NAME}:${IMAGE_TAG} ${ECR_REPO}:latest

docker push ${ECR_REPO}:${IMAGE_TAG}
docker push ${ECR_REPO}:latest

echo "Image pushed: ${ECR_REPO}:${IMAGE_TAG}"
```

---

## 3. AWS Secrets Manager — Store Secrets

Never put secrets in environment variables directly in the task definition.
Use Secrets Manager and reference them by ARN.

```bash
# Store all secrets as a single JSON secret
aws secretsmanager create-secret \
    --name "horilla/production" \
    --region ${AWS_REGION} \
    --secret-string '{
        "SECRET_KEY": "your-50-char-django-secret-key-here",
        "DATABASE_URL": "postgresql://user:pass@ep-xxx.neon.tech/horilla?sslmode=require",
        "ADMIN_PASSWORD": "ChangeMe123!",
        "AWS_ACCESS_KEY_ID": "AKIA...",
        "AWS_SECRET_ACCESS_KEY": "...",
        "EMAIL_HOST_PASSWORD": "SG...."
    }'

# Note the ARN — you'll reference it in the task definition
aws secretsmanager describe-secret --secret-id horilla/production \
    --query ARN --output text
```

---

## 4. S3 Bucket — Media & Static Files

```bash
BUCKET_NAME=horilla-hrms-media-${AWS_ACCOUNT_ID}

# Create bucket
aws s3 mb s3://${BUCKET_NAME} --region ${AWS_REGION}

# Block public access (files served via signed URLs or CloudFront)
aws s3api put-public-access-block \
    --bucket ${BUCKET_NAME} \
    --public-access-block-configuration \
      "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Enable versioning (protects media uploads)
aws s3api put-bucket-versioning \
    --bucket ${BUCKET_NAME} \
    --versioning-configuration Status=Enabled

echo "S3 bucket: s3://${BUCKET_NAME}"
```

---

## 5. ElastiCache Redis — Cache + Celery Broker

```bash
# Create a subnet group (use your VPC subnet IDs)
aws elasticache create-cache-subnet-group \
    --cache-subnet-group-name horilla-redis-subnets \
    --cache-subnet-group-description "Horilla Redis Subnet Group" \
    --subnet-ids subnet-xxxxxxxxxxxxxxxxx subnet-yyyyyyyyyyyyyyyyy

# Create Redis cluster (single node for cost, multi-AZ for production)
aws elasticache create-cache-cluster \
    --cache-cluster-id horilla-redis \
    --cache-node-type cache.t4g.small \
    --engine redis \
    --engine-version 7.0 \
    --num-cache-nodes 1 \
    --cache-subnet-group-name horilla-redis-subnets \
    --security-group-ids sg-xxxxxxxxxxxxxxxxx

# Get the Redis endpoint (after cluster is available ~5 min)
aws elasticache describe-cache-clusters \
    --cache-cluster-id horilla-redis \
    --show-cache-node-info \
    --query 'CacheClusters[0].CacheNodes[0].Endpoint.Address' \
    --output text
# Example: horilla-redis.xxxxxx.0001.use1.cache.amazonaws.com
```

---

## 6. ECS Cluster + IAM Roles

### 6a. Create ECS cluster
```bash
aws ecs create-cluster \
    --cluster-name horilla-production \
    --capacity-providers FARGATE FARGATE_SPOT \
    --default-capacity-provider-strategy \
        capacityProvider=FARGATE,weight=1 \
    --settings name=containerInsights,value=enabled
```

### 6b. Create ECS Task Execution Role (allows ECS to pull images + read secrets)
```bash
# Trust policy
cat > /tmp/ecs-trust.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
    --role-name HorillaECSTaskExecutionRole \
    --assume-role-policy-document file:///tmp/ecs-trust.json

# Attach managed policies
aws iam attach-role-policy \
    --role-name HorillaECSTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

aws iam attach-role-policy \
    --role-name HorillaECSTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMReadOnlyAccess

# Allow reading secrets
cat > /tmp/secrets-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["secretsmanager:GetSecretValue"],
    "Resource": "arn:aws:secretsmanager:${AWS_REGION}:${AWS_ACCOUNT_ID}:secret:horilla/*"
  }]
}
EOF

aws iam put-role-policy \
    --role-name HorillaECSTaskExecutionRole \
    --policy-name HorillaSecretsAccess \
    --policy-document file:///tmp/secrets-policy.json
```

---

## 7. CloudWatch Log Groups

```bash
aws logs create-log-group --log-group-name /ecs/horilla/web    --region ${AWS_REGION}
aws logs create-log-group --log-group-name /ecs/horilla/worker --region ${AWS_REGION}
aws logs create-log-group --log-group-name /ecs/horilla/beat   --region ${AWS_REGION}

# Retain logs for 30 days
aws logs put-retention-policy --log-group-name /ecs/horilla/web    --retention-in-days 30
aws logs put-retention-policy --log-group-name /ecs/horilla/worker --retention-in-days 30
aws logs put-retention-policy --log-group-name /ecs/horilla/beat   --retention-in-days 30
```

---

## 8. ECS Task Definitions

Save each file and register it.

### 8a. Web Task Definition
Save as `task-web.json`:

```json
{
  "family": "horilla-web",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::ACCOUNT_ID:role/HorillaECSTaskExecutionRole",
  "taskRoleArn":      "arn:aws:iam::ACCOUNT_ID:role/HorillaECSTaskExecutionRole",
  "containerDefinitions": [{
    "name": "web",
    "image": "ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/horilla-hrms:latest",
    "essential": true,
    "portMappings": [{"containerPort": 8000, "protocol": "tcp"}],
    "command": ["/app/entrypoint.sh"],
    "environment": [
      {"name": "DEBUG",                  "value": "False"},
      {"name": "DJANGO_SETTINGS_MODULE", "value": "horilla.settings"},
      {"name": "PORT",                   "value": "8000"},
      {"name": "ALLOWED_HOSTS",          "value": "*.amazonaws.com,yourdomain.com"},
      {"name": "AWS_STORAGE_BUCKET_NAME","value": "horilla-hrms-media-ACCOUNT_ID"},
      {"name": "AWS_S3_REGION_NAME",     "value": "us-east-1"},
      {"name": "USE_S3",                 "value": "True"},
      {"name": "CELERY_BROKER_URL",      "value": "redis://horilla-redis.xxxxx.cache.amazonaws.com:6379/0"},
      {"name": "CACHE_REDIS_URL",        "value": "redis://horilla-redis.xxxxx.cache.amazonaws.com:6379/1"}
    ],
    "secrets": [
      {"name": "SECRET_KEY",          "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:horilla/production:SECRET_KEY::"},
      {"name": "DATABASE_URL",        "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:horilla/production:DATABASE_URL::"},
      {"name": "ADMIN_PASSWORD",      "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:horilla/production:ADMIN_PASSWORD::"},
      {"name": "AWS_ACCESS_KEY_ID",   "valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:horilla/production:AWS_ACCESS_KEY_ID::"},
      {"name": "AWS_SECRET_ACCESS_KEY","valueFrom": "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:horilla/production:AWS_SECRET_ACCESS_KEY::"}
    ],
    "healthCheck": {
      "command": ["CMD-SHELL", "curl -f http://localhost:8000/health/ || exit 1"],
      "interval": 30,
      "timeout": 10,
      "retries": 3,
      "startPeriod": 60
    },
    "logConfiguration": {
      "logDriver": "awslogs",
      "options": {
        "awslogs-group":         "/ecs/horilla/web",
        "awslogs-region":        "us-east-1",
        "awslogs-stream-prefix": "web"
      }
    }
  }]
}
```

```bash
# Register it
aws ecs register-task-definition --cli-input-json file://task-web.json
```

### 8b. Worker Task Definition
Save as `task-worker.json` — same as above but:
- `"family": "horilla-worker"`
- `"command": ["/app/entrypoint.worker.sh"]`
- No `portMappings`
- Log group `/ecs/horilla/worker`

### 8c. Beat Task Definition
Save as `task-beat.json` — same as worker but:
- `"family": "horilla-beat"`
- `"command": ["/app/entrypoint.beat.sh"]`
- Log group `/ecs/horilla/beat`

```bash
aws ecs register-task-definition --cli-input-json file://task-worker.json
aws ecs register-task-definition --cli-input-json file://task-beat.json
```

---

## 9. ECS Services

```bash
# ── Web Service (2 tasks, behind ALB) ─────────────────────────────────────────
aws ecs create-service \
    --cluster horilla-production \
    --service-name horilla-web \
    --task-definition horilla-web \
    --desired-count 2 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={
        subnets=[subnet-xxx,subnet-yyy],
        securityGroups=[sg-xxx],
        assignPublicIp=DISABLED}" \
    --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:...,
                      containerName=web,containerPort=8000" \
    --health-check-grace-period-seconds 90 \
    --deployment-configuration \
        "minimumHealthyPercent=50,maximumPercent=200"

# ── Worker Service (2 tasks) ──────────────────────────────────────────────────
aws ecs create-service \
    --cluster horilla-production \
    --service-name horilla-worker \
    --task-definition horilla-worker \
    --desired-count 2 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={
        subnets=[subnet-xxx,subnet-yyy],
        securityGroups=[sg-xxx],
        assignPublicIp=DISABLED}"

# ── Beat Service (ALWAYS exactly 1 task) ─────────────────────────────────────
aws ecs create-service \
    --cluster horilla-production \
    --service-name horilla-beat \
    --task-definition horilla-beat \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={
        subnets=[subnet-xxx,subnet-yyy],
        securityGroups=[sg-xxx],
        assignPublicIp=DISABLED}"
```

---

## 10. Application Load Balancer

```bash
# Create ALB
aws elbv2 create-load-balancer \
    --name horilla-alb \
    --subnets subnet-public-1 subnet-public-2 \
    --security-groups sg-alb-xxx \
    --scheme internet-facing \
    --type application

# Create Target Group
aws elbv2 create-target-group \
    --name horilla-web-tg \
    --protocol HTTP \
    --port 8000 \
    --vpc-id vpc-xxxxxxxxxxxxxxxxx \
    --target-type ip \
    --health-check-path /health/ \
    --health-check-interval-seconds 30 \
    --healthy-threshold-count 2 \
    --unhealthy-threshold-count 3

# Create HTTPS listener (requires ACM certificate)
aws elbv2 create-listener \
    --load-balancer-arn arn:aws:elasticloadbalancing:... \
    --protocol HTTPS \
    --port 443 \
    --ssl-policy ELBSecurityPolicy-TLS13-1-2-2021-06 \
    --certificates CertificateArn=arn:aws:acm:... \
    --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:...

# HTTP → HTTPS redirect
aws elbv2 create-listener \
    --load-balancer-arn arn:aws:elasticloadbalancing:... \
    --protocol HTTP \
    --port 80 \
    --default-actions \
        "Type=redirect,RedirectConfig={Protocol=HTTPS,Port=443,StatusCode=HTTP_301}"
```

---

## 11. Auto Scaling (Web Service)

```bash
# Register scalable target
aws application-autoscaling register-scalable-target \
    --service-namespace ecs \
    --resource-id service/horilla-production/horilla-web \
    --scalable-dimension ecs:service:DesiredCount \
    --min-capacity 2 \
    --max-capacity 10

# Scale out when CPU > 70%
aws application-autoscaling put-scaling-policy \
    --service-namespace ecs \
    --resource-id service/horilla-production/horilla-web \
    --scalable-dimension ecs:service:DesiredCount \
    --policy-name horilla-cpu-scaling \
    --policy-type TargetTrackingScaling \
    --target-tracking-scaling-policy-configuration '{
        "TargetValue": 70.0,
        "PredefinedMetricSpecification": {
            "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
        },
        "ScaleOutCooldown": 60,
        "ScaleInCooldown": 300
    }'
```

---

## 12. Deploy a New Image (CI/CD)

Use this script on every push to main:

```bash
#!/bin/bash
# deploy.sh — called from GitHub Actions / CodePipeline
set -e

IMAGE_TAG=$(git rev-parse --short HEAD)
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}"

# 1. Login
aws ecr get-login-password --region ${AWS_REGION} \
    | docker login --username AWS --password-stdin ${ECR_REPO}

# 2. Build & Push
docker build --platform linux/amd64 --target runtime \
    -t ${ECR_REPO}:${IMAGE_TAG} -t ${ECR_REPO}:latest .
docker push ${ECR_REPO}:${IMAGE_TAG}
docker push ${ECR_REPO}:latest

# 3. Force new ECS deployment (pulls :latest)
aws ecs update-service \
    --cluster horilla-production \
    --service horilla-web \
    --force-new-deployment \
    --region ${AWS_REGION}

aws ecs update-service \
    --cluster horilla-production \
    --service horilla-worker \
    --force-new-deployment \
    --region ${AWS_REGION}

aws ecs update-service \
    --cluster horilla-production \
    --service horilla-beat \
    --force-new-deployment \
    --region ${AWS_REGION}

# 4. Wait for web service to stabilise
aws ecs wait services-stable \
    --cluster horilla-production \
    --services horilla-web

echo "Deployment complete: ${ECR_REPO}:${IMAGE_TAG}"
```

---

## 13. Folder Structure

```
horilla-1.0/
├── Dockerfile                  ← multi-stage, production-ready
├── .dockerignore               ← keeps image lean
├── docker-compose.yaml         ← local dev + staging
├── entrypoint.sh               ← web startup (migrate → gunicorn)
├── entrypoint.worker.sh        ← celery worker startup
├── entrypoint.beat.sh          ← celery beat startup
├── gunicorn.conf.py            ← gthread workers, timeouts
├── .env.example                ← template (never commit .env)
├── requirements.txt
│
├── aws/                        ← deployment manifests
│   ├── task-web.json           ← ECS task definition
│   ├── task-worker.json
│   ├── task-beat.json
│   └── deploy.sh               ← CI/CD deploy script
│
└── horilla/
    ├── settings.py
    ├── urls.py                 ← includes /health/ endpoint
    ├── wsgi.py
    └── celery.py
```

---

## 14. Security Groups

| Security Group | Inbound Rule | Source |
|---|---|---|
| `sg-alb` | 80, 443 | 0.0.0.0/0 |
| `sg-ecs-tasks` | 8000 | sg-alb only |
| `sg-redis` | 6379 | sg-ecs-tasks only |

```bash
# ECS tasks SG — only allow traffic from ALB
aws ec2 authorize-security-group-ingress \
    --group-id sg-ecs-tasks \
    --protocol tcp --port 8000 \
    --source-group sg-alb

# Redis SG — only allow from ECS tasks
aws ec2 authorize-security-group-ingress \
    --group-id sg-redis \
    --protocol tcp --port 6379 \
    --source-group sg-ecs-tasks
```

---

## 15. Monthly Cost Estimate (us-east-1)

| Resource | Config | Est. Cost/mo |
|---|---|---|
| ECS Fargate — web | 2 tasks × 1vCPU/2GB | ~$29 |
| ECS Fargate — worker | 2 tasks × 0.5vCPU/1GB | ~$15 |
| ECS Fargate — beat | 1 task × 0.25vCPU/0.5GB | ~$4 |
| ElastiCache Redis | cache.t4g.small | ~$25 |
| NeonDB | Free tier (0.5GB) / Pro ($19) | $0–$19 |
| S3 + Data Transfer | 10 GB storage + requests | ~$3 |
| ALB | 1 ALB + LCU | ~$18 |
| CloudWatch Logs | 5 GB/mo | ~$3 |
| **Total** | | **~$97–$116/mo** |

Cost optimization tips:
- Use `FARGATE_SPOT` for the worker service (save 70%)
- Switch beat to a scheduled Lambda instead of a 24/7 Fargate task

---

## 16. Final Deployment Checklist

```
PRE-DEPLOY
[ ] .env.example reviewed, .env never committed
[ ] SECRET_KEY is 50+ random chars
[ ] DEBUG=False
[ ] ALLOWED_HOSTS includes ALB DNS and your domain
[ ] DATABASE_URL points to NeonDB with ?sslmode=require
[ ] All secrets stored in AWS Secrets Manager
[ ] S3 bucket created, public access blocked
[ ] ACM certificate issued and validated for your domain

INFRASTRUCTURE
[ ] VPC with private subnets for ECS + Redis
[ ] Public subnets for ALB only
[ ] Security groups follow least-privilege (no 0.0.0.0/0 on ECS/Redis)
[ ] ECR repository created and image pushed
[ ] ECS cluster created with Container Insights enabled
[ ] CloudWatch log groups created with retention policy
[ ] IAM roles created with only required permissions

ECS SERVICES
[ ] Task definitions registered (web, worker, beat)
[ ] Web service running 2+ tasks
[ ] Worker service running 2 tasks
[ ] Beat service running EXACTLY 1 task
[ ] ALB health check passing (/health/ returns 200)
[ ] Auto-scaling policy set on web service

POST-DEPLOY
[ ] HTTPS working (HTTP redirects to HTTPS)
[ ] Login to /login works
[ ] Leave dashboard loads
[ ] File upload test (employee photo)
[ ] Celery task test (trigger payroll generation)
[ ] CloudWatch logs showing requests
[ ] Set up CloudWatch alarms (CPU > 80%, task count < desired)
```

---

## Quick Reference Commands

```bash
# View running tasks
aws ecs list-tasks --cluster horilla-production --service-name horilla-web

# View logs (last 100 lines)
aws logs tail /ecs/horilla/web --follow --since 1h

# Force redeploy without new image
aws ecs update-service --cluster horilla-production \
    --service horilla-web --force-new-deployment

# Scale web service manually
aws ecs update-service --cluster horilla-production \
    --service horilla-web --desired-count 4

# Check service health
aws ecs describe-services \
    --cluster horilla-production \
    --services horilla-web \
    --query 'services[0].{Running:runningCount,Desired:desiredCount,Status:status}'
```
