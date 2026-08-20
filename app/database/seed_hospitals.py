import logging
from sqlalchemy.orm import Session
from app.models.hospitals import Facility
from app.models.facility_capability import FacilityCapability
from app.models.facility_user import FacilityUser
from app.models.api_key import APIKey
from app.database.db_connection import SessionLocal
from app.utils.security import hash_api_key, mask_api_key, get_password_hash

logger = logging.getLogger(__name__)

INITIAL_FACILITIES = [
    {
        "facility_name": "St. Jude General Hospital",
        "facility_type": "Level 1 Hospital",
        "ownership": "Private",
        "facility_head": "Dr. Corazon Ibarra",
        "region": "Region XI",
        "province": "Davao del Sur",
        "municipality": "Davao City",
        "barangay": "Talomo",
        "address": "123 Main St, Talomo, Davao City",
        "latitude": 7.0731,
        "longitude": 125.6128,
        "contact_number": "+639171234567",
        "email": "info@stjudehospital.ph",
        "lto_number": "LTO-11-2026-001",
        "lto_type": "Hospital Level 1",
        "lto_status": "Active",
        "facility_status": "Active",
        "api_key": "irdss_api_key_stjude_9a8b7c6d5e4f3a",
        "admin_username": "stjude_admin",
        "admin_password": "password123",
        "capability": {
            "authorized_bed_capacity": 100,
            "functional_beds": 80,
            "has_er_trauma": True,
            "has_icu": False,
            "has_nicu": False,
            "has_delivery_room": True,
            "has_hemodialysis": False,
            "has_blood_bank": False,
            "has_ct_mri": False,
            "has_cardiologist": False,
            "has_obgyn": True,
            "has_neurologist": False,
            "has_general_surgeon": True,
        }
    },
    {
        "facility_name": "City Care Medical Center",
        "facility_type": "Level 2 Hospital",
        "ownership": "Private",
        "facility_head": "Dr. Eduardo Marasigan",
        "region": "Region XI",
        "province": "Davao del Sur",
        "municipality": "Davao City",
        "barangay": "Poblacion",
        "address": "456 Central Ave, Davao City",
        "latitude": 7.0850,
        "longitude": 125.6200,
        "contact_number": "+639205551234",
        "email": "admin@citycaremed.ph",
        "lto_number": "LTO-11-2026-002",
        "lto_type": "Hospital Level 2",
        "lto_status": "Active",
        "facility_status": "Active",
        "api_key": "irdss_api_key_citycare_1b2c3d4e5f6a",
        "admin_username": "citycare_admin",
        "admin_password": "password123",
        "capability": {
            "authorized_bed_capacity": 120,
            "functional_beds": 98,
            "has_er_trauma": True,
            "has_icu": True,
            "has_nicu": False,
            "has_delivery_room": True,
            "has_hemodialysis": True,
            "has_blood_bank": True,
            "has_ct_mri": True,
            "has_cardiologist": True,
            "has_obgyn": True,
            "has_neurologist": False,
            "has_general_surgeon": True,
        }
    },
    {
        "facility_name": "Metro Health Medical Center",
        "facility_type": "Level 3 Hospital",
        "ownership": "Government",
        "facility_head": "Dr. Federico Aquino",
        "region": "Region XI",
        "province": "Davao del Sur",
        "municipality": "Davao City",
        "barangay": "Toril",
        "address": "789 Highway Blvd, Toril, Davao City",
        "latitude": 7.0620,
        "longitude": 125.6050,
        "contact_number": "+639193332211",
        "email": "contact@metrohealth.gov.ph",
        "lto_number": "LTO-11-2026-003",
        "lto_type": "Hospital Level 3",
        "lto_status": "Active",
        "facility_status": "Active",
        "api_key": "irdss_api_key_metro_9z8y7x6w5v4u",
        "admin_username": "metro_admin",
        "admin_password": "password123",
        "capability": {
            "authorized_bed_capacity": 200,
            "functional_beds": 150,
            "has_er_trauma": True,
            "has_icu": True,
            "has_nicu": True,
            "has_delivery_room": True,
            "has_hemodialysis": True,
            "has_blood_bank": True,
            "has_ct_mri": True,
            "has_cardiologist": True,
            "has_obgyn": True,
            "has_neurologist": True,
            "has_general_surgeon": True,
        }
    },
    {
        "facility_name": "Malagos Barangay Health Station",
        "facility_type": "BHS",
        "ownership": "Government",
        "facility_head": "Grace Villanueva",
        "region": "Region XI",
        "province": "Davao del Sur",
        "municipality": "Davao City",
        "barangay": "Malagos",
        "address": "Malagos, Davao City",
        "latitude": 7.1100,
        "longitude": 125.4500,
        "contact_number": "+639170001111",
        "email": "malagos.bhs@davao.gov.ph",
        "lto_number": "LTO-11-2026-004",
        "lto_type": "BHS",
        "lto_status": "Active",
        "facility_status": "Active",
        "api_key": "irdss_api_key_malagos_bhs_1a2b3c4d5e",
        "admin_username": "malagos_admin",
        "admin_password": "password123",
        "capability": {
            "authorized_bed_capacity": 5,
            "functional_beds": 5,
            "has_er_trauma": False,
            "has_icu": False,
            "has_nicu": False,
            "has_delivery_room": True,
            "has_hemodialysis": False,
            "has_blood_bank": False,
            "has_ct_mri": False,
            "has_cardiologist": False,
            "has_obgyn": False,
            "has_neurologist": False,
            "has_general_surgeon": False,
        }
    },
    {
        "facility_name": "Mintal Rural Health Unit",
        "facility_type": "RHU",
        "ownership": "Government",
        "facility_head": "Ramon Bautista",
        "region": "Region XI",
        "province": "Davao del Sur",
        "municipality": "Davao City",
        "barangay": "Mintal",
        "address": "Mintal, Davao City",
        "latitude": 7.0900,
        "longitude": 125.5300,
        "contact_number": "+639172223333",
        "email": "mintal.rhu@davao.gov.ph",
        "lto_number": "LTO-11-2026-005",
        "lto_type": "RHU",
        "lto_status": "Active",
        "facility_status": "Active",
        "api_key": "irdss_api_key_mintal_rhu_6f7g8h9i0j",
        "admin_username": "mintal_admin",
        "admin_password": "password123",
        "capability": {
            "authorized_bed_capacity": 15,
            "functional_beds": 12,
            "has_er_trauma": False,
            "has_icu": False,
            "has_nicu": False,
            "has_delivery_room": True,
            "has_hemodialysis": False,
            "has_blood_bank": False,
            "has_ct_mri": False,
            "has_cardiologist": False,
            "has_obgyn": True,
            "has_neurologist": False,
            "has_general_surgeon": False,
        }
    }
]


def seed_hospitals_and_keys(db: Session = None):
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        seeded_info = []
        for fac_data in INITIAL_FACILITIES:
            name = fac_data["facility_name"]
            raw_key_val = fac_data["api_key"]
            hashed_key_val = hash_api_key(raw_key_val)

            # 1. Seed / Check Facility
            facility = db.query(Facility).filter(Facility.facility_name.ilike(name)).first()
            if not facility:
                facility = Facility(
                    facility_name=name,
                    facility_type=fac_data["facility_type"],
                    ownership=fac_data["ownership"],
                    facility_head=fac_data["facility_head"],
                    region=fac_data["region"],
                    province=fac_data["province"],
                    municipality=fac_data["municipality"],
                    barangay=fac_data["barangay"],
                    address=fac_data["address"],
                    latitude=fac_data["latitude"],
                    longitude=fac_data["longitude"],
                    contact_number=fac_data["contact_number"],
                    email=fac_data["email"],
                    lto_number=fac_data["lto_number"],
                    lto_type=fac_data["lto_type"],
                    lto_status=fac_data["lto_status"],
                    facility_status=fac_data["facility_status"]
                )
                db.add(facility)
                db.flush()
                facility.facility_code = f"FAC-{facility.id:06d}"
                db.commit()
                db.refresh(facility)
                logger.info(f"Seeded facility: '{name}' (ID: {facility.id}, Code: {facility.facility_code})")
            elif not facility.facility_code:
                facility.facility_code = f"FAC-{facility.id:06d}"
                db.commit()

            # 2. Seed / Check FacilityCapability
            cap = db.query(FacilityCapability).filter(FacilityCapability.facility_id == facility.id).first()
            if not cap:
                cap_data = fac_data["capability"]
                cap = FacilityCapability(
                    facility_id=facility.id,
                    authorized_bed_capacity=cap_data["authorized_bed_capacity"],
                    functional_beds=cap_data["functional_beds"],
                    has_er_trauma=cap_data["has_er_trauma"],
                    has_icu=cap_data["has_icu"],
                    has_nicu=cap_data["has_nicu"],
                    has_delivery_room=cap_data["has_delivery_room"],
                    has_hemodialysis=cap_data["has_hemodialysis"],
                    has_blood_bank=cap_data["has_blood_bank"],
                    has_ct_mri=cap_data["has_ct_mri"],
                    has_cardiologist=cap_data["has_cardiologist"],
                    has_obgyn=cap_data["has_obgyn"],
                    has_neurologist=cap_data["has_neurologist"],
                    has_general_surgeon=cap_data["has_general_surgeon"]
                )
                db.add(cap)
                db.commit()
                logger.info(f"Seeded capability for facility '{name}'")

            # 3. Seed / Check FacilityUser
            fuser = db.query(FacilityUser).filter(FacilityUser.username == fac_data["admin_username"]).first()
            if not fuser:
                fuser = FacilityUser(
                    facility_id=facility.id,
                    username=fac_data["admin_username"],
                    password_hash=get_password_hash(fac_data["admin_password"]),
                    role="FACILITY_ADMIN",
                    status="Active"
                )
                db.add(fuser)
                db.commit()
                logger.info(f"Seeded facility user '{fac_data['admin_username']}' for '{name}'")

            # 4. Seed / Check api_keys
            api_key_rec = db.query(APIKey).filter(APIKey.hospital_name.ilike(name)).first()
            if not api_key_rec:
                api_key_rec = APIKey(
                    hospital_name=name,
                    api_key=hashed_key_val,
                    api_key_display=mask_api_key(raw_key_val),
                    is_active=True
                )
                db.add(api_key_rec)
                db.commit()
                db.refresh(api_key_rec)
                logger.info(f"Seeded API Key hash for facility '{name}'")

            seeded_info.append({
                "facility_id": facility.id,
                "facility_code": facility.facility_code,
                "facility_name": name,
                "admin_username": fac_data["admin_username"],
                "raw_api_key": raw_key_val
            })

        return seeded_info

    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding facility database: {str(e)}")
        raise
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    info = seed_hospitals_and_keys()
    print("\nDatabase seeding completed successfully:")
    for item in info:
        print(f"Facility [{item['facility_code']}] ID {item['facility_id']}: '{item['facility_name']}'")
        print(f"  -> Admin User: {item['admin_username']}")
        print(f"  -> Raw API Key: {item['raw_api_key']}")
