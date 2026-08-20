"""
Pre-made Official DOH Service Assessment Forms for APEX Hospital (Levels 1-3), RHU (Primary Care), and BHS.
Contains static structural metadata and filtering logic — no dynamic admin template building required.
"""

# 1. APEX / HOSPITAL ASSESSMENT FORM (Levels 1 - 3)
HOSPITAL_ASSESSMENT_FORM = {
    "form_type": "HOSPITAL",
    "title": "DOH Health Facility Assessment Instrument — Hospital (Levels 1–3)",
    "description": "Official Department of Health assessment tool for Levels 1, 2, and 3 hospitals covering medical services, nursing service, physical plant, personnel counts, and major equipment.",
    "sections": [
        {
            "section_id": "info",
            "title": "A. Assessment Information",
            "type": "metadata",
            "fields": [
                {"item_code": "assessment_type", "label": "Assessment Type", "type": "select", "options": ["New", "Renewal", "Monitoring"], "required": True},
                {"item_code": "assessment_date", "label": "Assessment Date", "type": "date", "required": True},
                {"item_code": "assessment_period", "label": "Assessment Period", "type": "text", "placeholder": "e.g., CY 2026", "required": True},
                {"item_code": "assessor_name", "label": "Person Completing Assessment", "type": "text", "required": True},
                {"item_code": "general_remarks", "label": "General Remarks", "type": "textarea", "required": False}
            ]
        },
        {
            "section_id": "medical_services",
            "title": "B. Medical Services",
            "type": "services",
            "description": "Indicate service availability and operational status. Items are filtered by hospital level applicability.",
            "items": [
                {"item_code": "er", "label": "Emergency Room (ER)", "min_level": "LEVEL_1"},
                {"item_code": "opd", "label": "Outpatient Department (OPD)", "min_level": "LEVEL_1"},
                {"item_code": "ward", "label": "Inpatient / Ward Service", "min_level": "LEVEL_1"},
                {"item_code": "or", "label": "Operating Room (OR)", "min_level": "LEVEL_1"},
                {"item_code": "obgyn_service", "label": "Obstetric Service", "min_level": "LEVEL_1"},
                {"item_code": "pediatric_service", "label": "Pediatric Service", "min_level": "LEVEL_1"},
                {"item_code": "medical_service", "label": "Medical Service", "min_level": "LEVEL_1"},
                {"item_code": "surgical_service", "label": "Surgical Service", "min_level": "LEVEL_1"},
                {"item_code": "anesthesia_service", "label": "Anesthesia Service", "min_level": "LEVEL_1"},
                {"item_code": "high_risk_pregnancy", "label": "High-Risk Pregnancy Care", "min_level": "LEVEL_2"},
                {"item_code": "nicu", "label": "Neonatal Intensive Care Unit (NICU)", "min_level": "LEVEL_2"},
                {"item_code": "icu", "label": "Intensive Care Unit (ICU)", "min_level": "LEVEL_2"},
                {"item_code": "respiratory_unit", "label": "Respiratory Care Unit", "min_level": "LEVEL_2"},
                {"item_code": "pmr", "label": "Physical Medicine & Rehabilitation (PM&R)", "min_level": "LEVEL_2"},
                {"item_code": "ambulatory_surgery", "label": "Ambulatory Surgical Clinic", "min_level": "LEVEL_2"},
                {"item_code": "dialysis", "label": "Dialysis Clinic / Unit", "min_level": "LEVEL_2"},
                {"item_code": "teaching_training", "label": "Teaching / Training Service", "min_level": "LEVEL_3"},
                {"item_code": "blood_bank", "label": "Blood Bank / Blood Service Facility", "min_level": "LEVEL_2"},
                {"item_code": "gensurg_service", "label": "General Surgery Service (General Surgeon on Staff)", "min_level": "LEVEL_1"},
                {"item_code": "cardio_service", "label": "Cardiology Service (Cardiologist on Staff)", "min_level": "LEVEL_2"},
                {"item_code": "neuro_service", "label": "Neurology Service (Neurologist on Staff)", "min_level": "LEVEL_2"}
            ]
        },
        {
            "section_id": "nursing_service",
            "title": "C. Nursing Service",
            "type": "compliance",
            "description": "Evaluate DOH Hospital Nursing Service compliance.",
            "items": [
                {"item_code": "nursing_dept", "label": "Organized Nursing Department"},
                {"item_code": "nursing_personnel", "label": "Licensed Nursing Personnel Staffing"},
                {"item_code": "nursing_policies", "label": "Written Nursing Policies & Standard Operating Procedures"},
                {"item_code": "patient_care_doc", "label": "Patient Care Documentation & Charts"},
                {"item_code": "nursing_records", "label": "Nursing Administrative & Clinical Records"},
                {"item_code": "nursing_staffing", "label": "Shift Staffing & Duty Rosters"},
                {"item_code": "nursing_stations", "label": "Equipped Ward Nursing Stations"},
                {"item_code": "patient_procedures", "label": "Standardized Patient Care Procedures"}
            ]
        },
        {
            "section_id": "physical_plant",
            "title": "D. Physical Plant",
            "type": "compliance",
            "description": "Evaluate hospital facility infrastructure compliance.",
            "items": [
                {"item_code": "patient_rooms", "label": "Patient Rooms & Private Accommodation"},
                {"item_code": "wards", "label": "General Patient Wards"},
                {"item_code": "emergency_area", "label": "Dedicated Emergency Area"},
                {"item_code": "operating_room_plant", "label": "Sterile Operating Room Suite"},
                {"item_code": "nursing_stations_plant", "label": "Central Nursing Stations"},
                {"item_code": "consultation_rooms", "label": "OPD Consultation Rooms"},
                {"item_code": "water_supply", "label": "Continuous Clean Water Supply"},
                {"item_code": "electrical_supply", "label": "Continuous Electrical Supply & Backup Generator"},
                {"item_code": "lighting", "label": "Adequate Facility Lighting"},
                {"item_code": "ventilation", "label": "Adequate Air Ventilation & HVAC"},
                {"item_code": "sanitation", "label": "Sanitation & Hygiene Infrastructure"},
                {"item_code": "waste_mgmt", "label": "Healthcare Waste Management System"},
                {"item_code": "fire_safety", "label": "Fire Protection & Alarm System"},
                {"item_code": "accessibility", "label": "Accessibility Infrastructure (PWD Ramps/Lifts)"}
            ]
        },
        {
            "section_id": "personnel",
            "title": "E. Personnel & Bed Capacity",
            "type": "counts",
            "description": "Report current facility personnel counts and bed capacity (individual physician/nurse details remain in local HIS).",
            "items": [
                {"item_code": "functional_beds", "label": "Total Functional / Available Beds"},
                {"item_code": "num_physicians", "label": "Number of Physicians"},
                {"item_code": "num_nurses", "label": "Number of Registered Nurses"},
                {"item_code": "num_midwives", "label": "Number of Midwives"},
                {"item_code": "num_allied_health", "label": "Number of Allied Health Professionals"},
                {"item_code": "num_admin_staff", "label": "Number of Administrative & Support Staff"}
            ]
        },
        {
            "section_id": "equipment",
            "title": "F. Major Equipment",
            "type": "equipment",
            "description": "Report inventory, availability, and functional status of major hospital equipment.",
            "items": [
                {"item_code": "eq_anesthesia", "label": "Anesthesia Machine"},
                {"item_code": "eq_ventilator", "label": "Mechanical Ventilator"},
                {"item_code": "eq_monitor", "label": "Multiparameter Patient Monitor"},
                {"item_code": "eq_defibrillator", "label": "Defibrillator / Cardiac Monitor"},
                {"item_code": "eq_infusion_pump", "label": "Infusion / Syringe Pump"},
                {"item_code": "eq_suction", "label": "Medical Suction Machine"},
                {"item_code": "eq_xray", "label": "Digital Diagnostic X-Ray Unit"},
                {"item_code": "eq_ultrasound", "label": "Diagnostic Ultrasound Machine"},
                {"item_code": "eq_incubator", "label": "Infant Incubator"},
                {"item_code": "eq_autoclave", "label": "Autoclave / Steam Sterilizer"}
            ]
        }
    ]
}


# 2. RHU / PRIMARY CARE ASSESSMENT FORM (RHU)
RHU_ASSESSMENT_FORM = {
    "form_type": "RHU",
    "title": "DOH Primary Care Facility (RHU) Assessment Instrument",
    "description": "Official Department of Health assessment tool for Rural Health Units (RHU) covering primary healthcare services, ancillary diagnostics, minor surgery, infrastructure, personnel, and supervisory duties.",
    "sections": [
        {
            "section_id": "info",
            "title": "A. Assessment Information",
            "type": "metadata",
            "fields": [
                {"item_code": "assessment_type", "label": "Assessment Type", "type": "select", "options": ["New", "Renewal", "Monitoring"], "required": True},
                {"item_code": "assessment_date", "label": "Assessment Date", "type": "date", "required": True},
                {"item_code": "assessment_period", "label": "Assessment Period", "type": "text", "placeholder": "e.g., CY 2026", "required": True},
                {"item_code": "assessor_name", "label": "Person Completing Assessment", "type": "text", "required": True},
                {"item_code": "general_remarks", "label": "General Remarks", "type": "textarea", "required": False}
            ]
        },
        {
            "section_id": "primary_care_services",
            "title": "B. Primary Healthcare Services",
            "type": "services",
            "items": [
                {"item_code": "rhu_consultation", "label": "General Physician Consultation"},
                {"item_code": "rhu_maternal", "label": "Maternal Health Services"},
                {"item_code": "rhu_newborn", "label": "Newborn Care Services"},
                {"item_code": "rhu_child_health", "label": "Child Health Services"},
                {"item_code": "rhu_immunization", "label": "Expanded Program on Immunization (EPI)"},
                {"item_code": "rhu_family_planning", "label": "Family Planning Services"},
                {"item_code": "rhu_adolescent", "label": "Adolescent Health Services"},
                {"item_code": "rhu_nutrition", "label": "Nutrition Services"},
                {"item_code": "rhu_communicable", "label": "Communicable Disease Prevention & Control"},
                {"item_code": "rhu_non_communicable", "label": "Non-Communicable Disease Management"},
                {"item_code": "rhu_health_ed", "label": "Health Education & Promotion"},
                {"item_code": "rhu_outreach", "label": "Community Health & Barangay Outreach"},
                {"item_code": "rhu_referral", "label": "Patient Referral & Navigation Services"}
            ]
        },
        {
            "section_id": "ancillary_services",
            "title": "C. Diagnostic / Ancillary Services",
            "type": "services",
            "items": [
                {"item_code": "rhu_lab", "label": "Primary Care Clinical Laboratory"},
                {"item_code": "rhu_pharmacy", "label": "Pharmacy / Medicine Dispensing Unit"},
                {"item_code": "rhu_basic_diagnostic", "label": "Basic Diagnostic Services"},
                {"item_code": "rhu_other_ancillary", "label": "Other Ancillary Healthcare Services"}
            ]
        },
        {
            "section_id": "minor_surgery",
            "title": "D. Minor Surgical Services",
            "type": "minor_surgery",
            "items": [
                {"item_code": "surg_suturing", "label": "Suturing of Wounds"},
                {"item_code": "surg_circumcision", "label": "Circumcision"},
                {"item_code": "surg_incision_drainage", "label": "Incision and Drainage"},
                {"item_code": "surg_debridement", "label": "Wound Debridement"},
                {"item_code": "surg_excision_cysts", "label": "Excision of Small Cysts / Lesions"}
            ]
        },
        {
            "section_id": "personnel",
            "title": "E. Personnel Counts",
            "type": "counts",
            "items": [
                {"item_code": "num_physicians", "label": "Physicians"},
                {"item_code": "num_nurses", "label": "Nurses"},
                {"item_code": "num_midwives", "label": "Midwives"},
                {"item_code": "num_med_techs", "label": "Medical Technologists"},
                {"item_code": "num_pharmacists", "label": "Pharmacists"},
                {"item_code": "num_other_health", "label": "Other Health Personnel"}
            ]
        },
        {
            "section_id": "infrastructure",
            "title": "F. Facility / Infrastructure",
            "type": "infrastructure",
            "items": [
                {"item_code": "infra_consultation_room", "label": "Consultation Room"},
                {"item_code": "infra_treatment_room", "label": "Treatment Room"},
                {"item_code": "infra_maternal_delivery", "label": "Maternal / Delivery Area"},
                {"item_code": "infra_pharmacy_area", "label": "Pharmacy / Dispensing Area"},
                {"item_code": "infra_laboratory_area", "label": "Laboratory Room"},
                {"item_code": "infra_waiting_area", "label": "Patient Waiting Area"},
                {"item_code": "infra_toilet", "label": "Clean Sanitary Toilet Facilities"},
                {"item_code": "infra_water", "label": "Clean Potable Water Supply"},
                {"item_code": "infra_electricity", "label": "Reliable Power / Generator Supply"},
                {"item_code": "infra_waste", "label": "Waste Segregation & Disposal System"},
                {"item_code": "infra_emergency_area", "label": "Emergency Triage Area"}
            ]
        },
        {
            "section_id": "supervisory_services",
            "title": "G. Supervisory Services",
            "type": "services_simple",
            "items": [
                {"item_code": "sup_patient_nav", "label": "Patient Navigation & Referral System"},
                {"item_code": "sup_bhs_supervision", "label": "Supervision of Barangay Health Stations (BHS)"},
                {"item_code": "sup_bhw_supervision", "label": "Supervision of Barangay Health Workers (BHW)"},
                {"item_code": "sup_community_activities", "label": "Community Public Health Campaigns"}
            ]
        }
    ]
}


# 3. BARANGAY HEALTH STATION ASSESSMENT FORM (BHS)
BHS_ASSESSMENT_FORM = {
    "form_type": "BHS",
    "title": "DOH Barangay Health Station (BHS) Assessment Instrument",
    "description": "Official Department of Health basic assessment tool for Barangay Health Stations covering essential primary services, health workers, basic infrastructure, and equipment.",
    "sections": [
        {
            "section_id": "info",
            "title": "A. Assessment Information",
            "type": "metadata",
            "fields": [
                {"item_code": "assessment_date", "label": "Assessment Date", "type": "date", "required": True},
                {"item_code": "assessment_period", "label": "Assessment Period", "type": "text", "placeholder": "e.g., CY 2026", "required": True},
                {"item_code": "assessor_name", "label": "Person Completing Assessment", "type": "text", "required": True},
                {"item_code": "general_remarks", "label": "General Remarks", "type": "textarea", "required": False}
            ]
        },
        {
            "section_id": "basic_services",
            "title": "B. Basic Health Services",
            "type": "services",
            "items": [
                {"item_code": "bhs_consultation", "label": "Basic Health Consultation"},
                {"item_code": "bhs_maternal", "label": "Maternal Health & Prenatal Care"},
                {"item_code": "bhs_child", "label": "Child Health Services"},
                {"item_code": "bhs_immunization", "label": "Childhood Immunization Outreach"},
                {"item_code": "bhs_family_planning", "label": "Family Planning Counseling & Supplies"},
                {"item_code": "bhs_nutrition", "label": "Nutritional Weighing & Monitoring"},
                {"item_code": "bhs_health_ed", "label": "Community Health Education"},
                {"item_code": "bhs_prevention", "label": "Disease Prevention & Mosquito Control"},
                {"item_code": "bhs_community_activities", "label": "Barangay Health Assemblies & Activities"}
            ]
        },
        {
            "section_id": "bhs_personnel",
            "title": "C. Personnel",
            "type": "bhs_personnel",
            "items": [
                {"item_code": "bhw", "label": "Barangay Health Worker (BHW)"},
                {"item_code": "midwife", "label": "Assigned Rural Health Midwife"},
                {"item_code": "nurse", "label": "Visiting Public Health Nurse"},
                {"item_code": "other_staff", "label": "Other Health Support Staff"}
            ]
        },
        {
            "section_id": "basic_infrastructure",
            "title": "D. Basic Facility / Infrastructure",
            "type": "infrastructure",
            "items": [
                {"item_code": "bhs_consultation_area", "label": "Consultation Area"},
                {"item_code": "bhs_waiting_area", "label": "Waiting Area"},
                {"item_code": "bhs_toilet", "label": "Sanitary Toilet Facility"},
                {"item_code": "bhs_water", "label": "Water Supply"},
                {"item_code": "bhs_electricity", "label": "Electricity / Power Source"},
                {"item_code": "bhs_handwashing", "label": "Handwashing Facility with Soap"},
                {"item_code": "bhs_waste", "label": "Waste Disposal Area"},
                {"item_code": "bhs_medicine_storage", "label": "Medicine / Supply Cabinet"}
            ]
        },
        {
            "section_id": "basic_equipment",
            "title": "E. Basic Equipment",
            "type": "equipment",
            "items": [
                {"item_code": "bp_apparatus", "label": "Blood Pressure (BP) Apparatus"},
                {"item_code": "stethoscope", "label": "Stethoscope"},
                {"item_code": "thermometer", "label": "Clinical Thermometer"},
                {"item_code": "weighing_scale", "label": "Adult & Infant Weighing Scale"},
                {"item_code": "tape_measure", "label": "Height Board / Tape Measure"},
                {"item_code": "first_aid_kit", "label": "Emergency First Aid Kit"},
                {"item_code": "emergency_light", "label": "Emergency Light / Flashlight"},
                {"item_code": "supply_cabinet", "label": "Locked Medicine Storage Box"}
            ]
        }
    ]
}


def get_premade_doh_form(facility_type: str, facility_level: str = None) -> dict:
    """
    Returns the exact pre-made DOH Service Assessment form based on facility_type and facility_level.
    Filters hospital items by hospital level applicability.
    """
    ftype = (facility_type or "HOSPITAL").upper()
    flevel = (facility_level or "LEVEL_1").upper()

    if "RHU" in ftype or "RURAL" in ftype:
        return RHU_ASSESSMENT_FORM
    elif "BHS" in ftype or "BARANGAY" in ftype:
        return BHS_ASSESSMENT_FORM
    else:
        # Hospital Form — filter medical services by min_level
        form = HOSPITAL_ASSESSMENT_FORM.copy()
        filtered_sections = []

        level_rank = {"LEVEL_1": 1, "LEVEL_2": 2, "LEVEL_3": 3}
        current_rank = level_rank.get(flevel, 1)

        for sec in form["sections"]:
            if sec["section_id"] == "medical_services":
                filtered_items = []
                for item in sec["items"]:
                    min_lvl = item.get("min_level", "LEVEL_1")
                    item_rank = level_rank.get(min_lvl, 1)
                    if item_rank <= current_rank:
                        filtered_items.append(item)
                
                sec_copy = sec.copy()
                sec_copy["items"] = filtered_items
                filtered_sections.append(sec_copy)
            else:
                filtered_sections.append(sec)

        form_copy = form.copy()
        form_copy["sections"] = filtered_sections
        return form_copy
