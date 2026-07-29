from sqlalchemy import Column, Integer, String, Float, Boolean
from app.database.db_connection import Base

class HospitalResources(Base):
    __tablename__ = "hospital_resources"
    id = Column(Integer, primary_key=True, index=True)
    hospital_name = Column(String, index=True)
    hospital_level = Column(String)
    hospital_environment = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    available_beds = Column(Integer)
    emergency_equipment = Column(Boolean)  # e.g., crash carts, intubation supplies
    medical_equipment = Column(Boolean)
    communication_systems = Column(Boolean)
    medical_specialists_count = Column(Integer)