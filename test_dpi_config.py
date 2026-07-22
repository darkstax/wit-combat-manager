from pathlib import Path
import xml.etree.ElementTree as ET


def test_windows_manifest_declares_per_monitor_v2():
    manifest = Path(__file__).with_name("WIT-Combat-Manager.manifest")
    root = ET.parse(manifest).getroot()
    values = [text.strip() for text in root.itertext() if text.strip()]

    assert "PerMonitorV2, PerMonitor" in values
    assert "true/pm" in values
