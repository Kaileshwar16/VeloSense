variable "subscription_id" {
  type = string
}

variable "location" {
  description = "Select a region allowed by the student subscription with VM quota."
  type        = string
}

variable "vm_size" {
  description = "2 CPU / 8 GiB AMD64 demo candidate. Confirm region quota and credit consumption."
  type        = string
  default     = "Standard_B2ms"
  validation {
    condition     = contains(["Standard_B2ms", "Standard_D2s_v5"], var.vm_size)
    error_message = "Only the reviewed two-core AMD64 demo sizes are accepted."
  }
}

variable "ssh_public_key" {
  type = string
  validation {
    condition     = can(regex("^ssh-(ed25519|rsa) ", var.ssh_public_key))
    error_message = "Supply an OpenSSH public key, never a private key."
  }
}

variable "admin_cidr" {
  type = string
  validation {
    condition     = can(cidrnetmask(var.admin_cidr)) && endswith(var.admin_cidr, "/32")
    error_message = "Use your public IPv4 address followed by /32."
  }
}

variable "credit_and_price_checked" {
  type        = bool
  default     = false
  description = "Confirm sufficient remaining credit and an acceptable regional estimate. This is not a permanent free VM."
}

variable "shutdown_time_utc" {
  type        = string
  default     = "1800"
  description = "Daily deallocation, 18:00 UTC = 23:30 IST by default. Restart manually for demos. Disk/IP still consume credit."
  validation {
    condition     = can(regex("^([01][0-9]|2[0-3])[0-5][0-9]$", var.shutdown_time_utc))
    error_message = "Use HHmm in UTC."
  }
}
