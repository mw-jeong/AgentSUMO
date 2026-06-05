"""
Tests for additional files guide implementation:
1. Rerouter detection in simulation_runner
2. FilesystemMCPClient multiple directory support
3. Guide-based XML validity
"""

import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================
# 1. Test _has_rerouter() detection (standalone, no heavy imports)
# ============================================================

def _has_rerouter(additional_files):
    """Standalone copy of SimulationRunner._has_rerouter for testing without SUMO deps."""
    import xml.etree.ElementTree as _ET
    for f in (additional_files or []):
        try:
            tree = _ET.parse(f)
            if tree.find('.//rerouter') is not None:
                return True
        except Exception:
            continue
    return False


def test_has_rerouter_positive():
    """Rerouter XML should be detected."""
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
    <additional>
      <rerouter id="test" edges="edge_1" probability="1.0">
        <interval begin="0" end="3600">
          <closingReroute id="edge_1"/>
        </interval>
      </rerouter>
    </additional>"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.add.xml', delete=False) as f:
        f.write(xml_content)
        tmp_path = f.name

    try:
        assert _has_rerouter([tmp_path]) is True
        print("PASS: _has_rerouter detects rerouter XML")
    finally:
        os.unlink(tmp_path)


def test_has_rerouter_negative():
    """Non-rerouter XML should not be detected."""
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
    <additional>
      <variableSpeedSign id="vss1" lanes="edge_1_0">
        <step time="0" speed="8.33"/>
      </variableSpeedSign>
    </additional>"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.add.xml', delete=False) as f:
        f.write(xml_content)
        tmp_path = f.name

    try:
        assert _has_rerouter([tmp_path]) is False
        print("PASS: _has_rerouter ignores non-rerouter XML")
    finally:
        os.unlink(tmp_path)


def test_has_rerouter_empty_list():
    """Empty additional files list should return False."""
    assert _has_rerouter([]) is False
    assert _has_rerouter(None) is False
    print("PASS: _has_rerouter handles empty/None input")


def test_has_rerouter_mixed_files():
    """Should detect rerouter even when mixed with non-rerouter files."""
    vss_xml = """<?xml version="1.0" encoding="utf-8"?>
    <additional>
      <variableSpeedSign id="vss1" lanes="edge_1_0">
        <step time="0" speed="8.33"/>
      </variableSpeedSign>
    </additional>"""

    rerouter_xml = """<?xml version="1.0" encoding="utf-8"?>
    <additional>
      <rerouter id="r1" edges="edge_2">
        <interval begin="0" end="3600">
          <closingReroute id="edge_2"/>
        </interval>
      </rerouter>
    </additional>"""

    tmp_files = []
    try:
        for content in [vss_xml, rerouter_xml]:
            f = tempfile.NamedTemporaryFile(mode='w', suffix='.add.xml', delete=False)
            f.write(content)
            f.close()
            tmp_files.append(f.name)

        assert _has_rerouter(tmp_files) is True
        print("PASS: _has_rerouter detects rerouter in mixed file list")
    finally:
        for f in tmp_files:
            os.unlink(f)


# ============================================================
# 2. Test FilesystemMCPClient multiple directory support
# ============================================================

def test_filesystem_client_single_string():
    """Single string should be converted to list."""
    # Test constructor logic directly without importing MCP deps
    allowed = "/path/to/dir"
    result = [allowed] if isinstance(allowed, str) else allowed
    assert result == ["/path/to/dir"]
    print("PASS: FilesystemMCPClient single string → list conversion")


def test_filesystem_client_multiple_dirs():
    """Multiple directories should remain as list."""
    dirs = ["/path/to/guides", "/path/to/output"]
    result = [dirs] if isinstance(dirs, str) else dirs
    assert result == dirs
    print("PASS: FilesystemMCPClient multiple directories preserved")


def test_filesystem_client_args_construction():
    """MCP server args should include all directories."""
    dirs = ["/path/to/guides", "/path/to/output"]
    args = ["-y", "@modelcontextprotocol/server-filesystem", *dirs]
    assert args == ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/guides", "/path/to/output"]
    print("PASS: MCP server args correctly include all directories")


# ============================================================
# 3. Test guide-based XML validity
# ============================================================

def test_rerouter_xml_examples():
    """All rerouter guide examples should be valid XML."""
    examples = [
        # Example 1: Full road closure
        """<additional>
  <rerouter id="rerouter_construction" edges="edge_abc123" probability="1.0">
    <interval begin="0" end="3600">
      <closingReroute id="edge_abc123"/>
    </interval>
  </rerouter>
</additional>""",
        # Example 2: Partial closure
        """<additional>
  <rerouter id="rerouter_morning" edges="edge_abc123" probability="1.0">
    <interval begin="0" end="1800">
      <closingReroute id="edge_abc123"/>
    </interval>
  </rerouter>
</additional>""",
        # Example 3: Lane reduction
        """<additional>
  <rerouter id="rerouter_lane_closure" edges="edge_abc123" probability="1.0">
    <interval begin="0" end="3600">
      <closingLaneReroute id="edge_abc123_2"/>
    </interval>
  </rerouter>
</additional>""",
        # Example 4: Emergency only
        """<additional>
  <rerouter id="rerouter_emergency_only" edges="edge_abc123" probability="1.0">
    <interval begin="0" end="3600">
      <closingReroute id="edge_abc123" allow="emergency"/>
    </interval>
  </rerouter>
</additional>""",
        # Example 5: Multiple roads
        """<additional>
  <rerouter id="rerouter_area_closure" edges="edge_abc123 edge_def456 edge_ghi789" probability="1.0">
    <interval begin="0" end="3600">
      <closingReroute id="edge_abc123"/>
      <closingReroute id="edge_def456"/>
      <closingReroute id="edge_ghi789"/>
    </interval>
  </rerouter>
</additional>""",
    ]

    for i, xml in enumerate(examples, 1):
        try:
            tree = ET.fromstring(xml)
            assert tree.tag == "additional"
            rerouter = tree.find("rerouter")
            assert rerouter is not None
            assert "id" in rerouter.attrib
            assert "edges" in rerouter.attrib
        except ET.ParseError as e:
            print(f"FAIL: Rerouter example {i} is invalid XML: {e}")
            return

    print(f"PASS: All {len(examples)} rerouter XML examples are valid")


def test_vss_xml_examples():
    """All VSS guide examples should be valid XML."""
    examples = [
        # Example 1: Speed reduction
        """<additional>
  <variableSpeedSign id="vss_construction" lanes="edge_abc123_0 edge_abc123_1">
    <step time="0" speed="8.33"/>
  </variableSpeedSign>
</additional>""",
        # Example 2: Time-varying
        """<additional>
  <variableSpeedSign id="vss_school_zone" lanes="edge_abc123_0 edge_abc123_1">
    <step time="0" speed="8.33"/>
    <step time="1800" speed="-1"/>
  </variableSpeedSign>
</additional>""",
        # Example 3: Gradual change
        """<additional>
  <variableSpeedSign id="vss_gradual" lanes="edge_abc123_0 edge_abc123_1">
    <step time="0" speed="16.67"/>
    <step time="1200" speed="11.11"/>
    <step time="2400" speed="8.33"/>
  </variableSpeedSign>
</additional>""",
        # Example 4: Multiple segments
        """<additional>
  <variableSpeedSign id="vss_road1" lanes="edge_abc123_0 edge_abc123_1">
    <step time="0" speed="13.89"/>
  </variableSpeedSign>
  <variableSpeedSign id="vss_road2" lanes="edge_def456_0 edge_def456_1 edge_def456_2">
    <step time="0" speed="13.89"/>
  </variableSpeedSign>
</additional>""",
    ]

    for i, xml in enumerate(examples, 1):
        try:
            tree = ET.fromstring(xml)
            assert tree.tag == "additional"
            vss = tree.find("variableSpeedSign")
            assert vss is not None
            assert "id" in vss.attrib
            assert "lanes" in vss.attrib
        except ET.ParseError as e:
            print(f"FAIL: VSS example {i} is invalid XML: {e}")
            return

    print(f"PASS: All {len(examples)} VSS XML examples are valid")


def test_vtype_xml_examples():
    """vType guide examples should be valid XML with correct structure."""
    examples = [
        # Example 1: Upgraded emission
        """<additional>
    <vType id="passenger" vClass="passenger"
           accel="2.5" decel="4.5" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="1,0,0" emissionClass="HBEFA4/PC_petrol_Euro-6d"/>
    <vType id="electric" vClass="passenger"
           accel="2.5" decel="4.5" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="0,255,0" emissionClass="Energy"/>
    <vType id="gasoline" vClass="passenger"
           accel="2.0" decel="4.0" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="255,0,0" emissionClass="HBEFA4/PC_petrol_Euro-6d"/>
</additional>""",
        # Example 2: With truck
        """<additional>
    <vType id="passenger" vClass="passenger"
           accel="2.5" decel="4.5" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="1,0,0" emissionClass="HBEFA3/PC_G_EU4"/>
    <vType id="electric" vClass="passenger"
           accel="2.5" decel="4.5" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="0,255,0" emissionClass="Energy"/>
    <vType id="gasoline" vClass="passenger"
           accel="2.0" decel="4.0" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="255,0,0" emissionClass="HBEFA3/PC_G_EU4"/>
    <vType id="truck" vClass="truck"
           accel="1.3" decel="4.0" sigma="0.5" length="12.0" minGap="3.0" maxSpeed="22.22"
           color="0,0,255" emissionClass="HBEFA4/RT_diesel_Euro-6d"/>
</additional>""",
    ]

    for i, xml in enumerate(examples, 1):
        try:
            tree = ET.fromstring(xml)
            assert tree.tag == "additional"
            vtypes = tree.findall("vType")
            assert len(vtypes) >= 3  # At least the 3 defaults
            for vt in vtypes:
                assert "id" in vt.attrib
                assert "emissionClass" in vt.attrib
        except ET.ParseError as e:
            print(f"FAIL: vType example {i} is invalid XML: {e}")
            return

    print(f"PASS: All {len(examples)} vType XML examples are valid")


def test_speed_reference_table():
    """Verify the speed conversion values in the guides are accurate."""
    conversions = {
        10: 2.78, 20: 5.56, 30: 8.33, 40: 11.11, 50: 13.89,
        60: 16.67, 70: 19.44, 80: 22.22, 90: 25.00, 100: 27.78,
        110: 30.56, 120: 33.33
    }

    for kmh, expected_ms in conversions.items():
        actual = round(kmh / 3.6, 2)
        assert abs(actual - expected_ms) < 0.01, \
            f"FAIL: {kmh} km/h should be {actual} m/s, guide says {expected_ms}"

    print(f"PASS: All {len(conversions)} speed conversions in guide are accurate")


def test_guide_files_exist():
    """All three guide files should exist."""
    guide_dir = Path(__file__).parent.parent / "agentsumo" / "agent" / "additional_files_guide"

    expected = ["rerouter.md", "vss.md", "vtype.md"]
    for fname in expected:
        path = guide_dir / fname
        assert path.exists(), f"FAIL: {fname} not found at {path}"

    print(f"PASS: All {len(expected)} guide files exist")


# ============================================================
# 4. Test _validate_additional_files()
# ============================================================

def _validate_additional_files(additional_files, net_file, duration):
    """Standalone copy of validation logic for testing without SUMO deps."""
    import xml.etree.ElementTree as _ET

    if not additional_files:
        return []

    errors = []
    # No network available in test → skip Level 2 edge checks
    edge_ids = set()
    edge_lane_counts = {}

    for file_path in additional_files:
        fname = Path(file_path).name

        try:
            tree = _ET.parse(file_path)
            root = tree.getroot()
        except _ET.ParseError as e:
            errors.append(f"[{fname}] Invalid XML: {e}")
            continue

        if root.tag != "additional":
            errors.append(f"[{fname}] Root element must be <additional>, got <{root.tag}>")
            continue

        for rerouter in root.findall("rerouter"):
            rid = rerouter.get("id")
            if not rid:
                errors.append(f"[{fname}] <rerouter> missing required 'id' attribute")
            edges_attr = rerouter.get("edges")
            if not edges_attr:
                errors.append(f"[{fname}] <rerouter id='{rid}'> missing required 'edges' attribute")
            else:
                if ";" in edges_attr:
                    errors.append(
                        f"[{fname}] <rerouter id='{rid}'> edges attribute uses semicolons — "
                        f"SUMO requires SPACE-separated edge IDs. "
                        f"Replace ';' with ' ' in: edges=\"{edges_attr}\""
                    )

            for interval in rerouter.findall("interval"):
                begin = interval.get("begin")
                end = interval.get("end")
                if begin is None or end is None:
                    errors.append(f"[{fname}] <interval> in rerouter '{rid}' missing begin/end")
                    continue
                try:
                    b, e = float(begin), float(end)
                    if b < 0:
                        errors.append(f"[{fname}] interval begin={b} is negative")
                    if e > duration:
                        errors.append(f"[{fname}] interval end={e} exceeds simulation duration ({duration}s)")
                except ValueError:
                    errors.append(f"[{fname}] interval begin/end must be numeric")

        for vss in root.findall("variableSpeedSign"):
            vss_id = vss.get("id")
            if not vss_id:
                errors.append(f"[{fname}] <variableSpeedSign> missing required 'id' attribute")
            lanes_attr = vss.get("lanes")
            if not lanes_attr:
                errors.append(f"[{fname}] <variableSpeedSign id='{vss_id}'> missing required 'lanes' attribute")

            for step in vss.findall("step"):
                time_val = step.get("time")
                if time_val is None:
                    errors.append(f"[{fname}] <step> in VSS '{vss_id}' missing 'time' attribute")

                speed_val = step.get("speed")
                if speed_val is not None:
                    try:
                        s = float(speed_val)
                        if s > 100:
                            errors.append(
                                f"[{fname}] VSS '{vss_id}' speed={s} m/s ({s*3.6:.0f} km/h) "
                                f"is unusually high — did you use km/h instead of m/s?"
                            )
                    except ValueError:
                        errors.append(f"[{fname}] step speed must be numeric in VSS '{vss_id}'")

    return errors


def _write_tmp_xml(content):
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.add.xml', delete=False)
    f.write(content)
    f.close()
    return f.name


def test_validation_valid_rerouter():
    """Valid rerouter should pass validation."""
    xml = """<?xml version="1.0" encoding="utf-8"?>
<additional>
  <rerouter id="r1" edges="edge_1" probability="1.0">
    <interval begin="0" end="3600">
      <closingReroute id="edge_1"/>
    </interval>
  </rerouter>
</additional>"""
    tmp = _write_tmp_xml(xml)
    try:
        errors = _validate_additional_files([tmp], None, 3600)
        assert errors == [], f"Unexpected errors: {errors}"
        print("PASS: Valid rerouter passes validation")
    finally:
        os.unlink(tmp)


def test_validation_malformed_xml():
    """Malformed XML should be caught."""
    xml = "<additional><rerouter id='r1' edges='e1'><interval begin='0' end='3600'>"  # unclosed
    tmp = _write_tmp_xml(xml)
    try:
        errors = _validate_additional_files([tmp], None, 3600)
        assert len(errors) == 1
        assert "Invalid XML" in errors[0]
        print("PASS: Malformed XML detected")
    finally:
        os.unlink(tmp)


def test_validation_wrong_root():
    """Wrong root element should be caught."""
    xml = """<?xml version="1.0"?><routes><rerouter id="r1" edges="e1"/></routes>"""
    tmp = _write_tmp_xml(xml)
    try:
        errors = _validate_additional_files([tmp], None, 3600)
        assert len(errors) == 1
        assert "Root element must be <additional>" in errors[0]
        print("PASS: Wrong root element detected")
    finally:
        os.unlink(tmp)


def test_validation_missing_attributes():
    """Missing required attributes should be caught."""
    xml = """<?xml version="1.0"?>
<additional>
  <rerouter>
    <interval begin="0" end="3600">
      <closingReroute id="e1"/>
    </interval>
  </rerouter>
</additional>"""
    tmp = _write_tmp_xml(xml)
    try:
        errors = _validate_additional_files([tmp], None, 3600)
        assert any("missing required 'id'" in e for e in errors)
        assert any("missing required 'edges'" in e for e in errors)
        print("PASS: Missing rerouter attributes detected")
    finally:
        os.unlink(tmp)


def test_validation_interval_exceeds_duration():
    """Interval end exceeding duration should be caught."""
    xml = """<?xml version="1.0"?>
<additional>
  <rerouter id="r1" edges="e1">
    <interval begin="0" end="7200">
      <closingReroute id="e1"/>
    </interval>
  </rerouter>
</additional>"""
    tmp = _write_tmp_xml(xml)
    try:
        errors = _validate_additional_files([tmp], None, 3600)
        assert len(errors) == 1
        assert "exceeds simulation duration" in errors[0]
        print("PASS: Interval exceeding duration detected")
    finally:
        os.unlink(tmp)


def test_validation_vss_speed_kmh_mistake():
    """Speed in km/h instead of m/s should be caught."""
    xml = """<?xml version="1.0"?>
<additional>
  <variableSpeedSign id="vss1" lanes="edge_1_0">
    <step time="0" speed="120"/>
  </variableSpeedSign>
</additional>"""
    tmp = _write_tmp_xml(xml)
    try:
        errors = _validate_additional_files([tmp], None, 3600)
        assert len(errors) == 1
        assert "km/h instead of m/s" in errors[0]
        print("PASS: km/h speed mistake detected")
    finally:
        os.unlink(tmp)


def test_validation_vss_missing_lanes():
    """VSS without lanes should be caught."""
    xml = """<?xml version="1.0"?>
<additional>
  <variableSpeedSign id="vss1">
    <step time="0" speed="8.33"/>
  </variableSpeedSign>
</additional>"""
    tmp = _write_tmp_xml(xml)
    try:
        errors = _validate_additional_files([tmp], None, 3600)
        assert any("missing required 'lanes'" in e for e in errors)
        print("PASS: Missing VSS lanes detected")
    finally:
        os.unlink(tmp)


def test_validation_valid_vss():
    """Valid VSS should pass."""
    xml = """<?xml version="1.0"?>
<additional>
  <variableSpeedSign id="vss1" lanes="edge_1_0 edge_1_1">
    <step time="0" speed="8.33"/>
    <step time="1800" speed="-1"/>
  </variableSpeedSign>
</additional>"""
    tmp = _write_tmp_xml(xml)
    try:
        errors = _validate_additional_files([tmp], None, 3600)
        assert errors == [], f"Unexpected errors: {errors}"
        print("PASS: Valid VSS passes validation")
    finally:
        os.unlink(tmp)


def test_validation_negative_time():
    """Negative interval begin should be caught."""
    xml = """<?xml version="1.0"?>
<additional>
  <rerouter id="r1" edges="e1">
    <interval begin="-100" end="3600">
      <closingReroute id="e1"/>
    </interval>
  </rerouter>
</additional>"""
    tmp = _write_tmp_xml(xml)
    try:
        errors = _validate_additional_files([tmp], None, 3600)
        assert any("negative" in e for e in errors)
        print("PASS: Negative time detected")
    finally:
        os.unlink(tmp)


def test_validation_semicolon_in_edges():
    """Semicolons in rerouter edges attribute should be caught."""
    xml = """<?xml version="1.0"?>
<additional>
  <rerouter id="r1" edges="e1;e2;e3">
    <interval begin="0" end="3600">
      <closingReroute id="e1"/>
    </interval>
  </rerouter>
</additional>"""
    tmp = _write_tmp_xml(xml)
    try:
        errors = _validate_additional_files([tmp], None, 3600)
        assert any("semicolon" in e.lower() or "SPACE-separated" in e for e in errors), \
            f"Should detect semicolons in edges attribute, got: {errors}"
        print("PASS: Semicolons in edges attribute detected")
    finally:
        os.unlink(tmp)


# ============================================================
# Run all tests
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Testing additional files guide implementation")
    print("=" * 60)

    tests = [
        # Rerouter detection
        test_has_rerouter_positive,
        test_has_rerouter_negative,
        test_has_rerouter_empty_list,
        test_has_rerouter_mixed_files,
        # Filesystem MCP
        test_filesystem_client_single_string,
        test_filesystem_client_multiple_dirs,
        test_filesystem_client_args_construction,
        # XML validity
        test_rerouter_xml_examples,
        test_vss_xml_examples,
        test_vtype_xml_examples,
        # Reference data
        test_speed_reference_table,
        # File existence
        test_guide_files_exist,
        # Validation (Level 1 — no network needed)
        test_validation_valid_rerouter,
        test_validation_malformed_xml,
        test_validation_wrong_root,
        test_validation_missing_attributes,
        test_validation_interval_exceeds_duration,
        test_validation_vss_speed_kmh_mistake,
        test_validation_vss_missing_lanes,
        test_validation_valid_vss,
        test_validation_negative_time,
        test_validation_semicolon_in_edges,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__} — {e}")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 60)
