import csv
import re
from datetime import datetime
from netmiko import ConnectHandler
import os
from config import username, password, server_ip

current_path = os.path.dirname(os.path.abspath(__file__))
input_csv_path = os.path.join(current_path, "hosts.csv")
output_csv_path = os.path.join(current_path, "results.csv")

device_type = "cisco_ios"

memory_req = 500
protocol = "tftp"
target_image = "cat3k_caa-universalk9.SPA.03.06.10.E.152-2.E10.bin"
destination = "flash:"
copy_command = f"copy {protocol}://{server_ip}/{target_image} {destination}"

class NetworkDevice:
    def __init__(self, device_type, username, password):
        self.device_type = device_type
        self.username = username
        self.password = password
        self.net_connect = None


    def connect(self, device_ip):
        if self.net_connect:
            self.net_connect.disconnect()
        device = {
            "device_type": self.device_type,
            "ip": device_ip,
            "username": self.username,
            "password": self.password,
        }
        self.net_connect = ConnectHandler(**device)

    def disconnect(self):
        if self.net_connect:
            self.net_connect.disconnect()

    def send_command(self, command):
        if self.net_connect:
            return self.net_connect.send_command(command)
        else:
            raise ValueError("Network connection not established")

    def send_command_timing(self, command):
        if self.net_connect:
            return self.net_connect.send_command_timing(command)
        else:
            raise ValueError("Network connection not established")
def check_memory_size(net_device):
    try:
        show_flash_output = net_device.send_command("show flash")
        match = re.search(r"(\d+) bytes available", show_flash_output)
        if match:
            available_bytes = int(match.group(1))
            available_MB = available_bytes / (1024 ** 2)
            if available_MB < memory_req:
                print(f"Insufficient memory space - Available memory: {available_MB}")
                return "Insufficient memory space"
            else:
                print(f"Ready to Install - Available memory: {available_MB}")
                return "Ready to Install"
        else:
            print(f"Memory stats not found - Check your syntax")
            return "Memory stats not found - Check your syntax"
    except Exception as e:
        return f"ERROR - {e}"

def get_boot_variable(net_device):
    try:
        show_boot_output = net_device.send_command("show boot")
        match = re.search(r"BOOT variable = (.+)", show_boot_output)
        if match:
            return match.group(1)
        else:
            return "N/A"
    except Exception as e:
        return f"ERROR - {e}"

def delete_binary_if_needed(net_device):
    try:
        show_flash_output = net_device.send_command("dir flash:")
        bin_files = re.findall(r"(\S+\.bin)", show_flash_output)
        if bin_files:
            def get_datetime(file_name):
                match = re.search(r"(\w{3} \d{1,2} \d{4} \d{2}:\d{2}:\d{2})", file_name)
                if match:
                    date_time_str = match.group()
                    return datetime.strptime(date_time_str, "%b %d %Y %H:%M:%S")
                return datetime.min
            bin_files.sort(key=get_datetime)
            oldest_bin = bin_files[0]
            match = re.search(r"BOOT variable = flash:(\S+\.bin)", get_boot_variable(net_device))
            system_binary = match.group(1) if match else ""
            if oldest_bin != system_binary:
                net_device.send_command_timing(f'delete /force flash:{oldest_bin}')
                print(f"Deleted the oldest file '{oldest_bin}' to free up space.")
            else:
                print(f"Oldest file '{oldest_bin}' matches the system binary. Not deleted.")
        else:
            print("No *.bin files found in the flash directory")
    except Exception as e:
        print(f"ERROR - {e}")

def copy_firmware_to_device(net_device, copy_command):
    memory_status = check_memory_size(net_device)
    try:
        if memory_status == "Ready to Install":
            net_device.send_command(copy_command)
            print("SUCCESSFUL")
            return "SUCCESSFUL"
        else:
            print("FAILED - Insufficient memory space")
            return "FAILED - Insufficient memory space"
    except Exception as e:
        print("ERROR")
        return f"ERROR - {e}"
    
def main():
    updated_rows = []

    with open(input_csv_path, "r") as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = reader.fieldnames + ["BOOT variable", "Available Memory", "Status"]

        try:
            for row in reader:
                device_ip = row["IP"]
                print(device_ip)
                net_device.connect(device_ip)
                boot_variable = get_boot_variable(net_device)
                row["BOOT variable"] = boot_variable
                row["Available Memory"] = check_memory_size(net_device)
                delete_binary_if_needed(net_device)
                copy_status = copy_firmware_to_device(net_device, copy_command)
                row["Status"] = copy_status
                updated_rows.append(row)
                net_device = NetworkDevice(device_type, username, password)
                net_device.disconnect()
        except Exception as e:
            print(f"Error: {e}")

    with open(output_csv_path, "w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_rows)

if __name__ == "__main__":
    main()