"""Fictional engineering corpus ("Program Halcyon"). Every fact, ID and document is invented
so the eval ground truth is known exactly. Replace/extend with real public PDFs (e.g. NASA NTRS)."""

DOCS = [
 ("battery_thermal_design_spec.pdf", "Battery Thermal Design Specification, Program Halcyon (fictional), Doc ENG-BT-0412", [
  ("1. Scope", "This specification defines thermal design requirements for the 82 kWh high voltage battery pack used on the Halcyon platform. It covers cell temperature limits, the coolant loop, thermal runaway containment and verification. It applies to pack revision C and later."),
  ("2. Cell Operating Temperature", "Cells shall operate between -20 C and 55 C during driving. Charging above 45 C cell temperature is not permitted; the battery management system reduces charge current linearly from 40 C. The maximum allowed temperature spread across cells within the pack is 5 C."),
  ("3. Coolant Loop", "The pack uses a 50/50 water glycol coolant at a nominal flow rate of 8 liters per minute. The loop has two electric pumps in a redundant arrangement so that a single pump failure keeps at least 60 percent of nominal flow. Coolant inlet temperature is controlled by a chiller connected to the vehicle air conditioning circuit."),
  ("4. Thermal Runaway Containment", "Per REQ-104, thermal runaway in a single cell shall not propagate to adjacent modules for at least 5 minutes, giving occupants time to exit. Mica barriers are placed between modules and the pack vent directs gases away from the cabin. Verification is by test case TC-204, a nail penetration test on a fully charged module."),
  ("5. Limits Summary", [["Parameter", "Limit", "Unit"], ["Min operating temp", "-20", "C"], ["Max operating temp", "55", "C"], ["Max charge temp", "45", "C"], ["Max cell temperature spread", "5", "C"], ["Coolant flow rate", "8", "L/min"]]),
 ]),
 ("hv_connector_vibration_test_report.pdf", "High Voltage Connector Vibration Test Report, Doc TR-HV-0077 (fictional)", [
  ("1. Summary", "Connector family HV-7 was tested to the vibration profile in REQ-112. Two of six samples failed. The failure was logged as FAIL-88 and corrective action is tracked in change request CR-13."),
  ("2. Test Setup", "Samples were mounted on an electrodynamic shaker and excited with random vibration from 20 Hz to 2000 Hz in three axes for 16 hours per axis. Contact resistance was monitored continuously with 1 milliohm resolution."),
  ("3. Results", "Sample 3 and sample 5 showed contact resistance rise above the 5 milliohm limit after 14 hours on the Z axis. Teardown found fretting corrosion on the tin plated terminals."),
  ("4. Corrective Action", "The proposed fix in CR-13 replaces tin plating with silver plating on the power terminals and adds a secondary terminal lock. Re-test is planned under test case TC-212 after the change is implemented."),
  ("5. Sample Results", [["Sample", "Axis", "Hours to failure", "Result"], ["1", "Z", "none", "Pass"], ["3", "Z", "14", "Fail"], ["5", "Z", "14", "Fail"], ["6", "X", "none", "Pass"]]),
 ]),
 ("brake_by_wire_requirements.pdf", "Brake by Wire System Requirements, Doc SR-BBW-0210 (fictional)", [
  ("1. Purpose", "This document lists system level requirements for the electro hydraulic brake by wire system, including latency, redundancy and degraded mode behaviour."),
  ("2. Response Latency", "From pedal input to hydraulic pressure build the brake system shall respond within 120 milliseconds at all temperatures from -40 C to 85 C. This is requirement REQ-109 and it is verified by test case TC-209 on the hardware in the loop rig."),
  ("3. Redundancy", "Two independent brake control units are powered from separate 12 volt supplies. If the primary unit fails the secondary unit takes over within 50 milliseconds."),
  ("4. Degraded Mode", "When only one brake control unit is available the vehicle limits speed to 80 km/h and guarantees at least 0.3 g deceleration. The driver is warned with a red brake telltale and a chime."),
 ]),
 ("charging_interface_control_document.pdf", "DC Fast Charging Interface Control Document, Doc ICD-CHG-0031 (fictional)", [
  ("1. Scope", "This interface control document defines the electrical and communication interface between the vehicle charging inlet and off board DC fast chargers."),
  ("2. Power Limits", "The vehicle accepts DC fast charging up to 350 kW on the CCS1 inlet. Maximum charging current is 500 A and the supported voltage window is 400 V to 920 V."),
  ("3. Communication", "Charger to vehicle communication uses ISO 15118 over power line communication, with DIN 70121 as a fallback for older chargers. Plug and Charge certificates are stored in the vehicle hardware security module."),
  ("4. Safety Monitoring", "The insulation monitoring threshold is 500 ohms per volt. Pre-charge of the DC link must complete within 300 milliseconds or the charging session is aborted. This requirement is REQ-118."),
 ]),
 ("adas_camera_calibration_procedure.pdf", "ADAS Front Camera Calibration Procedure, Doc PR-ADAS-0105 (fictional)", [
  ("1. When to Calibrate", "Static camera calibration is required after windshield replacement, camera bracket replacement, or a wheel alignment change greater than 0.5 degrees."),
  ("2. Target Setup", "Place the calibration target 4.5 meters in front of the front axle centerline, aligned to the vehicle thrust line. Ambient lighting at the target must be at least 500 lux with no direct sunlight."),
  ("3. Acceptance", "Calibration passes when yaw, pitch and roll errors are each within 0.1 degrees. If calibration fails three times, inspect the camera bracket for damage before retrying."),
 ]),
 ("salt_spray_corrosion_test.pdf", "Salt Spray Corrosion Test Report, Doc TR-COR-0219 (fictional)", [
  ("1. Method", "Parts were exposed to neutral salt spray per ASTM B117 for 720 hours. Inspections were made every 96 hours."),
  ("2. Acceptance Criteria", "No red rust is permitted on Class A visible surfaces. White corrosion on zinc coated fasteners is acceptable up to 240 hours."),
  ("3. Results", "The rear subframe bracket showed red rust at 480 hours on a weld seam, failing the criteria of REQ-125. The failure was logged as FAIL-89 and addressed by change request CR-14, which added an e-coat touch up step; CR-14 is now closed."),
 ]),
 ("vcu_software_release_notes.pdf", "Vehicle Control Unit Software Release Notes, Version 4.2.1 (fictional)", [
  ("1. Fixes", "Fixed a torque limiting bug where creep torque was applied for 200 milliseconds after the driver selected park. Fixed a diagnostic trouble code that was set falsely during over the air updates."),
  ("2. Known Issues", "Regenerative braking is disabled when battery temperature is below -10 C because cold cells cannot accept high charge current; the driver is informed by a message in the cluster. A fix is planned for version 4.3."),
  ("3. Compatibility", "VCU version 4.2.1 requires battery management firmware 7.8 or later and must be flashed together with gateway software 2.14."),
 ]),
 ("design_review_minutes_q3.pdf", "Design Review Minutes, Q3, Program Halcyon (fictional)", [
  ("1. Attendees", "Battery engineering lead, chassis systems lead, quality engineer, program manager and validation lead. Roles only; the program is fictional."),
  ("2. Decisions", "The review board approved CR-12, which adds an extra mica barrier layer to address the thermal propagation failure FAIL-87. The board deferred CR-15 for brake latency to the next review pending supplier data."),
  ("3. Action Items", "The validation lead will rerun TC-204 after the CR-12 hardware arrives. The chassis lead will obtain updated valve timing data from the brake supplier before the next review."),
 ]),
]
