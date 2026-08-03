resource "aws_ecr_repository" "this" {
  name                 = var.name
  image_tag_mutability = var.image_tag_mutability
  force_delete         = var.force_delete

  image_scanning_configuration {
    scan_on_push = var.scan_on_push
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = var.tags
}

# La regle de comptage expire les images les plus anciennes sans savoir laquelle est
# referencee par une task definition vivante ou resolue en digest au moment du plan.
# « Les N plus recentes » n'a aucun rapport avec « celles qui servent » : sur un depot
# dont les images sont epinglees par digest, elle supprime des cibles de rollback et
# peut faire echouer un plan portant sur tout autre chose. ECR ne sait pas exprimer
# « ne supprime pas ce qui est reference » ; expire_tagged_images = false retire donc
# la regle, et seules les images sans tag expirent.
locals {
  untagged_expiry_rule = {
    rulePriority = 1
    description  = "Expire untagged images after 7 days"
    selection = {
      tagStatus   = "untagged"
      countType   = "sinceImagePushed"
      countUnit   = "days"
      countNumber = 7
    }
    action = {
      type = "expire"
    }
  }

  tagged_expiry_rule = {
    rulePriority = 100
    description  = "Keep only the most recent images for the test runtime repository"
    selection = {
      tagStatus   = "any"
      countType   = "imageCountMoreThan"
      countNumber = var.keep_last_images
    }
    action = {
      type = "expire"
    }
  }

  # slice sur un tuple plutot qu'un conditionnel renvoyant deux listes : les deux
  # regles n'ont pas le meme type d'objet (countUnit n'existe que sur la premiere)
  # et Terraform echouerait a unifier les branches.
  lifecycle_rules = slice(
    [local.untagged_expiry_rule, local.tagged_expiry_rule],
    0,
    var.expire_tagged_images ? 2 : 1,
  )
}

resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name

  policy = jsonencode({
    rules = local.lifecycle_rules
  })
}
