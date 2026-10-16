from pathlib import Path


# Paths

PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_DIR / "configs"
OUTPUT_PATH = CONFIG_DIR / "fmc16_tx0_tx1.txt"


# Configuration

TX_COUNT = 2
RX_COUNT = 16

RANGE_US = 30.0
TIME_SLOT_US = 2000.0
PULSE_WIDTH_US = 0.5

DIGITAL_GAIN_DB = 0.0
ANALOG_GAIN_DB = 20.0
FILTER_INDEX = 1


def acquisition_cycle(cycle, tx):
    starts = ";".join(["0.000000"] * RX_COUNT)
    decimation = ";".join(["0"] * RX_COUNT)

    return f"""[Cycle:{cycle}]
GainDigital={DIGITAL_GAIN_DB:.6f} dB
Range={RANGE_US:.6f} us
HWAcquisitionTime={TIME_SLOT_US:.6f} us
PointCount=0
Rectification=Signed
FilterIndex={FILTER_INDEX}
GainAnalog={ANALOG_GAIN_DB:.6f} dB
GateCount=0
BeamCorrection=0.000000 dB
HWAcquisition=1

[Cycle:{cycle}\\Pulser]
Element.count=1
Element={tx}
Width.count=1
Width={PULSE_WIDTH_US:.6f} us

[Cycle:{cycle}\\Receiver]
Element.count=1
Element=0
StartFirst=0
Start.count={RX_COUNT}
Start={starts} us
Decimation={decimation}

"""


def replay_cycle(cycle, rx):
    return f"""[Cycle:{cycle}]
GainDigital={DIGITAL_GAIN_DB:.6f} dB
Range={RANGE_US:.6f} us
HWReplayTime={TIME_SLOT_US:.6f} us
PointCount=0
Rectification=Signed
FilterIndex={FILTER_INDEX}
GateCount=0
BeamCorrection=0.000000 dB
HWAcquisition=0

[Cycle:{cycle}\\Receiver]
Element.count=1
Element={rx}

"""


def main():
    CONFIG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    total_cycles = TX_COUNT * RX_COUNT

    text = (
        "[Root]\n"
        "VersionDriverOEMPA=1.1.5.4\n"
        f"CycleCount={total_cycles}\n"
        "EnableMultiChannel=1\n\n"
    )

    for tx in range(TX_COUNT):
        base_cycle = tx * RX_COUNT

        text += acquisition_cycle(
            base_cycle,
            tx,
        )

        for rx in range(1, RX_COUNT):
            cycle = base_cycle + rx

            text += replay_cycle(
                cycle,
                rx,
            )

    OUTPUT_PATH.write_text(
        text,
        encoding="utf-8",
    )

    print("AOS OEM-PA 2-TX Configuration Generator")
    print("---------------------------------------")
    print(f"TX elements:   0-{TX_COUNT - 1}")
    print(f"RX elements:   0-{RX_COUNT - 1}")
    print(f"Total cycles:  {total_cycles}")
    print()
    print(f"[OK] Created: {OUTPUT_PATH}")
    print()
    print("Cycle mapping:")
    print("  Cycles  0-15: TX0 -> RX0-15")
    print("  Cycles 16-31: TX1 -> RX0-15")


if __name__ == "__main__":
    main()