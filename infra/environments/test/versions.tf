terraform {
  required_version = ">= 1.9.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.32"
    }

    # Le secret de chemin unique de V2-LLD-001 §7.4 est tire une fois et conserve dans
    # l'etat, plutot que saisi dans un tfvars ou passe en variable de CI : ni l'un ni
    # l'autre ne le garderait hors d'un depot et hors des artefacts de plan.
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }
}
