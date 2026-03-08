provider "aws" {
  region = var.region
}

resource "aws_vpc" "main" {
  cidr_block = var.vpc_cidr
  enable_dns_support = true
  enable_dns_hostnames = true
  tags = {
    Name = var.vpc_name
  }
}

resource "aws_subnet" "public" {
  count = length(var.public_subnets)
  vpc_id = aws_vpc.main.id
  cidr_block = var.public_subnets[count.index]
  map_public_ip_on_launch = true
  availability_zone = var.availability_zones[count.index]
  tags = {
    Name = "public-subnet-${count.index}"
  }
}

resource "aws_subnet" "private" {
  count = length(var.private_subnets)
  vpc_id = aws_vpc.main.id
  cidr_block = var.private_subnets[count.index]
  availability_zone = var.availability_zones[count.index]
  tags = {
    Name = "private-subnet-${count.index}"
  }
}

resource "aws_security_group" "flask" {
  name_prefix = "flask-sg-"
  vpc_id = aws_vpc.main.id
  ingress {
    from_port = 5000
    to_port = 5000
    protocol = "tcp"
    cidr_blocks = [var.cidr_blocks]
  }
  egress {
    from_port = 0
    to_port = 0
    protocol = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "flask-sg"
  }
}

resource "aws_security_group" "django" {
  name_prefix = "django-sg-"
  vpc_id = aws_vpc.main.id
  ingress {
    from_port = 8000
    to_port = 8000
    protocol = "tcp"
    cidr_blocks = [var.cidr_blocks]
  }
  egress {
    from_port = 0
    to_port = 0
    protocol = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "django-sg"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags = {
    Name = "main-igw"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = {
    Name = "public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)
  subnet_id = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_eks_cluster" "main" {
  name = var.cluster_name
  role_arn = var.cluster_role_arn
  vpc_config {
    subnet_ids = concat(aws_subnet.public.*.id, aws_subnet.private.*.id)
  }
}

resource "aws_iam_role" "eks" {
  name = "eks-cluster-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = {
        Service = "eks.amazonaws.com"
      },
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "amazon_eks_cluster_policy" {
  role = aws_iam_role.eks.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_iam_role_policy_attachment" "amazon_eks_service_policy" {
  role = aws_iam_role.eks.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSServicePolicy"
}
