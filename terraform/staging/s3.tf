# Documents bucket — replaces MinIO. boto3 code path unchanged.
resource "aws_s3_bucket" "docs" {
  bucket = "${local.name_prefix}-docs"
  tags   = { Name = "${local.name_prefix}-docs" }
}

resource "aws_s3_bucket_public_access_block" "docs" {
  bucket                  = aws_s3_bucket.docs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "docs" {
  bucket = aws_s3_bucket.docs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "docs" {
  bucket = aws_s3_bucket.docs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "docs" {
  bucket = aws_s3_bucket.docs.id

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# Frontend bucket — public-read static website behind Cloudflare. Cloudflare
# is the CDN/WAF/TLS terminator; this bucket serves built Vite assets only
# (public JS/CSS/HTML). User documents live in aws_s3_bucket.docs (private).
# Bucket name MUST equal the public hostname. S3 static-website endpoints
# route by Host header — when Cloudflare proxies "staging.grounded-iq.com",
# S3 looks for a bucket named exactly that. Without this match: 404 NoSuchBucket.
resource "aws_s3_bucket" "frontend" {
  bucket = var.frontend_subdomain
  tags   = { Name = var.frontend_subdomain }
}

# S3 website hosting: serves index.html for unknown keys (SPA fallback for
# React Router deep links like /chat/abc, /projects, /full-pipeline/xyz).
resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  index_document {
    suffix = "index.html"
  }
  error_document {
    key = "index.html"
  }
}

# block_public_policy=false and restrict_public_buckets=false are required so
# the bucket policy below (public s3:GetObject) is allowed to attach.
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = false
  ignore_public_acls      = true
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "PublicReadGetObject"
      Effect    = "Allow"
      Principal = "*"
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.frontend.arn}/*"
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.frontend]
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
