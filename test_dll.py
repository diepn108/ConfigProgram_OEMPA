import ctypes
import os
import platform
import sys

# Paths
dll_dir = os.environ.get("OEMPA_AOS_RUNTIME", os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "AOS", "OEMPA 1.1.5.4"))

# Environment
print("AOS OEM-PA DLL Test")
print(f"Python version: {sys.version.split()[0]}")
print(f"Python architecture: {platform.architecture()[0]}")
print(f"DLL directory: {dll_dir}")
print()

if not os.path.isdir(dll_dir):
    raise FileNotFoundError(f"DLL directory not found: {dll_dir}")

# Make dependent DLLs discoverable
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(dll_dir)

# DLLs
dll_names = [
    "UTCom.dll",
    "UTKernelDriver.dll",
    "UTKernelDriverOEMPA.dll",
    "UTKernelAPI.dll",
    "UTCustomizedDriverAPI.dll",
    "UTCustomizedWizardAPI.dll",
]

loaded_dlls = {}

# Load DLL stack
for dll_name in dll_names:
    dll_path = os.path.join(dll_dir, dll_name)

    if not os.path.isfile(dll_path):
        print(f"[MISSING] {dll_name}")
        continue

    try:
        loaded_dlls[dll_name] = ctypes.WinDLL(dll_path)
        print(f"[OK] {dll_name}")

    except OSError as exc:
        print(f"[FAILED] {dll_name}")
        print(f"         {exc}")

print()

# Result
if "UTKernelDriverOEMPA.dll" in loaded_dlls:
    print("OEM-PA driver DLL loaded successfully.")
else:
    print("OEM-PA driver DLL did NOT load.")