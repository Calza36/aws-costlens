<p align="center">
  <h1 align="center">AWS CostLens</h1>
  <p align="center">
    <strong>AWS Cost Intelligence CLI Tool</strong><br>
    Terminal-based dashboard for AWS cost monitoring, resource scanning, and report generation.
  </p>
</p>

<p align="center">
  <a href="https://pypi.org/project/devops-aws-costlens/"><img src="https://img.shields.io/pypi/v/devops-aws-costlens?color=blue&label=PyPI" alt="PyPI version"></a>
  <img src="https://img.shields.io/badge/python-3.8%2B-blue" alt="Python 3.8+">
  <a href="https://github.com/Calza36/aws-costlens/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License MIT"></a>
  <a href="https://pepy.tech/projects/devops-aws-costlens"><img src="https://static.pepy.tech/personalized-badge/devops-aws-costlens?period=total&units=international_system&left_color=black&right_color=green&left_text=downloads" alt="Downloads"></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/Calza36/aws-costlens/main/assets/banner.jpg" alt="AWS CostLens CLI Banner" width="550">
</p>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **💵 Cost Dashboard** | Current vs previous period costs by service, budgets, EC2 summary |
| **📈 Cost History** | 6-month trend visualization with month-over-month changes |
| **🔍 Resource Scan** | Find stopped instances, unused volumes, unattached EIPs, untagged resources |
| **📄 Export Reports** | PDF, CSV, JSON formats — structured and shareable |
| **⏱️ Flexible Time Ranges** | `last-month`, N days, or custom date ranges |
| **🏷️ Tag Filtering** | Filter costs by AWS cost allocation tags |
| **🔧 Multi-Profile** | Run across one, multiple, or all AWS CLI profiles |
| **📋 YAML Config** | Reusable configuration files |
| **☁️ S3 Upload** | Automatically upload reports to S3 |

---

## 🚀 Installation

**From PyPI (recommended):**

```bash
pip install devops-aws-costlens
```

**Or with pipx (isolated):**

```bash
pipx install devops-aws-costlens
```

**Verify installation:**

```bash
aws-costlens --version
```

---

## 📖 Quick Start

```bash
# Cost dashboard (default command)
aws-costlens --profiles <profile>

# Resource scan
aws-costlens scan --profiles <profile>

# 6-month cost history
aws-costlens history --profiles <profile>
```

---

## ⏱️ Time Range Options

CostLens supports flexible time range comparisons:

| Option | Description | Example |
|--------|-------------|---------|
| *(default)* | Current month (MTD) vs last full month | `aws-costlens --profiles mfa` |
| `last-month` | Last full month vs prior full month | `aws-costlens --profiles mfa --time-range last-month` |
| `N` (days) | Last N days vs previous N days | `aws-costlens --profiles mfa --time-range 30` |
| `YYYY-MM-DD:YYYY-MM-DD` | Custom date range vs prior same-length window | `aws-costlens --profiles mfa --time-range 2025-12-01:2026-01-01` |

**Examples:**

```bash
# Last 7 days vs previous 7 days (spike detection)
aws-costlens --profiles mfa --time-range 7

# Full December 2025 vs November 2025
aws-costlens --profiles mfa --time-range last-month

# Last 90 days vs previous 90 days
aws-costlens --profiles mfa --time-range 90
```

---

## 🏷️ Tag Filtering

Filter costs by AWS cost allocation tags:

```bash
# Single tag
aws-costlens --profiles mfa --tag Project=CDS

# Multiple tags (AND logic)
aws-costlens --profiles mfa --tag Project=CDS --tag Environment=prod
```

> **Note:** Cost allocation tags must be activated in AWS Billing for tag-based filtering to work.

---

## 📤 Export Reports

### Scan Reports (PDF, CSV, JSON)

```bash
aws-costlens scan --profiles <profile> --format csv --name scan-report
aws-costlens scan --profiles <profile> --format pdf csv json --name scan-report
```

### History Reports (JSON only)

```bash
aws-costlens history --profiles <profile> --format json --name history-report
```

### Cost Dashboard Reports (PDF, CSV, JSON)

```bash
aws-costlens export --profiles <profile> --format pdf --name cost-report
aws-costlens export --profiles <profile> --format csv json --name cost-report
```

### Complete Report Pack

```bash
# Dashboard + Scan + History in all formats
aws-costlens export --profiles <profile> --scan --history --format pdf csv json --name full-report
```

---

## 🔧 Commands Reference

### `cost` — Cost Dashboard *(default)*

```bash
aws-costlens [cost] --profiles <profile> [options]

Options:
  --profiles, -p      AWS CLI profile names
  --all-profiles, -a  Use all configured profiles
  --merge             Merge results from same account
  --time-range, -t    last-month | N days | YYYY-MM-DD:YYYY-MM-DD
  --tag               Filter by tag (key=value)
  --config, -c        YAML config file
```

### `history` — 6-Month Cost History

```bash
aws-costlens history --profiles <profile> [options]

Options:
  --profiles, -p      AWS CLI profile names
  --all-profiles, -a  Use all configured profiles
  --format, -f        json (for export)
  --name, -n          Report file name (required with --format)
  --dir, -d           Output directory
```

### `scan` — Resource Scan

```bash
aws-costlens scan --profiles <profile> [options]

Options:
  --profiles, -p      AWS CLI profile names
  --all-profiles, -a  Use all configured profiles
  --regions, -r       Specific regions (default: all accessible)
  --format, -f        pdf | csv | json (for export)
  --name, -n          Report file name (required with --format)
  --dir, -d           Output directory
```

**Scan checks:**
- ⏹️ Stopped EC2 instances
- 💾 Unattached EBS volumes
- 🌐 Unused Elastic IPs
- 🏷️ Untagged resources (EC2, RDS, Lambda, ELBv2)

### `export` — Generate Reports

```bash
aws-costlens export --profiles <profile> [options]

Options:
  --profiles, -p      AWS CLI profile names
  --all-profiles, -a  Use all configured profiles
  --merge             Merge results from same account
  --time-range, -t    last-month | N days | YYYY-MM-DD:YYYY-MM-DD
  --tag               Filter by tag (key=value)
  --format, -f        pdf | csv | json (default: pdf)
  --name, -n          Report file name (default: costlens_report)
  --dir, -d           Output directory
  --scan              Include resource scan
  --history           Include cost history
  --bucket            S3 bucket for upload
  --s3-path           S3 prefix
```

---

## 📋 Configuration File

Create `costlens.yaml` for reusable settings:

```yaml
profiles:
  - dev
  - staging
  - prod

regions:
  - us-east-1
  - eu-west-1

name: monthly_report
format:
  - pdf
  - csv

dir: ./reports
merge: false
```

**Usage:**

```bash
aws-costlens --config costlens.yaml
aws-costlens export --config costlens.yaml
```

> CLI arguments override config file settings.

---

## 🔐 AWS Permissions

CostLens uses **read-only** AWS APIs. Required permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "ce:GetCostAndUsage",
      "budgets:DescribeBudgets",
      "ec2:DescribeInstances",
      "ec2:DescribeVolumes",
      "ec2:DescribeAddresses",
      "ec2:DescribeRegions",
      "rds:DescribeDBInstances",
      "rds:ListTagsForResource",
      "lambda:ListFunctions",
      "lambda:ListTags",
      "elasticloadbalancing:DescribeLoadBalancers",
      "elasticloadbalancing:DescribeTags",
      "sts:GetCallerIdentity",
      "s3:PutObject"
    ],
    "Resource": "*"
  }]
}
```

> `s3:PutObject` is only needed if uploading reports to S3.

---

## 🐳 Docker

```bash
# Build
docker build -t aws-costlens .

# Run with AWS credentials
docker run -v ~/.aws:/root/.aws:ro aws-costlens --profiles default
```

**Docker Compose:**

```bash
docker compose run costlens --profiles prod
docker compose run costlens scan --all-profiles
docker compose run costlens export --all-profiles --format pdf csv
```

---

## 📸 Screenshots

<!-- 
Add screenshots here showing:
- Cost dashboard output
- Scan results
- History visualization
- Exported PDF/CSV examples
-->

*Screenshots coming soon...*

---

## 📦 From Source

```bash
git clone https://github.com/Calza36/aws-costlens.git
cd aws-costlens
pip install -e .
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE) file.

*Inspired by aws-finops-dashboard*

---

<p align="center">
  <strong>Author:</strong> Ernesto Calzadilla Martínez<br>
  <a href="https://github.com/Calza36/aws-costlens">GitHub</a> · 
  <a href="https://pypi.org/project/devops-aws-costlens/">PyPI</a>
</p>
