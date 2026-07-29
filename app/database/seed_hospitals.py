import logging
from sqlalchemy.orm import Session
from app.models.hospitals import HospitalResources
from app.models.api_key import APIKey
from app.database.db_connection import SessionLocal
from app.utils.security import hash_api_key

logger = logging.getLogger(__name__)

INITIAL_HOSPITALS = [
    {
        "hospital_name": "St. Jude General Hospital",
        "hospital_level": "Level 2",
        "hospital_environment": "Urban",
        "latitude": 7.0731,
        "longitude": 125.6128,
        "available_beds": 100,
        "emergency_equipment": True,
        "medical_equipment": True,
        "communication_systems": True,
        "medical_specialists_count": 30,
        "api_key": "irdss_api_key_stjude_9a8b7c6d5e4f3a"
    },
    {
        "hospital_name": "City Care Medical Center",
        "hospital_level": "Level 2",
        "hospital_environment": "Urban",
        "latitude": 7.0850,
        "longitude": 125.6200,
        "available_beds": 80,
        "emergency_equipment": True,
        "medical_equipment": True,
        "communication_systems": True,
        "medical_specialists_count": 22,
        "api_key": "irdss_api_key_citycare_1f2e3d4c5b6a7f"
    },
    {
        "hospital_name": "Metro Health Medical Center",
        "hospital_level": "Level 3",
        "hospital_environment": "Urban",
        "latitude": 7.0620,
        "longitude": 125.6050,
        "available_beds": 150,
        "emergency_equipment": True,
        "medical_equipment": True,
        "communication_systems": True,
        "medical_specialists_count": 50,
        "api_key": "irdss_api_key_metrohealth_8e7d6c5b4a3f2e"
    }
]


def seed_hospitals_and_keys(db: Session = None):
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        seeded_info = []
        for hosp_data in INITIAL_HOSPITALS:
            name = hosp_data["hospital_name"]
            raw_key_val = hosp_data["api_key"]
            hashed_key_val = hash_api_key(raw_key_val)

            # 1. Seed / Check hospital_resources
            hospital = db.query(HospitalResources).filter(HospitalResources.hospital_name == name).first()
            if not hospital:
                hospital = HospitalResources(
                    hospital_name=name,
                    hospital_level=hosp_data["hospital_level"],
                    hospital_environment=hosp_data["hospital_environment"],
                    latitude=hosp_data["latitude"],
                    longitude=hosp_data["longitude"],
                    available_beds=hosp_data["available_beds"],
                    emergency_equipment=hosp_data["emergency_equipment"],
                    medical_equipment=hosp_data["medical_equipment"],
                    communication_systems=hosp_data["communication_systems"],
                    medical_specialists_count=hosp_data["medical_specialists_count"]
                )
                db.add(hospital)
                db.commit()
                db.refresh(hospital)
                logger.info(f"Seeded hospital resource: '{name}' (ID: {hospital.id})")

            # 2. Seed / Check api_keys (storing SHA-256 hash)
            api_key_rec = db.query(APIKey).filter(APIKey.hospital_name == name).first()
            if not api_key_rec:
                api_key_rec = APIKey(
                    hospital_name=name,
                    api_key=hashed_key_val,
                    is_active=True
                )
                db.add(api_key_rec)
                db.commit()
                db.refresh(api_key_rec)
                logger.info(f"Seeded SHA-256 API Key hash for hospital '{name}'")

            seeded_info.append({
                "hospital_id": hospital.id,
                "hospital_name": name,
                "raw_api_key": raw_key_val,
                "api_key_hash": api_key_rec.api_key
            })

        return seeded_info

    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding hospital database: {str(e)}")
        raise
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    info = seed_hospitals_and_keys()
    print("Database seeding completed successfully:")
    for item in info:
        print(f"Hospital ID {item['hospital_id']}: '{item['hospital_name']}'")
        print(f"  -> Raw Key: {item['raw_api_key']}")
        print(f"  -> SHA-256 Hash stored in DB: {item['api_key_hash']}")
