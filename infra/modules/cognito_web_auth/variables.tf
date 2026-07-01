variable "name" {
  type = string
}

variable "app_client_name" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
