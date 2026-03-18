SHELL := /bin/bash
AWS_REGION ?= eu-central-1
TF_COMPOSE = docker compose -f docker-compose.terraform.yml run --rm terraform

session:
	aws-vault exec artur.demo --duration=2h

list_profiles:
	aws-vault list

bootstrap-init:
	$(TF_COMPOSE) -chdir=/work/bootstrap init

bootstrap-plan:
	$(TF_COMPOSE) -chdir=/work/bootstrap plan

bootstrap-apply:
	$(TF_COMPOSE) -chdir=/work/bootstrap apply

bootstrap-destroy:
	$(TF_COMPOSE) -chdir=/work/bootstrap destroy

prod-init:
	$(TF_COMPOSE) -chdir=/work/prod init

prod-fmt:
	$(TF_COMPOSE) -chdir=/work/prod fmt -recursive

prod-db-init:
	@CLUSTER=$$($(TF_COMPOSE) -chdir=/work/prod output -raw ecs_cluster_name); \
	TASKDEF=$$($(TF_COMPOSE) -chdir=/work/prod output -raw db_init_task_definition_arn || true); \
	[[ -n "$$TASKDEF" && "$$TASKDEF" != "null" ]] || { echo "db_init_task_definition_arn is null. Did you run prod-stage1-apply?"; exit 2; }; \
	SUBNETS=$$($(TF_COMPOSE) -chdir=/work/prod output -json private_app_subnet_ids | python3 -c 'import json,sys; print(",".join(json.load(sys.stdin)))'); \
	SG=$$($(TF_COMPOSE) -chdir=/work/prod output -raw sg_services_id); \
	echo "Cluster=$$CLUSTER"; \
	echo "TaskDef=$$TASKDEF"; \
	echo "Subnets=$$SUBNETS"; \
	echo "SG=$$SG"; \
	TASK_ARN=$$(aws ecs run-task --region $(AWS_REGION) --cluster $$CLUSTER --launch-type FARGATE \
	  --task-definition $$TASKDEF \
	  --network-configuration "awsvpcConfiguration={subnets=[$$SUBNETS],securityGroups=[$$SG],assignPublicIp=DISABLED}" \
	  --query 'tasks[0].taskArn' --output text); \
	echo "db-init task ARN: $$TASK_ARN"; \
	aws ecs wait tasks-stopped --region $(AWS_REGION) --cluster $$CLUSTER --tasks $$TASK_ARN; \
	EXIT_CODE=$$(aws ecs describe-tasks --region $(AWS_REGION) --cluster $$CLUSTER --tasks $$TASK_ARN --query 'tasks[0].containers[0].exitCode' --output text); \
	STOPPED_REASON=$$(aws ecs describe-tasks --region $(AWS_REGION) --cluster $$CLUSTER --tasks $$TASK_ARN --query 'tasks[0].stoppedReason' --output text); \
	echo "ExitCode=$$EXIT_CODE"; \
	echo "StoppedReason=$$STOPPED_REASON"; \
	test "$$EXIT_CODE" = "0"; \
	echo "db-init finished successfully."


prod-stage1-plan:
	$(TF_COMPOSE) -chdir=/work/prod plan -var-file=stage1.tfvars

prod-stage1-apply:
	$(TF_COMPOSE) -chdir=/work/prod apply -auto-approve -var-file=stage1.tfvars

prod-stage2-plan:
	$(TF_COMPOSE) -chdir=/work/prod plan -var-file=stage2.tfvars

prod-stage2-apply:
	$(TF_COMPOSE) -chdir=/work/prod apply -auto-approve -var-file=stage2.tfvars

prod-bootstrap-db-safe: prod-init prod-stage1-plan prod-stage1-apply prod-db-init prod-stage2-plan prod-stage2-apply

prod-pause:
	$(TF_COMPOSE) -chdir=/work/prod apply -auto-approve -var-file=pause.tfvars

prod-resume:
	$(TF_COMPOSE) -chdir=/work/prod apply -auto-approve -var-file=resume.tfvars

prod-destroy:
	$(TF_COMPOSE) -chdir=/work/prod destroy -auto-approve -var-file=pause.tfvars

redeploy-session-auth:
	CLUSTER=$$(docker compose -f docker-compose.terraform.yml run --rm terraform -chdir=/work/prod output -raw ecs_cluster_name); \
	aws ecs update-service \
		--region eu-central-1 \
		--cluster "$$CLUSTER" \
		--service fm-session-auth \
		--force-new-deployment

redeploy-session-worker:
	CLUSTER=$$(docker compose -f docker-compose.terraform.yml run --rm terraform -chdir=/work/prod output -raw ecs_cluster_name); \
	aws ecs update-service \
		--region eu-central-1 \
		--cluster "$$CLUSTER" \
		--service fm-session-worker \
		--force-new-deployment

redeploy-session-beat:
	CLUSTER=$$(docker compose -f docker-compose.terraform.yml run --rm terraform -chdir=/work/prod output -raw ecs_cluster_name); \
	aws ecs update-service \
		--region eu-central-1 \
		--cluster "$$CLUSTER" \
		--service fm-session-beat \
		--force-new-deployment

redeploy-nice-ui:
	CLUSTER=$$(docker compose -f docker-compose.terraform.yml run --rm terraform -chdir=/work/prod output -raw ecs_cluster_name); \
	aws ecs update-service \
		--region eu-central-1 \
		--cluster "$$CLUSTER" \
		--service fm-nice-ui \
		--force-new-deployment

redeploy-wallet:
	CLUSTER=$$(docker compose -f docker-compose.terraform.yml run --rm terraform -chdir=/work/prod output -raw ecs_cluster_name); \
	aws ecs update-service \
		--region eu-central-1 \
		--cluster "$$CLUSTER" \
		--service fm-wallet \
		--force-new-deployment

redeploy-stock:
	CLUSTER=$$(docker compose -f docker-compose.terraform.yml run --rm terraform -chdir=/work/prod output -raw ecs_cluster_name); \
	aws ecs update-service \
		--region eu-central-1 \
		--cluster "$$CLUSTER" \
		--service fm-stock \
		--force-new-deployment