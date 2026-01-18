# AWS CostLens

**AWS Cost Intelligence Tool** - Terminal-based dashboard for AWS cost monitoring and resource scanning.

```
╔═══════════════════════════════════════════════╗
║     AWS CostLens - Cost Intelligence Tool     ║
╚═══════════════════════════════════════════════╝
```

## Features

- 💵 **Cost Dashboard** - View current and previous period costs by service
- 📈 **Cost History** - 6-month cost trend visualization with ASCII charts
- 🔍 **Resource Scan** - Find stopped instances, unused volumes, unattached EIPs, untagged resources
- 📄 **Export Reports** - PDF, CSV, JSON formats
- ☁️ **S3 Upload** - Automatically upload reports to S3
- 🔧 **Multi-Profile** - Support for multiple AWS CLI profiles
- 📋 **YAML Config** - Configuration file support

## Installation

### From PyPI (Recommended)

Install from PyPI using `pip`:

```bash
pip install devops-aws-costlens
```

Or using `pipx` for isolated installation:

```bash
pipx install devops-aws-costlens
```

After installation, the command is:

```bash
aws-costlens --help
```

### From Source

If you want to install from source or contribute:

```bash
# Clone the repository
git clone https://github.com/Calza36/aws-costlens.git
cd aws-costlens

# Install in development mode
pip install -e .
```

### Using Docker

```bash
# Build the image
docker build -t aws-costlens .

# Run with AWS credentials mounted
docker run -v ~/.aws:/root/.aws:ro aws-costlens cost --profiles default
```

## Quick Start

```bash
# Cost dashboard for default profile
aws-costlens cost

# Cost dashboard for specific profiles
aws-costlens cost --profiles dev prod

# All profiles merged
aws-costlens cost --all-profiles --merge

# 6-month cost history
aws-costlens history --profiles prod

# Resource scan
aws-costlens scan --profiles prod

# Generate PDF report
aws-costlens export --profiles prod --format pdf
```

## Commands

### `cost` - Cost Dashboard

Display cost information for AWS accounts.

```bash
aws-costlens cost [options]

Options:
  --profiles, -p      AWS CLI profile names
  --regions, -r       AWS regions to check
  --all-profiles, -a  Process all available profiles
  --merge             Merge results from multiple profiles of the same account
  --time-range, -t    Time range (days or YYYY-MM-DD:YYYY-MM-DD)
  --tag               Filter by tag (key=value)
  --config, -c        Path to YAML config file
```

### `history` - Cost History

Display 6-month cost history with ASCII visualization.

```bash
aws-costlens history [options]

Options:
  --profiles, -p      AWS CLI profile names
  --all-profiles, -a  Process all available profiles
  --config, -c        Path to YAML config file
```

### `scan` - Resource Scan

Find unused and untagged resources.

```bash
aws-costlens scan [options]

Options:
  --profiles, -p      AWS CLI profile names
  --regions, -r       AWS regions to check
  --all-profiles, -a  Process all available profiles
  --config, -c        Path to YAML config file
```

Scan checks:
- ⏹️ Stopped EC2 instances
- 💾 Unused EBS volumes
- 🌐 Unattached Elastic IPs
- 🏷️ Untagged resources (EC2, RDS, Lambda, ELBv2)

### `export` - Generate Reports

Generate and export reports in various formats.

```bash
aws-costlens export [options]

Options:
  --profiles, -p      AWS CLI profile names
  --all-profiles, -a  Process all available profiles
  --merge             Merge results from multiple profiles
  --name, -n          Base name for report files
  --format, -f        Export formats: pdf, csv, json
  --dir, -d           Output directory
  --bucket            S3 bucket for uploads
  --s3-path           S3 path/prefix for reports
  --scan              Include resource scan report
  --history           Include cost history report
  --config, -c        Path to YAML config file
```

## Configuration File

Create a YAML config file for reusable settings. See `config.example.yaml` for a complete example.

```yaml
# costlens.yaml
profiles:
  - dev
  - staging
  - prod

regions:
  - us-east-1
  - eu-west-1

name: monthly_cost_report
format:
  - pdf
  - csv

bucket: my-reports-bucket
s3_path: costlens/monthly
```

Use with:

```bash
aws-costlens cost --config costlens.yaml
aws-costlens export --config costlens.yaml
```

## Docker Compose

```bash
# Run cost dashboard
docker compose run costlens cost --profiles prod

# Run scan
docker compose run costlens scan --all-profiles

# Generate reports
docker compose run costlens export --all-profiles --format pdf csv
```

## AWS Permissions Required

The following AWS permissions are required:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
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
    }
  ]
}
```

## Examples

### Monthly Cost Report for All Profiles

```bash
aws-costlens export --all-profiles --merge --format pdf csv json \
  --name monthly_$(date +%Y%m) \
  --dir ./reports
```

### Scan with S3 Upload

```bash
aws-costlens export --profiles prod --scan \
  --format pdf \
  --bucket my-audit-bucket \
  --s3-path scans/$(date +%Y/%m)
```

### Filter Costs by Tag

```bash
aws-costlens cost --profiles prod --tag Environment=production --tag Project=web
```

### Custom Time Range

```bash
# Last 7 days
aws-costlens cost --profiles prod --time-range 7

# Specific date range
aws-costlens cost --profiles prod --time-range 2025-01-01:2025-01-31
```

## License

MIT License - See [LICENSE](LICENSE) file.

---

**Author:** Ernesto Calzadilla Martínez

---

*Inspired by aws-finops-dashboard*
