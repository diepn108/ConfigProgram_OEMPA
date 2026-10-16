import os
import struct

# AOS installation
dll_dir = os.environ.get("OEMPA_AOS_RUNTIME", os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "AOS", "OEMPA 1.1.5.4"))

dll_names = [
    "UTCom.dll",
    "UTKernelDriver.dll",
    "UTKernelDriverOEMPA.dll",
    "UTKernelAPI.dll",
    "UTCustomizedDriverAPI.dll",
    "UTCustomizedWizardAPI.dll",
]


def read_exports(path):
    with open(path, "rb") as file:
        data = file.read()

    # DOS header
    if data[:2] != b"MZ":
        raise ValueError("Not a valid PE file")

    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]

    # PE signature
    if data[pe_offset:pe_offset + 4] != b"PE\x00\x00":
        raise ValueError("Invalid PE signature")

    coff_offset = pe_offset + 4
    number_of_sections = struct.unpack_from("<H", data, coff_offset + 2)[0]
    optional_header_size = struct.unpack_from("<H", data, coff_offset + 16)[0]

    optional_offset = coff_offset + 20
    magic = struct.unpack_from("<H", data, optional_offset)[0]

    # Locate export directory entry
    if magic == 0x20B:
        data_directory_offset = optional_offset + 112
    elif magic == 0x10B:
        data_directory_offset = optional_offset + 96
    else:
        raise ValueError("Unknown PE format")

    export_rva, export_size = struct.unpack_from(
        "<II",
        data,
        data_directory_offset,
    )

    if export_rva == 0:
        return []

    section_offset = optional_offset + optional_header_size
    sections = []

    # Read section table
    for index in range(number_of_sections):
        offset = section_offset + index * 40

        virtual_size = struct.unpack_from("<I", data, offset + 8)[0]
        virtual_address = struct.unpack_from("<I", data, offset + 12)[0]
        raw_size = struct.unpack_from("<I", data, offset + 16)[0]
        raw_pointer = struct.unpack_from("<I", data, offset + 20)[0]

        sections.append(
            (
                virtual_address,
                max(virtual_size, raw_size),
                raw_pointer,
            )
        )

    def rva_to_offset(rva):
        for virtual_address, size, raw_pointer in sections:
            if virtual_address <= rva < virtual_address + size:
                return raw_pointer + rva - virtual_address

        raise ValueError(f"RVA 0x{rva:X} not found")

    export_offset = rva_to_offset(export_rva)

    number_of_names = struct.unpack_from(
        "<I",
        data,
        export_offset + 24,
    )[0]

    names_rva = struct.unpack_from(
        "<I",
        data,
        export_offset + 32,
    )[0]

    names_offset = rva_to_offset(names_rva)

    exports = []

    # Read exported function names
    for index in range(number_of_names):
        name_rva = struct.unpack_from(
            "<I",
            data,
            names_offset + index * 4,
        )[0]

        name_offset = rva_to_offset(name_rva)
        end = data.find(b"\x00", name_offset)

        name = data[name_offset:end].decode(
            "ascii",
            errors="replace",
        )

        exports.append(name)

    return exports


# Inspect DLLs
for dll_name in dll_names:
    path = os.path.join(dll_dir, dll_name)

    print()
    print(f"--- {dll_name} ---")

    try:
        exports = read_exports(path)

        print(f"Exported names: {len(exports)}")

        for name in exports:
            print(name)

    except Exception as exc:
        print(f"FAILED: {exc}")