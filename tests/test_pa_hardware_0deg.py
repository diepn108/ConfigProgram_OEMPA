from pathlib import Path
from oempa.api import create_handle, destroy_handle, connect, disconnect, disable_acquisition, get_cycle_count, get_multichannel_state, load_configuration, get_cycle_snapshot

PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_DIR / "configs" / "pa_test_0deg.txt"
IP_ADDRESS = "192.168.1.11"
PORT = 5001

def write_config():
    z = ";".join(["0.000000 us"] * 16)
    w = ";".join(["0.500000 us"] * 16)
    g = ";".join(["0.000000 dB"] * 16)
    e = ";".join(str(i) for i in range(16))
    text = f"""[Root]
VersionDriverOEMPA=1.1.5.4
CycleCount=1

[Cycle:0]
GainDigital=0.000000 dB
BeamCorrection=0.000000 dB
Start=0.000000 us
Range=30.000000 us
TimeSlot=2000.000000 us
PointCount=0
CompressionType=Compression
Rectification=Signed
FilterIndex=1
GainAnalog=20.000000 dB
GateCount=0

[Cycle:0\\Pulser]
WedgeDelay=0.000000 us
CenterDelay=0.000000 us
Element.count=16
Element={e}
Delay.count=16;1
Delay={z}
Width.count=16
Width={w}

[Cycle:0\\Receiver]
WedgeDelay=0.000000 us
CenterDelay=0.000000 us
Element.count=16
Element={e}
Focusing=Standard
Delay.count=16;1
Delay={z}
Gain.count=16
Gain={g}
FocalTimeOfFlight.count=1
FocalTimeOfFlight=0.000000 us
"""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(text, encoding="utf-8")

def main():
    print("OEM-PA 0-Degree PA Hardware Readback Test")
    print("-----------------------------------------")
    print(f"Device: {IP_ADDRESS}:{PORT}")
    print(f"Configuration: {CONFIG_PATH}")
    print("[SAFE] Acquisition will remain OFF.")

    write_config()
    print("[OK] Generated 0-degree PA configuration")

    handle = None
    connected = False
    try:
        handle = create_handle()
        connect(handle, IP_ADDRESS, PORT)
        connected = True
        print("[OK] Connected")

        disable_acquisition(handle)
        print("[OK] Acquisition forced OFF")

        load_configuration(handle, CONFIG_PATH)
        print("[OK] Configuration loaded")

        disable_acquisition(handle)
        print("[OK] Acquisition confirmed OFF")

        cycle_count = get_cycle_count(handle)
        multi = get_multichannel_state(handle)
        s = get_cycle_snapshot(handle, 0)

        tx = [i for i, v in enumerate(s["tx_enabled"]) if v]
        rx = [i for i, v in enumerate(s["rx_enabled"]) if v]

        print("\nHardware readback")
        print("-----------------")
        print(f"Cycle count: {cycle_count}")
        print(f"Multi-Channel enabled: {multi['enabled']}")
        print(f"TX elements: {tx}")
        print(f"RX elements: {rx}")
        print(f"Analog gain: {s['gain_analog_db']:.3f} dB")
        print(f"Digital gain: {s['gain_digital_db']:.3f} dB")
        print(f"Start: {s['start_s'] * 1e6:.3f} us")
        print(f"Range: {s['range_s'] * 1e6:.3f} us")
        print(f"Sampling rate: {s['sampling_hz'] / 1e6:.3f} MHz")
        print(f"Time slot: {s['time_slot_s'] * 1e6:.3f} us")
        print(f"Point count: {s['point_count']}")
        print(f"Filter index: {s['filter_index']}")

        expected = list(range(16))
        if cycle_count != 1:
            raise RuntimeError(f"Expected CycleCount=1, got {cycle_count}.")
        if multi["enabled"]:
            raise RuntimeError("Multi-Channel must be OFF for PA mode.")
        if tx != expected:
            raise RuntimeError(f"TX aperture mismatch: {tx}")
        if rx != expected:
            raise RuntimeError(f"RX aperture mismatch: {rx}")
        if abs(s["gain_analog_db"] - 20.0) > 0.01:
            raise RuntimeError("Analog gain mismatch.")
        if abs(s["gain_digital_db"]) > 0.01:
            raise RuntimeError("Digital gain mismatch.")
        if abs(s["start_s"]) > 1e-9:
            raise RuntimeError("Start mismatch.")
        if abs(s["range_s"] - 30e-6) > 0.1e-6:
            raise RuntimeError("Range mismatch.")

        print("\n[OK] CycleCount = 1")
        print("[OK] Multi-Channel disabled")
        print("[OK] TX aperture = elements 0..15")
        print("[OK] RX aperture = elements 0..15")
        print("[OK] Acquisition parameters verified")
        print("[OK] 0-degree PA hardware readback PASSED")
    finally:
        if handle is not None:
            if connected:
                try:
                    disable_acquisition(handle)
                except Exception:
                    pass
                try:
                    disconnect(handle)
                    print("[OK] Disconnected")
                except Exception:
                    pass
            destroy_handle(handle)
        print("[SAFE] No A-scan acquisition was started.")

if __name__ == "__main__":
    main()
