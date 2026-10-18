terraform {
  required_version = ">= 1.10"
  required_providers { aws = { source = "hashicorp/aws", version = ">= 5.0, < 7.0" } }
  # Configure encrypted remote state and locking before init/apply. State contains secrets.
}
provider "aws" { region = "me-central-1" }
variable "name" { type = string }
variable "availability_zones" { type = list(string) }
variable "database_password" {
  type = string
  sensitive = true
}
variable "application_security_group_id" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }

resource "aws_kms_key" "financial" {
  description = "AuditOS staging financial data"
  enable_key_rotation = true
  deletion_window_in_days = 30
}
resource "aws_s3_bucket" "evidence" {
  bucket = "${var.name}-evidence"
  force_destroy = false
}
resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  block_public_acls = true
  block_public_policy = true
  ignore_public_acls = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.financial.arn
      sse_algorithm = "aws:kms"
    }
  }
}
resource "aws_security_group" "database" {
  name_prefix = "${var.name}-db-"
  description = "PostgreSQL ingress from the approved application security group only"
  vpc_id = var.vpc_id
  ingress {
    description = "Private application PostgreSQL traffic"
    from_port = 5432
    to_port = 5432
    protocol = "tcp"
    security_groups = [var.application_security_group_id]
  }
}
resource "aws_db_subnet_group" "private" {
  name = var.name
  subnet_ids = var.private_subnet_ids
}
resource "aws_db_instance" "database" {
  identifier = var.name
  engine = "postgres"
  engine_version = "16"
  instance_class = "db.t4g.medium"
  allocated_storage = 100
  storage_encrypted = true
  kms_key_id = aws_kms_key.financial.arn
  db_name = "auditos"
  username = "auditos_owner"
  password = var.database_password
  multi_az = true
  publicly_accessible = false
  db_subnet_group_name = aws_db_subnet_group.private.name
  vpc_security_group_ids = [aws_security_group.database.id]
  backup_retention_period = 14
  deletion_protection = true
  skip_final_snapshot = false
  final_snapshot_identifier = "${var.name}-final"
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  auto_minor_version_upgrade = true
  iam_database_authentication_enabled = true
}
# Provision application and migration roles separately; do not use the owner login in APIs.
# Redis, IAM task roles, private networking, WAF, compute, alerts, remote state, secret
# injection, backup vault and region/service validation remain environment-specific gates.
