import json
from sqlalchemy.orm import Session
from database import SessionLocal, HospitalResources  # Adjust imports based on your structure [cite: 101]

def seed_pso_thresholds():
    db = SessionLocal()
    try:
        # Load the configuration we generated
        with open("/workspace/scratch/pso_capacity_config.json", "r") as f: [cite: 57]
            config = json.load(f)

        capacities = config.get("hospital_capacities", [])

        for item in capacities:
            # Match by name or ID in your mock DB [cite: 101]
            hospital = db.query(HospitalResources).filter(
                HospitalResources.id == item["hospital_id"]
            ).first()

            if hospital:
                hospital.pso_daily_routing_limit = item["pso_daily_routing_limit"]
                hospital.referrals_accepted_today = 0  # Re-initialize daily count [cite: 101]
                print(f"Updated {hospital.hospital_name} with PSO routing limit: {hospital.pso_daily_routing_limit}")
            else:
                # If the hospital doesn't exist, create it! [cite: 101]
                new_hospital = HospitalResources(
                    id=item["hospital_id"],
                    hospital_name=item["name"],
                    available_beds=item["actual_bed_capacity"],
                    pso_daily_routing_limit=item["pso_daily_routing_limit"],
                    referrals_accepted_today=0
                )
                db.add(new_hospital)
                print(f"Created and seeded {new_hospital.hospital_name}")

        db.commit()
        print("Database successfully seeded with optimized PSO capacities!") [cite: 57]
    except Exception as e:
        db.rollback()
        print(f"Seeding failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_pso_thresholds()