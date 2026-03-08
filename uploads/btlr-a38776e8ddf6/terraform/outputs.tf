output "vpc_id" {
  description = "The ID of the VPC"
  value = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "The IDs of the public subnets"
  value = aws_subnet.public.*.id
}

output "private_subnet_ids" {
  description = "The IDs of the private subnets"
  value = aws_subnet.private.*.id
}

output "flask_security_group_id" {
  description = "The ID of the security group for the Flask application"
  value = aws_security_group.flask.id
}

output "django_security_group_id" {
  description = "The ID of the security group for the Django application"
  value = aws_security_group.django.id
}

output "eks_cluster_id" {
  description = "The ID of the EKS cluster"
  value = aws_eks_cluster.main.id
}
