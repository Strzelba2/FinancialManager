SHELL := /bin/bash

AWS_REGION ?= eu-central-1
AWS_PROFILE ?= artur.demo

LOCAL_REGISTRY ?= local
TEST_TAG ?= test

GIT_SHA := $(shell git rev-parse --short HEAD 2>/dev/null || echo "nogit")
TAG ?= $(GIT_SHA)

AWS_ACCOUNT_ID ?= $(shell aws sts get-caller-identity --query Account --output text 2>/dev/null)
ECR_REGISTRY ?= $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com

SCRIPT := ./ecr_build.sh

IMAGES := fm-wallet fm-stock fm-session-auth fm-nice-ui

.PHONY: help test-build test-clean prod-build prod-push ecr-login show

help:
	@echo "Targets:"
	@echo "  make test-build        Build locally (no push), tags: $(LOCAL_REGISTRY)/<image>:$(TEST_TAG)"
	@echo "  make test-clean        Remove local test images"
	@echo "  make prod-build        Build prod images tagged for ECR (no push), tag: $(TAG)"
	@echo "  make prod-push         Build + push to ECR, tag: $(TAG)"
	@echo "  make ecr-login         Docker login to ECR (optional helper)"
	@echo "  make show              Show computed vars (registry/tag/account)"
	@echo ""
	@echo "Examples:"
	@echo "  make test-build"
	@echo "  make prod-push TAG=$$(git rev-parse --short HEAD)"
	@echo "  AWS_REGION=eu-central-1 make prod-push"

show:
	@echo "AWS_REGION=$(AWS_REGION)"
	@echo "AWS_ACCOUNT_ID=$(AWS_ACCOUNT_ID)"
	@echo "ECR_REGISTRY=$(ECR_REGISTRY)"
	@echo "TAG=$(TAG)"
	@echo "LOCAL_REGISTRY=$(LOCAL_REGISTRY)"
	@echo "TEST_TAG=$(TEST_TAG)"

test-build:
	@ECR_REGISTRY=$(LOCAL_REGISTRY) TAG=$(TEST_TAG) $(SCRIPT)

test-clean:
	@for img in $(IMAGES); do \
	  docker rmi -f $(LOCAL_REGISTRY)/$$img:$(TEST_TAG) >/dev/null 2>&1 || true; \
	done
	@echo "Removed local test images (if existed)."

prod-build:
	@ECR_REGISTRY=$(ECR_REGISTRY) TAG=$(TAG) $(SCRIPT)

prod-push:
	@ECR_REGISTRY=$(ECR_REGISTRY) TAG=$(TAG) $(SCRIPT) --push

prod-push-ui:
	@ECR_REGISTRY=$(ECR_REGISTRY) TAG=$(TAG) $(SCRIPT) --push fm-nice-ui

prod-push-session-auth:
	@ECR_REGISTRY=$(ECR_REGISTRY) TAG=$(TAG) $(SCRIPT) --push fm-session-auth

prod-push-pgadmin:
	@ECR_REGISTRY=$(ECR_REGISTRY) TAG=$(TAG) $(SCRIPT) --push fm-pgadmin

prod-push-wallet:
	@ECR_REGISTRY=$(ECR_REGISTRY) TAG=$(TAG) $(SCRIPT) --push fm-wallet

prod-push-stock:
	@ECR_REGISTRY=$(ECR_REGISTRY) TAG=$(TAG) $(SCRIPT) --push fm-stock

ecr-login:
	@aws ecr get-login-password --region $(AWS_REGION) \
	  | docker login --username AWS --password-stdin $(ECR_REGISTRY)