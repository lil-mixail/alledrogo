# obraz serwera aplikacji, odpalany z GitHub Actions (patrz .github/workflows/deploy.yml)
packer {
  required_plugins {
    amazon = {
      version = ">= 1.3.0"
      source  = "github.com/hashicorp/amazon"
    }
  }
}

variable "git_sha" {
  type = string
}

variable "region" {
  type    = string
  default = "eu-north-1"
}

source "amazon-ebs" "alledrogo" {
  region        = var.region
  instance_type = "t3.micro"
  ami_name      = "alledrogo-${substr(var.git_sha, 0, 7)}-{{timestamp}}"

  # zawsze najnowszy Amazon Linux 2023 od Amazona
  source_ami_filter {
    filters = {
      name                = "al2023-ami-2023.*-x86_64"
      virtualization-type = "hvm"
      root-device-type    = "ebs"
    }
    owners      = ["amazon"]
    most_recent = true
  }

  # tymczasowa maszyna w default VPC, SSH tylko z IP runnera GitHuba,
  # klucz i security group packer tworzy sam i kasuje po buildzie
  ssh_username                              = "ec2-user"
  associate_public_ip_address               = true
  temporary_security_group_source_public_ip = true

  # tylko IMDSv2, tak samo jak na produkcji
  imds_support = "v2.0"
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  tags = {
    Name    = "alledrogo"
    Project = "alledrogo"
    GitSha  = var.git_sha
  }
  run_tags = {
    Name    = "alledrogo-packer-build"
    Project = "alledrogo"
  }
}

build {
  sources = ["source.amazon-ebs.alledrogo"]

  provisioner "file" {
    source      = "app.tar.gz"
    destination = "/tmp/app.tar.gz"
  }

  # ten sam skrypt co przy recznym budowaniu AMI na L4
  provisioner "shell" {
    inline = [
      "mkdir -p /tmp/alledrogo",
      "tar -xzf /tmp/app.tar.gz -C /tmp/alledrogo",
      "rm /tmp/app.tar.gz",
      "sudo bash /tmp/alledrogo/deploy/build_ami.sh",
    ]
  }

  post-processor "manifest" {
    output     = "manifest.json"
    strip_path = true
  }
}
