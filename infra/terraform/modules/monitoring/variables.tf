variable "resource_group_name" { type = string }
variable "resource_group_id" { type = string }
variable "location" { type = string }
variable "eventhub_namespace_id" { type = string }
variable "storage_account_id" { type = string }
variable "alert_email" { type = string }
variable "budget_amount" { type = number }
variable "budget_start_date" { type = string }
variable "teams_webhook_url" {
  type      = string
  default   = ""
  sensitive = true
}
